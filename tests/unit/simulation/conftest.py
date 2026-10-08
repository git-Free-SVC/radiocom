"""Shared fixtures/stubs for services/simulation unit tests. Deliberately
minimal — these stubs exist only to satisfy SimulationEntity/
SimulationScenario structurally; no RF/domain knowledge needed (§2 of the
Agent A task prompt: this package works against the Protocols only)."""

from __future__ import annotations


class StubScenario:
    def __init__(self, name: str, seed: int, entities: list) -> None:
        self.name = name
        self.seed = seed
        self.entities = entities


class RngEntity:
    """Correct pattern for reset()-safe randomness: pull the RNG from the
    engine each tick via rng_for(), never cache a private random.Random
    (see engine.py's documented limitation on why a cached RNG breaks
    reset())."""

    def __init__(self, entity_id: str, engine) -> None:
        self.entity_id = entity_id
        self._engine = engine
        self.draws: list[float] = []

    def on_tick(self, t_s: float) -> None:
        self.draws.append(self._engine.rng_for(self.entity_id).random())


class CountingEntity:
    """Records every tick time it's called at; optionally calls
    engine.pause() when it observes a given simulated time, to test that
    pause() invoked from inside on_tick takes effect correctly."""

    def __init__(self, entity_id: str, pause_at: float | None = None, engine=None) -> None:
        self.entity_id = entity_id
        self.ticks: list[float] = []
        self._pause_at = pause_at
        self._engine = engine

    def on_tick(self, t_s: float) -> None:
        self.ticks.append(t_s)
        if self._pause_at == t_s:
            self._engine.pause()
