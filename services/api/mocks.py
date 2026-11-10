"""Deterministic in-memory doubles for every port (Wave-1 mocks).

Rules enforced here and asserted by tests/unit/api/test_determinism.py:
  * counter ids — scn_0001 / sim_0001 / rdr_0001 (zero padded);
  * injected ClockPort with a fixed origin (2026-01-01T00:00:00Z, +1 s/call) —
    no uuid, no random, no wall clock anywhere in services/api;
  * every counter and mutable store is guarded by a threading.Lock because
    control routes run concurrently in FastAPI's threadpool;
  * the engine call log records one entry per request ("sim_0001:start"),
    so "called exactly once" is directly assertable — and, under parallel
    requests, "exactly N entries, no double calls".

Fixture data (task prompt §4): InMemoryScenarioStore.seed_default_scenarios()
plus InMemorySimulationRegistry seeded from the store's records produce two
scenarios, two radios per scenario, and one link per simulation with the
known values snr_db=12.5, margin_db=6.0, quality="up", time_s=0.0.
create_app() with default ports applies all of it automatically.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.domain.rf_results import LinkQuality, LinkState
from libraries.plugin_sdk.event_bus import Handler
from libraries.plugin_sdk.geodata import Feature, GeoJSONFile, LayerRef, PostGISTable
from libraries.plugin_sdk.simulation import SimulationEngine, SimulationState
from services.api.errors import ApiError
from services.api.serialization import (
    datetime_to_iso,
    link_to_payload,
    position_payload,
    radio_to_payload,
)
from services.api.ws_contract import CHANNEL_LINK, CHANNEL_MAP, CHANNEL_RADIO, telemetry_topic

FAKE_CLOCK_ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)

# Known link fixture values (README.txt records them as contract-visible).
SEED_LINK_SNR_DB = 12.5
SEED_LINK_MARGIN_DB = 6.0
SEED_LINK_QUALITY = "up"
SEED_LINK_TIME_S = 0.0

SEED_SCENARIO_NAMES = ("city-centre", "harbour")

# Two radios per seeded simulation (validated against the radio schemas).
SEED_RADIO_BODIES: tuple[dict[str, Any], ...] = (
    {
        "frequency": {"center_hz": 433_000_000.0, "bandwidth_hz": 12_500.0},
        "transmitter": {"power_watt": 2.0, "cable_loss_db": 1.5},
        "receiver": {"sensitivity_dBm": -110.0, "noise_figure_dB": 7.0},
        "antenna": {
            "antenna_type": "omni",
            "gain_dBi": 3.0,
            "height_m": 10.0,
            "polarization": "vertical",
        },
        "position": {"lat": 48.8566, "lon": 2.3522, "alt_m": 35.0},
    },
    {
        "frequency": {"center_hz": 868_000_000.0, "bandwidth_hz": 200_000.0},
        "transmitter": {"power_watt": 1.0, "cable_loss_db": 0.5},
        "receiver": {"sensitivity_dBm": -107.0, "noise_figure_dB": 6.0},
        "antenna": {
            "antenna_type": "omni",
            "gain_dBi": 2.0,
            "height_m": 15.0,
            "polarization": "vertical",
        },
        "position": {"lat": 48.86, "lon": 2.36, "alt_m": 42.0},
    },
)


class FakeClock:
    """ClockPort: fixed origin, +1 s per now() call, lock-guarded."""

    def __init__(self, *, origin: datetime = FAKE_CLOCK_ORIGIN, step_s: float = 1.0) -> None:
        self._now = origin
        self._step = timedelta(seconds=step_s)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            current = self._now
            self._now = current + self._step
            return current


class InMemoryEventBus:
    """Frozen EventBus contract (libraries/plugin_sdk/event_bus.py docstring):
    synchronous handlers in subscription order on the publisher's thread, a
    raising handler never affects the publisher or other handlers, double
    subscribe is idempotent, unknown unsubscribe is a no-op, and
    subscribe/unsubscribe during publish only affect later publishes.

    API-local extras: subscription_count() (leak assertions) and
    last_payload() (the /spectrum snapshot source)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[str, list[Handler]] = {}
        self._last_payloads: dict[str, dict[str, Any]] = {}
        self.handler_errors: list[Exception] = []

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            handlers = list(self._subscriptions.get(topic, ()))  # snapshot: later
            self._last_payloads[topic] = payload  # changes affect later publishes only
        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001 - frozen EventBus contract: never propagate
                self.handler_errors.append(exc)

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._subscriptions.setdefault(topic, [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._subscriptions.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)
            if not handlers:
                self._subscriptions.pop(topic, None)

    # -- API-local introspection ------------------------------------------------
    def subscription_count(self) -> int:
        with self._lock:
            return sum(len(handlers) for handlers in self._subscriptions.values())

    def subscriptions_on(self, topic: str) -> int:
        with self._lock:
            return len(self._subscriptions.get(topic, ()))

    def last_payload(self, topic: str) -> dict[str, Any] | None:
        with self._lock:
            return self._last_payloads.get(topic)


class _MockSimulationClock:
    """Minimal SimulationClock for MockSimulationState (state() is not routed;
    it exists because the frozen SimulationEngine declares it abstract)."""

    def __init__(self, now_s: float) -> None:
        self._now_s = now_s

    @property
    def now_s(self) -> float:
        return self._now_s

    def advance_to(self, t_s: float) -> None:
        self._now_s = t_s

    @property
    def real_time_factor(self) -> float | None:
        return None


class MockSimulationState:
    """SimulationState-shaped snapshot (not part of any routed payload)."""

    def __init__(self, sim_time_s: float) -> None:
        self.clock = _MockSimulationClock(sim_time_s)
        self.entities: dict[str, Any] = {}
        self.rng_state = b"agent-e-mock-seed"

    def checkpoint(self) -> bytes:
        return b"agent-e-mock-checkpoint"

    @classmethod
    def restore(cls, blob: bytes) -> MockSimulationState:
        return cls(0.0)


class MockSimulationEngine(SimulationEngine):
    """The frozen lifecycle, implemented literally (plugin_sdk/simulation.py):
      (new) --load--> LOADED --start--> RUNNING <--pause/resume--> PAUSED
      reset(): any state except new -> LOADED (clock 0)
      step() only in RUNNING; state() before load() raises RuntimeError.
    Illegal transitions raise RuntimeError — the API maps those to 409.

    Every method appends to the call log BEFORE the legality check, so N
    requests always produce exactly N entries (no double-calls) whether they
    succeeded or were rejected. Transitions are lock-guarded because control
    routes run concurrently in FastAPI's threadpool."""

    def __init__(self, *, on_call: Callable[[str], None] | None = None) -> None:
        self.calls: list[str] = []
        self.status = "new"
        self.scenario: Any = None
        self.sim_time_s = 0.0
        self._on_call = on_call
        self._lock = threading.Lock()

    # -- helpers ---------------------------------------------------------------
    def _record(self, method: str) -> None:
        self.calls.append(method)
        if self._on_call is not None:
            self._on_call(method)

    def _require(self, method: str, allowed: str) -> None:
        if self.status != allowed:
            raise RuntimeError(f"{method}() illegal in state {self.status}")

    # -- frozen interface ------------------------------------------------------
    def load(self, scenario: Any) -> None:
        with self._lock:
            self._record("load")
            self._require("load", "new")
            self.scenario = scenario
            self.status = "LOADED"

    def start(self) -> None:
        with self._lock:
            self._record("start")
            self._require("start", "LOADED")
            self.status = "RUNNING"

    def pause(self) -> None:
        with self._lock:
            self._record("pause")
            self._require("pause", "RUNNING")
            self.status = "PAUSED"

    def resume(self) -> None:
        with self._lock:
            self._record("resume")
            self._require("resume", "PAUSED")
            self.status = "RUNNING"

    def reset(self) -> None:
        with self._lock:
            self._record("reset")
            if self.status == "new":
                raise RuntimeError("reset() illegal in state new")
            self.status = "LOADED"
            self.sim_time_s = 0.0

    def step(self, max_time_s: float | None = None) -> None:
        with self._lock:
            self._record("step")
            self._require("step", "RUNNING")
            if max_time_s is not None:
                if max_time_s < self.sim_time_s:
                    raise ValueError(f"max_time_s {max_time_s} is before now {self.sim_time_s}")
                self.sim_time_s = max_time_s

    @property
    def state(self) -> SimulationState:
        with self._lock:
            if self.status == "new":
                raise RuntimeError("state() before load()")
            return MockSimulationState(self.sim_time_s)


def build_radio(radio_id: str, simulation_id: str, body: dict[str, Any]) -> Radio:
    """Construct frozen domain types from a schema-validated body.

    Frequency and GeoPosition validate in their own constructors; their
    ValueError is the API's 422 input path (never a 500). The simulation_id
    argument is validated by the route before this is ever called and is kept
    for symmetry with radio_to_payload."""
    del simulation_id
    frequency_body = body["frequency"]
    frequency = Frequency(
        center_hz=float(frequency_body["center_hz"]),
        bandwidth_hz=float(frequency_body["bandwidth_hz"]),
    )
    transmitter_body = body["transmitter"]
    transmitter = Transmitter(
        power_watt=float(transmitter_body["power_watt"]),
        cable_loss_db=float(transmitter_body.get("cable_loss_db", 0.0)),
    )
    receiver_body = body["receiver"]
    receiver = Receiver(
        sensitivity_dBm=float(receiver_body["sensitivity_dBm"]),
        noise_figure_dB=float(receiver_body["noise_figure_dB"]),
    )
    antenna_body = body["antenna"]
    antenna = Antenna(
        antenna_type=str(antenna_body["antenna_type"]),
        gain_dBi=float(antenna_body["gain_dBi"]),
        height_m=float(antenna_body["height_m"]),
        polarization=str(antenna_body.get("polarization", "vertical")),
        # pattern: default omni — the wire shape cannot carry a callable.
    )
    position_body = body["position"]
    position = GeoPosition(
        lat=float(position_body["lat"]),
        lon=float(position_body["lon"]),
        alt_m=float(position_body.get("alt_m", 0.0)),
    )
    return Radio(
        id=radio_id,
        frequency=frequency,
        transmitter=transmitter,
        receiver=receiver,
        antenna=antenna,
        position=position,
    )


class InMemoryScenarioStore:
    """ScenarioPort: counter ids scn_000N, injected clock for created_at."""

    def __init__(self, *, clock: FakeClock | None = None) -> None:
        self._lock = threading.RLock()
        self._clock = clock if clock is not None else FakeClock()
        self._records: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"scn_{self._counter:04d}"

    def seed_default_scenarios(self) -> list[dict[str, Any]]:
        """Two fixture scenarios (idempotence is the caller's responsibility;
        create_app() calls this exactly once, only for a default store)."""
        with self._lock:
            if self._order:
                return [self._records[key] for key in self._order]
            for name in SEED_SCENARIO_NAMES:
                record = {
                    "id": self._next_id(),
                    "scenario": {
                        "name": name,
                        "seed": 0,
                        "nodes": [
                            {
                                "id": "node_a",
                                "type": "fixed_radio",
                                "position": [48.8566, 2.3522],
                                "radio": "rdr_a",
                            },
                            {
                                "id": "node_b",
                                "type": "mobile_radio",
                                "position": [48.86, 2.36, 15.0],
                                "radio": "rdr_b",
                                "route": "loop_1",
                            },
                        ],
                    },
                    "created_at": datetime_to_iso(self._clock.now()),
                }
                self._records[record["id"]] = record
                self._order.append(record["id"])
            return [self._records[key] for key in self._order]

    # -- ScenarioPort ----------------------------------------------------------
    def list_scenarios(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"id": key, "name": self._records[key]["scenario"]["name"]} for key in self._order
            ]

    def create_scenario(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = {
                "id": self._next_id(),
                "scenario": body["scenario"],
                "created_at": datetime_to_iso(self._clock.now()),
            }
            self._records[record["id"]] = record
            self._order.append(record["id"])
            return record

    def get_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._records.get(scenario_id)

    # -- seeding seam ----------------------------------------------------------
    def seed_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._records[key] for key in self._order]


class InMemorySimulationRegistry:
    """SimulationRegistryPort + CorePort in one object (create_app takes the
    five prompt ports; the registry owns each simulation's engine, its radio
    store and its links, because radios and links belong to a simulation)."""

    def __init__(
        self,
        *,
        bus: InMemoryEventBus,
        scenario_store: InMemoryScenarioStore | None = None,
        clock: FakeClock | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock if clock is not None else FakeClock()
        self._bus = bus
        self._engines: dict[str, MockSimulationEngine] = {}
        self._scenario_ids: dict[str, str] = {}
        self._counter = 0
        self._radio_counter = 0
        self._radios: dict[str, tuple[str, Radio]] = {}
        self._radio_order: dict[str, list[str]] = {}
        self._links: dict[tuple[str, str], dict[str, Any]] = {}
        self._link_order: dict[str, list[tuple[str, str]]] = {}
        # The engine call log: entries are f"{simulation_id}:{method}".
        self.engine_calls: list[str] = []
        if scenario_store is not None:
            self._seed_from(scenario_store)

    # -- seeding (fixture data) ------------------------------------------------
    def _seed_from(self, scenario_store: InMemoryScenarioStore) -> None:
        """Two scenarios -> two simulations, two radios each, one link each."""
        for record in scenario_store.seed_records():
            simulation_id = self.create(record["id"])
            engine = self._engines[simulation_id]
            engine.load(record)  # recorded via on_call as f"{simulation_id}:load"
            for body in SEED_RADIO_BODIES:
                self.add_radio(simulation_id, {**body, "simulation_id": simulation_id})

    # -- SimulationRegistryPort ------------------------------------------------
    def create(self, scenario_id: str) -> str:
        with self._lock:
            self._counter += 1
            simulation_id = f"sim_{self._counter:04d}"

            def on_call(method: str, simulation: str = simulation_id) -> None:
                self.engine_calls.append(f"{simulation}:{method}")

            self._engines[simulation_id] = MockSimulationEngine(on_call=on_call)
            self._scenario_ids[simulation_id] = scenario_id
            self._radio_order[simulation_id] = []
            self._link_order[simulation_id] = []
            return simulation_id

    def get(self, simulation_id: str) -> SimulationEngine | None:
        return self._engines.get(simulation_id)

    def exists(self, simulation_id: str) -> bool:
        return simulation_id in self._engines

    def status(self, simulation_id: str) -> str:
        engine = self._engines.get(simulation_id)
        if engine is None:
            raise ApiError(404, f"simulation {simulation_id} not found")
        return engine.status

    def scenario_id(self, simulation_id: str) -> str:
        scenario_id = self._scenario_ids.get(simulation_id)
        if scenario_id is None:
            raise ApiError(404, f"simulation {simulation_id} not found")
        return scenario_id

    # -- CorePort: radios ------------------------------------------------------
    def add_radio(self, simulation_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if simulation_id not in self._engines:
            raise ApiError(404, f"simulation {simulation_id} not found")
        with self._lock:
            self._radio_counter += 1
            radio_id = f"rdr_{self._radio_counter:04d}"
        radio = build_radio(radio_id, simulation_id, body)  # domain ValueError -> 422
        with self._lock:
            self._radios[radio_id] = (simulation_id, radio)
            self._radio_order.setdefault(simulation_id, []).append(radio_id)
            new_link_key = self._maybe_link(simulation_id)
        payload = radio_to_payload(radio, simulation_id)
        topic = telemetry_topic(simulation_id)
        self._bus.publish(topic, {"channel": CHANNEL_RADIO, "data": payload})
        self._bus.publish(topic, {"channel": CHANNEL_MAP, "data": position_payload(radio)})
        if new_link_key is not None:
            record = self._links[new_link_key]
            self._bus.publish(
                topic,
                {
                    "channel": CHANNEL_LINK,
                    "data": link_to_payload(
                        new_link_key[0], new_link_key[1], record["state"], record["time_s"]
                    ),
                },
            )
        return payload

    def _maybe_link(self, simulation_id: str) -> tuple[str, str] | None:
        """Exactly one deterministic link: created when the simulation reaches
        exactly two radios, between the first and second of them."""
        order = self._radio_order[simulation_id]
        if len(order) != 2:
            return None
        key = (order[0], order[1])
        self._links[key] = {
            "simulation_id": simulation_id,
            "state": LinkState(
                snr_db=SEED_LINK_SNR_DB,
                margin_db=SEED_LINK_MARGIN_DB,
                quality=LinkQuality(SEED_LINK_QUALITY),
            ),
            "time_s": SEED_LINK_TIME_S,
        }
        self._link_order[simulation_id].append(key)
        return key

    def update_radio(self, radio_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        entry = self._radios.get(radio_id)
        if entry is None:
            return None
        simulation_id, current_radio = entry
        current = radio_to_payload(current_radio, simulation_id)
        merged = {
            key: patch[key] if key in patch else current[key]
            for key in ("frequency", "transmitter", "receiver", "antenna", "position")
        }
        # Whole-value replacement per provided key; domain constructors re-run
        # (e.g. a patched frequency of 0 raises ValueError -> 422).
        updated = build_radio(radio_id, simulation_id, merged)
        position_changed = updated.position != current_radio.position
        with self._lock:
            self._radios[radio_id] = (simulation_id, updated)
        payload = radio_to_payload(updated, simulation_id)
        topic = telemetry_topic(simulation_id)
        self._bus.publish(topic, {"channel": CHANNEL_RADIO, "data": payload})
        if position_changed:
            self._bus.publish(topic, {"channel": CHANNEL_MAP, "data": position_payload(updated)})
        return payload

    def radios(self, simulation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            order = list(self._radio_order.get(simulation_id, ()))
        payloads: list[dict[str, Any]] = []
        for radio_id in order:
            entry = self._radios.get(radio_id)
            if entry is not None:
                payloads.append(radio_to_payload(entry[1], entry[0]))
        return payloads

    # -- CorePort: links -------------------------------------------------------
    def get_link(self, a: str, b: str) -> dict[str, Any] | None:
        with self._lock:
            for (tx_id, rx_id), record in self._links.items():
                if {tx_id, rx_id} == {a, b} and a != b:
                    return link_to_payload(tx_id, rx_id, record["state"], record["time_s"])
        return None

    def links(self, simulation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            keys = list(self._link_order.get(simulation_id, ()))
        payloads: list[dict[str, Any]] = []
        for key in keys:
            record = self._links[key]
            payloads.append(link_to_payload(key[0], key[1], record["state"], record["time_s"]))
        return payloads


class MockGeodataProvider:
    """GeodataPort double: deterministic pure-math elevation, no GeoServer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._layers: list[LayerRef] = [
            LayerRef(name="base_terrain", kind="raster"),
            LayerRef(name="admin_boundaries", kind="vector"),
        ]
        self.styles: dict[str, str] = {}

    # -- GeodataPort / GeodataProvider ----------------------------------------
    def list_layers(self) -> list[LayerRef]:
        with self._lock:
            return list(self._layers)

    def publish_raster(self, name: str, path_or_uri: str, srs: str = "EPSG:4326") -> LayerRef:
        del path_or_uri, srs  # Wave-1 mock stores the reference, reads nothing
        layer = LayerRef(name=name, kind="raster")
        with self._lock:
            self._layers.append(layer)
        return layer

    def publish_vector(self, name: str, source: PostGISTable | GeoJSONFile) -> LayerRef:
        del source
        layer = LayerRef(name=name, kind="vector")
        with self._lock:
            self._layers.append(layer)
        return layer

    def set_style(self, layer: LayerRef, sld: str) -> None:
        with self._lock:
            self.styles[layer.name] = sld

    def elevation_at(self, pos: GeoPosition) -> float:
        return round(
            50.0 * math.sin(math.radians(pos.lat))
            + 30.0 * math.cos(math.radians(pos.lon))
            + pos.alt_m,
            3,
        )

    def elevation_profile(self, a: GeoPosition, b: GeoPosition, samples: int) -> list[float]:
        if samples < 2:
            raise ValueError(f"samples must be >= 2, got {samples}")
        start = self.elevation_at(a)
        end = self.elevation_at(b)
        return [round(start + (end - start) * index / (samples - 1), 3) for index in range(samples)]

    def features_in(self, layer: LayerRef, bbox: Any) -> list[Feature]:
        del layer, bbox
        return []

    def tile_url(self, layer: LayerRef, style: str | None = None) -> str:
        suffix = f"?style={style}" if style else ""
        return f"https://tiles.invalid/{layer.name}/{{z}}/{{x}}/{{y}}{suffix}"
