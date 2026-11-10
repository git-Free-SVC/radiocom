"""Port contracts (task prompt §4/§9): every mock is parametrized against its
Protocol, the frozen EventBus behavioural contract from
libraries/plugin_sdk/event_bus.py is exercised, the frozen SimulationEngine
lifecycle docstring is implemented literally, and the API-port behaviours the
routes depend on are pinned."""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

import pytest

from libraries.domain.position import GeoPosition
from libraries.plugin_sdk.event_bus import EventBus
from libraries.plugin_sdk.geodata import GeodataProvider, GeoJSONFile
from libraries.plugin_sdk.simulation import SimulationEngine
from services.api.errors import ApiError
from services.api.mocks import (
    FakeClock,
    InMemoryEventBus,
    InMemoryScenarioStore,
    InMemorySimulationRegistry,
    MockGeodataProvider,
    MockSimulationEngine,
)
from services.api.ports import (
    ClockPort,
    CorePort,
    GeodataPort,
    ScenarioPort,
    SimulationRegistryPort,
)

VALID_RADIO_BODY = {
    "simulation_id": "sim_0001",
    "frequency": {"center_hz": 433_000_000.0, "bandwidth_hz": 12_500.0},
    "transmitter": {"power_watt": 2.0, "cable_loss_db": 1.0},
    "receiver": {"sensitivity_dBm": -110.0, "noise_figure_dB": 7.0},
    "antenna": {"antenna_type": "omni", "gain_dBi": 3.0, "height_m": 10.0},
    "position": {"lat": 48.85, "lon": 2.35, "alt_m": 35.0},
}


def _registry() -> InMemorySimulationRegistry:
    return InMemorySimulationRegistry(bus=InMemoryEventBus())


PARAMETRIZED_IMPLEMENTATIONS: list[tuple[str, type, Any]] = [
    ("scenario", ScenarioPort, InMemoryScenarioStore),
    ("clock", ClockPort, FakeClock),
    ("geodata-port", GeodataPort, MockGeodataProvider),
    ("geodata-frozen", GeodataProvider, MockGeodataProvider),
    ("event-bus", EventBus, InMemoryEventBus),
    ("registry", SimulationRegistryPort, _registry),
    ("core", CorePort, _registry),
    ("engine", SimulationEngine, MockSimulationEngine),
]


@pytest.mark.parametrize(
    ("label", "protocol", "factory"),
    PARAMETRIZED_IMPLEMENTATIONS,
    ids=[entry[0] for entry in PARAMETRIZED_IMPLEMENTATIONS],
)
def test_mock_satisfies_its_protocol(label: str, protocol: type, factory: Any) -> None:
    instance = factory()
    assert isinstance(instance, protocol), f"{label} does not satisfy {protocol}"


# --------------------------------------------------------------------------------------
# ScenarioPort
# --------------------------------------------------------------------------------------


def test_scenario_port_behaviours() -> None:
    store = InMemoryScenarioStore(clock=FakeClock())
    assert store.list_scenarios() == []
    assert store.get_scenario("scn_0001") is None

    record = store.create_scenario({"scenario": {"name": "unit", "nodes": []}})
    assert record["id"] == "scn_0001"
    assert record["created_at"] == "2026-01-01T00:00:00Z"
    assert store.get_scenario("scn_0001") == record
    assert store.get_scenario("nope") is None
    assert store.list_scenarios() == [{"id": "scn_0001", "name": "unit"}]

    seeded = InMemoryScenarioStore(clock=FakeClock())
    seeded.seed_default_scenarios()
    assert [entry["id"] for entry in seeded.seed_records()] == ["scn_0001", "scn_0002"]


# --------------------------------------------------------------------------------------
# ClockPort
# --------------------------------------------------------------------------------------


def test_clock_port_is_injected_and_deterministic() -> None:
    first, second = FakeClock(), FakeClock()
    sequence_a = [first.now() for _ in range(3)]
    sequence_b = [second.now() for _ in range(3)]
    assert sequence_a == sequence_b
    assert sequence_a[1] - sequence_a[0] == timedelta(seconds=1)
    assert sequence_a[0].isoformat() == "2026-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------------------
# EventBus (frozen behavioural contract, verbatim from plugin_sdk docstring)
# --------------------------------------------------------------------------------------


def test_event_bus_handlers_run_in_subscription_order_on_publisher_thread() -> None:
    bus = InMemoryEventBus()
    order: list[str] = []
    threads: list[int] = []
    bus.subscribe("t", lambda _p: order.append("first"))
    bus.subscribe(
        "t",
        lambda _p: (order.append("second"), threads.append(threading.get_ident())),
    )
    bus.publish("t", {"x": 1})
    assert order == ["first", "second"]
    assert threads == [threading.get_ident()]


def test_event_bus_handler_errors_never_propagate_and_do_not_stop_delivery() -> None:
    bus = InMemoryEventBus()

    def boom(_payload: dict) -> None:
        raise RuntimeError("handler boom")

    delivered: list[dict] = []
    bus.subscribe("t", boom)
    bus.subscribe("t", delivered.append)
    bus.publish("t", {"v": 1})  # must neither raise nor stop delivery
    assert delivered == [{"v": 1}]
    assert len(bus.handler_errors) == 1
    assert isinstance(bus.handler_errors[0], RuntimeError)
    assert bus.subscription_count() == 2  # neither handler was removed


def test_event_bus_double_subscribe_is_idempotent_and_unknown_unsubscribe_noop() -> None:
    bus = InMemoryEventBus()

    def handler(_payload: dict) -> None:
        return None

    bus.subscribe("t", handler)
    bus.subscribe("t", handler)
    assert bus.subscriptions_on("t") == 1

    bus.unsubscribe("t", lambda _p: None)  # unknown -> silent no-op
    assert bus.subscriptions_on("t") == 1
    bus.unsubscribe("t", handler)
    bus.unsubscribe("t", handler)  # already gone -> no-op, no error
    assert bus.subscription_count() == 0


def test_event_bus_changes_during_publish_affect_later_publishes_only() -> None:
    bus = InMemoryEventBus()
    calls: list[str] = []

    def adder(_payload: dict) -> None:
        calls.append("adder")
        bus.subscribe("t", lambda _q: calls.append("added"))

    bus.subscribe("t", adder)
    bus.publish("t", {})  # the new subscription must NOT run in this publish
    assert calls == ["adder"]
    bus.publish("t", {})  # ...but does in the next one
    assert calls == ["adder", "adder", "added"]


# --------------------------------------------------------------------------------------
# SimulationEngine (frozen lifecycle docstring implemented literally)
# --------------------------------------------------------------------------------------


def test_engine_lifecycle_matches_frozen_state_machine() -> None:
    engine = MockSimulationEngine()

    # state() before load() -> RuntimeError
    with pytest.raises(RuntimeError, match=r"state\(\) before load"):
        _ = engine.state
    # every transition illegal from "new"
    for illegal in (engine.start, engine.pause, engine.resume, engine.reset, engine.step):
        with pytest.raises(RuntimeError):
            illegal()

    engine.load({"name": "x"})
    assert engine.status == "LOADED"
    with pytest.raises(RuntimeError):  # reload illegal
        engine.load({})
    with pytest.raises(RuntimeError):  # pause needs RUNNING
        engine.pause()

    engine.start()
    assert engine.status == "RUNNING"
    with pytest.raises(RuntimeError):  # start needs LOADED
        engine.start()
    with pytest.raises(RuntimeError):  # resume needs PAUSED
        engine.resume()

    engine.step(5.0)
    assert engine.sim_time_s == 5.0
    with pytest.raises(ValueError):  # backwards in time is a domain ValueError
        engine.step(1.0)

    engine.pause()
    assert engine.status == "PAUSED"
    engine.resume()
    assert engine.status == "RUNNING"
    engine.reset()  # legal from any state except "new"
    assert engine.status == "LOADED"
    assert engine.sim_time_s == 0.0

    state = engine.state
    assert state.clock.now_s == 0.0
    assert state.checkpoint() == b"agent-e-mock-checkpoint"


def test_engine_call_log_records_exactly_one_entry_per_attempt() -> None:
    engine = MockSimulationEngine()
    attempts = 0
    with pytest.raises(RuntimeError):  # illegal in state "new"
        engine.start()
    attempts += 1
    engine.load(None)
    attempts += 1
    with pytest.raises(RuntimeError):  # reload illegal
        engine.load(None)
    attempts += 1
    engine.start()
    attempts += 1

    assert engine.calls == ["start", "load", "load", "start"]
    assert len(engine.calls) == attempts


# --------------------------------------------------------------------------------------
# SimulationRegistryPort + CorePort
# --------------------------------------------------------------------------------------


def test_registry_port_behaviours() -> None:
    registry = _registry()
    assert registry.create("scn_0001") == "sim_0001"
    assert registry.exists("sim_0001")
    assert not registry.exists("sim_9999")
    assert registry.get("sim_9999") is None
    assert isinstance(registry.get("sim_0001"), SimulationEngine)
    assert registry.status("sim_0001") == "new"  # before load
    assert registry.scenario_id("sim_0001") == "scn_0001"

    with pytest.raises(ApiError) as missing_status:
        registry.status("sim_9999")
    assert missing_status.value.status_code == 404
    with pytest.raises(ApiError) as missing_scenario:
        registry.scenario_id("sim_9999")
    assert missing_scenario.value.status_code == 404


def test_core_port_behaviours() -> None:
    registry = _registry()
    registry.create("scn_0001")

    with pytest.raises(ApiError) as unknown_sim:
        registry.add_radio("sim_9999", dict(VALID_RADIO_BODY))
    assert unknown_sim.value.status_code == 404

    first = registry.add_radio("sim_0001", dict(VALID_RADIO_BODY))
    assert first["id"] == "rdr_0001"
    assert registry.radios("sim_0001") == [first]
    assert registry.radios("sim_9999") == []
    assert registry.get_link("rdr_0001", "rdr_0002") is None
    assert registry.update_radio("rdr_9999", {"position": {"lat": 1.0, "lon": 1.0}}) is None

    second = registry.add_radio("sim_0001", dict(VALID_RADIO_BODY))
    link = registry.get_link(first["id"], second["id"])
    assert link is not None
    assert link["snr_db"] == 12.5 and link["margin_db"] == 6.0
    assert link["quality"] == "up" and link["time_s"] == 0.0
    assert registry.links("sim_0001") == [link]

    patched = registry.update_radio(first["id"], {"position": {"lat": 49.0, "lon": 3.0}})
    assert patched is not None
    assert patched["position"] == {"lat": 49.0, "lon": 3.0, "alt_m": 0.0}
    assert patched["frequency"] == first["frequency"]


# --------------------------------------------------------------------------------------
# GeodataPort (frozen GeodataProvider + list_layers)
# --------------------------------------------------------------------------------------


def test_geodata_port_behaviours() -> None:
    geodata = MockGeodataProvider()
    assert [layer.name for layer in geodata.list_layers()] == [
        "base_terrain",
        "admin_boundaries",
    ]

    raster = geodata.publish_raster("dem", "s3://bucket/dem.tif", "EPSG:3857")
    vector = geodata.publish_vector("roads", GeoJSONFile(path="roads.geojson"))
    assert raster.kind == "raster" and vector.kind == "vector"
    assert len(geodata.list_layers()) == 4

    start = GeoPosition(lat=48.0, lon=2.0, alt_m=100.0)
    end = GeoPosition(lat=49.0, lon=3.0, alt_m=200.0)
    elevation = geodata.elevation_at(start)
    assert isinstance(elevation, float) and elevation == round(elevation, 3)

    profile = geodata.elevation_profile(start, end, 4)
    assert len(profile) == 4  # exactly `samples` points
    assert profile[0] == pytest.approx(elevation, abs=1e-9)  # starts at elevation_at(a)
    with pytest.raises(ValueError, match="samples must be >= 2"):
        geodata.elevation_profile(start, end, 1)

    geodata.set_style(raster, "<sld/>")
    assert geodata.styles["dem"] == "<sld/>"
    assert geodata.features_in(raster, None) == []
    assert geodata.tile_url(raster, style="dark").endswith("style=dark")
    assert "dem" in geodata.tile_url(raster)
