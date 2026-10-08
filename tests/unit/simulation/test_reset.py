"""reset() is only GUARANTEED deterministic for state the engine itself
owns (clock, scheduler, rng_for() streams) — see engine.py's documented
limitation. Entities MUST use engine.rng_for() rather than a private RNG
for their own randomness to benefit from this; that's what RngEntity
(tests/unit/simulation/conftest.py) demonstrates."""

from __future__ import annotations

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import RngEntity, StubScenario


class TestReset:
    def test_reset_then_rerun_reproduces_original_run(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entities = [RngEntity(eid, engine) for eid in ("A", "B")]
        engine.load(StubScenario("r", seed=555, entities=entities))
        engine.start()
        engine.step(max_time_s=3.0)
        first_run = [tuple(e.draws) for e in entities]

        for e in entities:
            e.draws = []  # clear the test-side accumulator only

        engine.reset()
        engine.start()
        engine.step(max_time_s=3.0)
        second_run = [tuple(e.draws) for e in entities]

        assert first_run == second_run

    def test_reset_resets_clock_to_zero(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entity = RngEntity("A", engine)
        engine.load(StubScenario("r", seed=1, entities=[entity]))
        engine.start()
        engine.step(max_time_s=5.0)
        assert engine.state.clock.now_s == 5.0

        engine.reset()
        assert engine.state.clock.now_s == 0.0
