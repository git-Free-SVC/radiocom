"""Reference SimulationEngine/Scheduler/State/Clock. Pre-seeds one MOBILITY_TICK
per second up to `horizon_s`, so step(None) drains and terminates."""

from __future__ import annotations

import heapq
import json
import pickle
import random

from libraries.plugin_sdk.simulation import (
    EventKind,
    SimulationEngine,
    SimulationEntity,
    SimulationEvent,
    SimulationScenario,
    SimulationScheduler,
    SimulationState,
)


class HeapScheduler(SimulationScheduler):
    def __init__(self) -> None:
        self._heap: list[SimulationEvent] = []

    def schedule(self, event: SimulationEvent) -> None:
        heapq.heappush(self._heap, event)

    def pop_next(self) -> SimulationEvent | None:
        return heapq.heappop(self._heap) if self._heap else None

    def peek_time(self) -> float | None:
        return self._heap[0].time_s if self._heap else None


class SimpleClock:
    def __init__(self) -> None:
        self._now = 0.0

    @property
    def now_s(self) -> float:
        return self._now

    def advance_to(self, t_s: float) -> None:
        if t_s < self._now:
            raise ValueError("clock cannot go backwards")
        self._now = t_s

    @property
    def real_time_factor(self) -> float | None:
        return None  # unbounded


class SimpleState:
    def __init__(
        self, clock: SimpleClock, entities: dict[str, SimulationEntity], rng: random.Random
    ):
        self.clock, self.entities, self._rng = clock, entities, rng

    @property
    def rng_state(self) -> bytes:
        return pickle.dumps(self._rng.getstate())

    def checkpoint(self) -> bytes:
        return json.dumps(
            {"now_s": self.clock.now_s, "rng": self.rng_state.hex()}, sort_keys=True
        ).encode()

    @classmethod
    def restore(cls, blob: bytes) -> "SimpleState":
        d = json.loads(blob)
        clock = SimpleClock()
        clock.advance_to(d["now_s"])
        rng = random.Random()
        rng.setstate(pickle.loads(bytes.fromhex(d["rng"])))
        return cls(clock, {}, rng)


class SimpleEngine(SimulationEngine):
    horizon_s = 60

    def __init__(self) -> None:
        self._status = "new"
        self._scenario: SimulationScenario | None = None

    def _init_run(self) -> None:
        sc = self._scenario
        self._sched = HeapScheduler()
        self._rng = random.Random(sc.seed)
        self._state = SimpleState(SimpleClock(), {e.entity_id: e for e in sc.entities}, self._rng)
        for i in range(1, self.horizon_s + 1):
            self._sched.schedule(SimulationEvent(float(i), i, EventKind.MOBILITY_TICK))

    def _require(self, *allowed: str) -> None:
        if self._status not in allowed:
            raise RuntimeError(f"illegal in state {self._status!r}")

    def load(self, scenario: SimulationScenario) -> None:
        self._scenario = scenario
        self._init_run()
        self._status = "loaded"

    def start(self) -> None:
        self._require("loaded")
        self._status = "running"

    def pause(self) -> None:
        self._require("running")
        self._status = "paused"

    def resume(self) -> None:
        self._require("paused")
        self._status = "running"

    def reset(self) -> None:
        self._require("loaded", "running", "paused")
        self._init_run()
        self._status = "loaded"

    def step(self, max_time_s: float | None = None) -> None:
        self._require("running")
        clock = self._state.clock
        if max_time_s is not None and max_time_s < clock.now_s:
            raise ValueError("max_time_s is in the past")
        while (t := self._sched.peek_time()) is not None and (
            max_time_s is None or t <= max_time_s
        ):
            ev = self._sched.pop_next()
            clock.advance_to(ev.time_s)
            if ev.kind is EventKind.MOBILITY_TICK:
                for ent in self._state.entities.values():
                    ent.on_tick(ev.time_s)
                self._rng.random()  # make RNG state evolve -> non-trivial determinism
        if max_time_s is not None:
            clock.advance_to(max_time_s)

    @property
    def state(self) -> SimulationState:
        self._require("loaded", "running", "paused")
        return self._state
