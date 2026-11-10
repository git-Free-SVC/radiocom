"""WebSocket behaviour (§17 + ws_contract.py): snapshot-then-delta ordering,
frozen link-schema conformance, unknown-id close 4404 before subscribe,
unsubscribe cleanup (subscription_count() == 0), bounded-queue backpressure
(drop oldest, publisher never blocks) and the 1000-cycle stress run.

No websockets/wsproto/httpx is installed: every test drives the ASGI
interface in-process and runs its async body with asyncio.run().
"""

from __future__ import annotations

import asyncio
import json as jsonlib
import threading
import time
from typing import Any

import jsonschema
from conftest import (  # type: ignore[import-not-found]
    VALID_RADIO_BODY,
    asgi_request,
    ws_connect,
)

from services.api.mocks import InMemoryEventBus
from services.api.schemas import LINK_EVENT_SCHEMA_PATH, load_frozen_schema
from services.api.ws_connection import WsConnection
from services.api.ws_contract import (
    CHANNEL_LINK,
    CHANNEL_MAP,
    CHANNEL_RADIO,
    CHANNEL_SPECTRUM,
    CLOSE_UNKNOWN_SIMULATION,
    KIND_DELTA,
    KIND_SNAPSHOT,
    QUEUE_MAXSIZE,
    SPECTRUM_TOPIC,
    WS_DATA_SCHEMAS,
    telemetry_topic,
)

SEEDED_TELEMETRY_PATH = "/ws/simulations/sim_0001/telemetry"
FROZEN_LINK_SCHEMA = load_frozen_schema(LINK_EVENT_SCHEMA_PATH)

LINK_EVENT_INSTANCE = {
    "tx_id": "rdr_0009",
    "rx_id": "rdr_0010",
    "snr_db": 7.5,
    "margin_db": -1.0,
    "quality": "marginal",
    "time_s": 12.25,
}


def assert_envelope(message: dict[str, Any], *, kind: str, channel: str) -> Any:
    assert set(message.keys()) == {"kind", "channel", "seq", "data"}, message
    assert message["kind"] == kind, message
    assert message["channel"] == channel, message
    assert isinstance(message["seq"], int) and message["seq"] >= 0, message
    return message["data"]


def assert_no_leaked_tasks() -> None:
    current = asyncio.current_task()
    leaked = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    assert leaked == [], leaked


# --------------------------------------------------------------------------------------
# Telemetry endpoint: snapshots, ordering, schema conformance
# --------------------------------------------------------------------------------------


def test_telemetry_snapshot_then_delta_ordering(seeded_app) -> None:
    app = seeded_app  # WS telemetry tests stream from a seeded simulation

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            radio_snap = await ws.receive_json()
            link_snap = await ws.receive_json()
            map_snap = await ws.receive_json()
            assert assert_envelope(radio_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_RADIO)
            assert assert_envelope(link_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_LINK)
            assert assert_envelope(map_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_MAP)
            assert [radio_snap["seq"], link_snap["seq"], map_snap["seq"]] == [0, 1, 2]

            response = await asgi_request(
                app,
                "POST",
                "/radios",
                json={**VALID_RADIO_BODY, "simulation_id": "sim_0001"},
            )
            assert response.status == 201, response.text

            radio_delta = await ws.receive_json()
            map_delta = await ws.receive_json()
            assert assert_envelope(radio_delta, kind=KIND_DELTA, channel=CHANNEL_RADIO)
            assert assert_envelope(map_delta, kind=KIND_DELTA, channel=CHANNEL_MAP)
            assert radio_delta["seq"] == 3
            assert map_delta["seq"] == 4
            assert radio_delta["data"]["id"] == "rdr_0005"
            assert radio_delta["data"]["position"] == {"lat": 48.85, "lon": 2.35, "alt_m": 30.0}
        assert_no_leaked_tasks()

    asyncio.run(main())


def test_telemetry_snapshot_content_and_frozen_link_schema(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            radio_snap = await ws.receive_json()
            link_snap = await ws.receive_json()
            map_snap = await ws.receive_json()

            radios = assert_envelope(radio_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_RADIO)
            links = assert_envelope(link_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_LINK)
            positions = assert_envelope(map_snap, kind=KIND_SNAPSHOT, channel=CHANNEL_MAP)

            assert [radio["id"] for radio in radios["radios"]] == ["rdr_0001", "rdr_0002"]
            jsonschema.validate(radio_snap["data"], WS_DATA_SCHEMAS[(KIND_SNAPSHOT, CHANNEL_RADIO)])

            # Every link event validates against the FROZEN contract file.
            assert len(links["links"]) == 1
            jsonschema.validate(links["links"][0], FROZEN_LINK_SCHEMA)
            assert set(links["links"][0].keys()) == set(FROZEN_LINK_SCHEMA["required"])

            assert len(positions["positions"]) == 2
            jsonschema.validate(map_snap["data"], WS_DATA_SCHEMAS[(KIND_SNAPSHOT, CHANNEL_MAP)])
            assert {entry["id"] for entry in positions["positions"]} == {
                "rdr_0001",
                "rdr_0002",
            }

    asyncio.run(main())


def test_unknown_simulation_closed_4404_before_subscribe(app) -> None:
    async def main() -> None:
        async with ws_connect(app, "/ws/simulations/sim_9999/telemetry") as ws:
            assert ws.accepted
            close = await ws.receive()
            assert close["type"] == "websocket.close"
            assert close.get("code") == CLOSE_UNKNOWN_SIMULATION
        # No subscription was ever created for the unknown id.
        assert app.state.bus.subscription_count() == 0
        assert app.state.ws_connections == set()
        assert_no_leaked_tasks()

    asyncio.run(main())


def test_published_link_delta_validates_against_frozen_schema(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            for _ in range(3):  # drain snapshots
                await ws.receive_json()
            app.state.bus.publish(
                telemetry_topic("sim_0001"),
                {"channel": CHANNEL_LINK, "data": dict(LINK_EVENT_INSTANCE)},
            )
            delta = await ws.receive_json()
            data = assert_envelope(delta, kind=KIND_DELTA, channel=CHANNEL_LINK)
            jsonschema.validate(data, FROZEN_LINK_SCHEMA)  # frozen contract
            assert data == LINK_EVENT_INSTANCE

    asyncio.run(main())


def test_radio_and_map_deltas_validate_against_declared_schemas(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            for _ in range(3):
                await ws.receive_json()
            response = await asgi_request(
                app,
                "POST",
                "/radios",
                json={**VALID_RADIO_BODY, "simulation_id": "sim_0001"},
            )
            assert response.status == 201, response.text
            radio_delta = await ws.receive_json()
            map_delta = await ws.receive_json()
            jsonschema.validate(radio_delta["data"], WS_DATA_SCHEMAS[(KIND_DELTA, CHANNEL_RADIO)])
            jsonschema.validate(map_delta["data"], WS_DATA_SCHEMAS[(KIND_DELTA, CHANNEL_MAP)])
            assert radio_delta["data"]["id"] == map_delta["data"]["id"] == "rdr_0005"

    asyncio.run(main())


def test_disconnect_unsubscribes_and_records_stats(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        topic = telemetry_topic("sim_0001")
        assert app.state.bus.subscriptions_on(topic) == 0
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            for _ in range(3):
                await ws.receive_json()
            assert app.state.bus.subscription_count() == 1
            assert len(app.state.ws_connections) == 1
        assert app.state.bus.subscription_count() == 0
        assert app.state.ws_connections == set()
        assert len(app.state.ws_history) == 1
        stats = app.state.ws_history[-1]
        assert stats.topic == topic
        assert stats.sent == 3
        assert stats.snapshots == 3
        assert stats.dropped == 0
        assert_no_leaked_tasks()

    asyncio.run(main())


def test_two_concurrent_clients_receive_identical_deltas(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as first:
            async with ws_connect(app, SEEDED_TELEMETRY_PATH) as second:
                for _ in range(3):
                    await first.receive_json()
                for _ in range(3):
                    await second.receive_json()
                app.state.bus.publish(
                    telemetry_topic("sim_0001"),
                    {"channel": CHANNEL_RADIO, "data": dict(LINK_EVENT_INSTANCE)},
                )
                delta_a = await first.receive_json()
                delta_b = await second.receive_json()
                assert delta_a["data"] == delta_b["data"]
                # Independent seq spaces, each continuing after its own snapshot.
                assert delta_a["seq"] == 3
                assert delta_b["seq"] == 3
            assert app.state.bus.subscription_count() == 1  # only the outer client left
        assert app.state.bus.subscription_count() == 0
        assert len(app.state.ws_history) == 2

    asyncio.run(main())


def test_disconnect_with_queued_messages_cleans_up(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            for _ in range(3):
                await ws.receive_json()
            for index in range(20):  # queue a burst, then leave immediately
                app.state.bus.publish(
                    telemetry_topic("sim_0001"),
                    {
                        "channel": CHANNEL_RADIO,
                        "data": {**VALID_RADIO_BURST_ITEM, "id": f"rdr_b{index:03d}"},
                    },
                )
        # Leaving the context must finish cleanly whatever was still queued.
        assert app.state.bus.subscription_count() == 0
        assert app.state.ws_connections == set()
        assert app.state.ws_history[-1].dropped <= 20
        assert_no_leaked_tasks()

    asyncio.run(main())


VALID_RADIO_BURST_ITEM: dict[str, Any] = {
    "simulation_id": "sim_0001",
    "frequency": {"center_hz": 1.0, "bandwidth_hz": 1.0},
    "transmitter": {"power_watt": 1.0},
    "receiver": {"sensitivity_dBm": -1.0, "noise_figure_dB": 1.0},
    "antenna": {"antenna_type": "omni", "gain_dBi": 1.0, "height_m": 1.0},
    "position": {"lat": 1.0, "lon": 1.0},
}


def test_messages_after_close_are_ignored(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        topic = telemetry_topic("sim_0001")
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            for _ in range(3):
                await ws.receive_json()
        sent_before = app.state.ws_history[-1].sent
        for _ in range(5):  # after close: no handler remains, nothing raises
            app.state.bus.publish(
                topic, {"channel": CHANNEL_RADIO, "data": dict(LINK_EVENT_INSTANCE)}
            )
        assert app.state.bus.subscription_count() == 0
        assert app.state.bus.handler_errors == []
        assert app.state.ws_history[-1].sent == sent_before
        assert app.state.ws_history[-1].dropped == 0

    asyncio.run(main())


# --------------------------------------------------------------------------------------
# /spectrum
# --------------------------------------------------------------------------------------


def test_spectrum_accepts_without_validation_and_streams(app) -> None:
    async def main() -> None:
        # No {id}, no query params — nothing is validated by design.
        async with ws_connect(app, "/spectrum") as ws:
            snapshot = await ws.receive_json()
            data = assert_envelope(snapshot, kind=KIND_SNAPSHOT, channel=CHANNEL_SPECTRUM)
            assert data == {"occupancy": []}  # no frame published yet
            assert snapshot["seq"] == 0

            app.state.bus.publish(
                SPECTRUM_TOPIC,
                {
                    "channel": CHANNEL_SPECTRUM,
                    "data": {"t_s": 1.5, "occupancy": [0.1, 0.7, 0.2]},
                },
            )
            delta = await ws.receive_json()
            delta_data = assert_envelope(delta, kind=KIND_DELTA, channel=CHANNEL_SPECTRUM)
            assert delta["seq"] == 1
            jsonschema.validate(delta_data, WS_DATA_SCHEMAS[(KIND_DELTA, CHANNEL_SPECTRUM)])
            assert delta_data == {"t_s": 1.5, "occupancy": [0.1, 0.7, 0.2]}
        assert app.state.bus.subscription_count() == 0

    asyncio.run(main())


def test_spectrum_snapshot_captures_last_published_frame(app) -> None:
    async def main() -> None:
        frame = {"t_s": 9.75, "occupancy": [0.5, 0.5, 0.9, 0.0]}
        app.state.bus.publish(SPECTRUM_TOPIC, {"channel": CHANNEL_SPECTRUM, "data": frame})
        async with ws_connect(app, "/spectrum") as ws:
            snapshot = await ws.receive_json()
            assert snapshot["kind"] == KIND_SNAPSHOT
            assert snapshot["data"] == frame  # current occupancy frame

    asyncio.run(main())


# --------------------------------------------------------------------------------------
# Backpressure (direct connection-unit tests)
# --------------------------------------------------------------------------------------


def test_backpressure_drops_oldest_and_counts(app) -> None:
    async def main() -> None:
        connection = WsConnection(topic="direct")
        connection.unfreeze()
        for index in range(QUEUE_MAXSIZE + 44):
            connection.enqueue_delta({"channel": CHANNEL_RADIO, "data": {"seq_hint": index}})
        assert connection.queue.qsize() == QUEUE_MAXSIZE
        assert connection.stats.dropped == 44
        assert connection.stats.peak_queued == QUEUE_MAXSIZE
        # The oldest were dropped: the head of the queue is message #44.
        head = connection.queue.get_nowait()
        assert head["seq"] == 44
        assert head["data"]["seq_hint"] == 44

    asyncio.run(main())


def test_publisher_never_blocks_when_client_is_slow(app) -> None:
    async def main() -> None:
        topic = "slow-client-topic"
        connection = WsConnection(topic=topic)
        connection.unfreeze()
        handler = connection.make_handler()  # loop-bound, as stream_events does
        bus = InMemoryEventBus()
        bus.subscribe(topic, handler)

        # Fill the queue — the consumer (pump) is paused: it never runs here.
        for index in range(QUEUE_MAXSIZE + 44):
            connection.enqueue_delta({"channel": CHANNEL_RADIO, "data": {"n": index}})
        assert connection.stats.dropped == 44

        def publisher() -> None:
            for index in range(10):
                bus.publish(topic, {"channel": CHANNEL_RADIO, "data": {"n": index}})

        thread = threading.Thread(target=publisher)
        started = time.perf_counter()
        thread.start()
        thread.join(timeout=2.0)
        elapsed = time.perf_counter() - started
        assert not thread.is_alive(), "publisher blocked on a full client queue"
        assert elapsed < 1.0, f"publisher took {elapsed:.3f}s"

        # The queued callbacks run on the loop: ten more oldest-drops.
        await asyncio.sleep(0.05)
        assert connection.stats.dropped == 44 + 10
        assert connection.queue.qsize() == QUEUE_MAXSIZE
        assert bus.handler_errors == []  # contract: no errors surfaced

    asyncio.run(main())


# --------------------------------------------------------------------------------------
# Stress:1000 connect/publish/disconnect cycles
# --------------------------------------------------------------------------------------


def test_stress_1000_connect_publish_disconnect_cycles(seeded_app) -> None:
    app = seeded_app

    async def main() -> None:
        topic = telemetry_topic("sim_0001")
        for cycle in range(1000):
            async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
                for _ in range(3):
                    snapshot = await ws.receive_json()
                    assert snapshot["kind"] == KIND_SNAPSHOT
                app.state.bus.publish(
                    topic,
                    {"channel": CHANNEL_RADIO, "data": {"cycle": cycle}},
                )
                delta = await ws.receive_json()
                assert delta["kind"] == KIND_DELTA
                assert delta["data"] == {"cycle": cycle}
                assert app.state.bus.subscription_count() == 1
            assert app.state.bus.subscription_count() == 0, cycle
        assert len(app.state.ws_history) == 1000
        assert sum(stats.sent for stats in app.state.ws_history) == 4000
        assert app.state.ws_connections == set()
        assert_no_leaked_tasks()

    asyncio.run(main())


def test_json_string_round_trip_of_envelope(seeded_app) -> None:
    """The envelope must survive a JSON text frame exactly (WS text frames)."""

    app = seeded_app

    async def main() -> None:
        async with ws_connect(app, SEEDED_TELEMETRY_PATH) as ws:
            message = await ws.receive(timeout=5.0)
            assert message["type"] == "websocket.send"
            reparsed = jsonlib.loads(message["text"])
            assert reparsed == {
                "kind": KIND_SNAPSHOT,
                "channel": CHANNEL_RADIO,
                "seq": 0,
                "data": reparsed["data"],
            }

    asyncio.run(main())
