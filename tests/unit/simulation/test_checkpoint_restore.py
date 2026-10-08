"""checkpoint()/restore() round-trips clock + RNG state. Entities are NOT
captured generically (documented limitation in state.py) — restored.entities
is intentionally empty; this test only asserts what's actually guaranteed."""

from __future__ import annotations

from services.simulation import CoreSimulationEngine
from services.simulation.state import InMemorySimulationState
from tests.unit.simulation.conftest import RngEntity, StubScenario


class TestCheckpointRestore:
    def test_round_trips_clock_and_rng_state(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entities = [RngEntity(eid, engine) for eid in ("A", "B")]
        engine.load(StubScenario("c", seed=555, entities=entities))
        engine.start()
        engine.step(max_time_s=2.0)

        blob = engine.state.checkpoint()
        restored = InMemorySimulationState.restore(blob)

        assert restored.clock.now_s == engine.state.clock.now_s
        assert restored.clock.real_time_factor == engine.state.clock.real_time_factor
        assert restored.rng_state == engine.state.rng_state

    def test_restored_entities_are_intentionally_empty(self) -> None:
        # Documents the known limitation explicitly, rather than leaving it
        # as an implicit surprise for whoever reads this later.
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entity = RngEntity("A", engine)
        engine.load(StubScenario("c", seed=1, entities=[entity]))
        engine.start()
        engine.step(max_time_s=1.0)

        blob = engine.state.checkpoint()
        restored = InMemorySimulationState.restore(blob)
        assert restored.entities == {}
