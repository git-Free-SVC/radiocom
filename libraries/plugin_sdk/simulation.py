"""Simulation Core interfaces. Frozen after Wave 0 — see docs/adr/ADR-000.
Real implementation: services/simulation (§14). This is the hybrid
discrete-event + fixed-tick engine: SimulationEvent for DES, plus a
periodic MOBILITY_TICK event for continuous motion/link re-evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class SimulationClock(Protocol):
    """Owns simulated time and its relation to wall-clock time."""

    @property
    def now_s(self) -> float:
        """Current simulation time, seconds since scenario start."""
        ...

    def advance_to(self, t_s: float) -> None: ...

    @property
    def real_time_factor(self) -> float:
        """1.0 = real-time pacing, >1 = accelerated, None-able for unbounded."""
        ...


class EventKind(str, Enum):
    MOBILITY_TICK = "mobility_tick"
    LINK_EVALUATE = "link_evaluate"
    RADIO_STATE_CHANGE = "radio_state_change"
    SCENARIO_CONTROL = "scenario_control"  # pause/resume/reset


@dataclass(order=True, slots=True)
class SimulationEvent:
    time_s: float
    seq: int  # tie-breaker for deterministic ordering at equal time_s
    kind: EventKind = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)


@runtime_checkable
class SimulationEntity(Protocol):
    """Anything with identity and lifecycle in the sim (a Radio, a jammer...)."""

    entity_id: str

    def on_tick(self, t_s: float) -> None: ...


class SimulationState(Protocol):
    """Snapshot of all entities + clock + RNG state, sufficient to checkpoint
    and resume deterministically (§14, §24 determinism gate)."""

    clock: SimulationClock
    entities: dict[str, SimulationEntity]
    rng_state: bytes

    def checkpoint(self) -> bytes: ...

    @classmethod
    def restore(cls, blob: bytes) -> "SimulationState": ...


class SimulationScenario(Protocol):
    """Validated, loaded scenario ready to run (post scenario-engine parsing)."""

    name: str
    seed: int
    entities: list[SimulationEntity]


class SimulationScheduler(ABC):
    """Priority-queue event scheduler. Concrete impl in services/simulation."""

    @abstractmethod
    def schedule(self, event: SimulationEvent) -> None: ...

    @abstractmethod
    def pop_next(self) -> SimulationEvent | None: ...

    @abstractmethod
    def peek_time(self) -> float | None: ...


class SimulationEngine(ABC):
    """Top-level orchestrator. Owns clock + scheduler + state, drives the
    run loop, and is the only thing the API (§17) talks to for control."""

    @abstractmethod
    def load(self, scenario: SimulationScenario) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def step(self, max_time_s: float | None = None) -> None:
        """Run until max_time_s or the event queue is drained."""
        ...

    @property
    @abstractmethod
    def state(self) -> SimulationState: ...
