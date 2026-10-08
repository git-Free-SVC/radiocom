from __future__ import annotations

import pytest

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import CountingEntity, StubScenario


class TestPauseResume:
    def test_pause_mid_run_then_resume_matches_unpaused_run(self) -> None:
        engine_a = CoreSimulationEngine(tick_interval_s=1.0)
        entity_a = CountingEntity("A")
        engine_a.load(StubScenario("p", seed=7, entities=[entity_a]))
        engine_a.start()
        engine_a.step(max_time_s=5.0)

        engine_b = CoreSimulationEngine(tick_interval_s=1.0)
        entity_b = CountingEntity("A", pause_at=2.0, engine=engine_b)
        engine_b.load(StubScenario("p", seed=7, entities=[entity_b]))
        engine_b.start()
        engine_b.step(max_time_s=5.0)  # stops early — entity called pause() at t=2.0
        assert engine_b.state.clock.now_s == 2.0
        engine_b.resume()
        engine_b.step(max_time_s=5.0)  # continues to completion

        assert entity_a.ticks == entity_b.ticks

    def test_state_queryable_while_paused(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entity = CountingEntity("A", pause_at=1.0, engine=engine)
        engine.load(StubScenario("p", seed=1, entities=[entity]))
        engine.start()
        engine.step(max_time_s=5.0)
        # should not raise — .state must be readable while paused
        assert engine.state.clock.now_s == 1.0

    def test_resume_without_start_raises(self) -> None:
        engine = CoreSimulationEngine()
        engine.load(StubScenario("p", seed=1, entities=[]))
        with pytest.raises(RuntimeError):
            engine.resume()

    def test_step_without_start_raises(self) -> None:
        engine = CoreSimulationEngine()
        engine.load(StubScenario("p", seed=1, entities=[]))
        with pytest.raises(RuntimeError):
            engine.step(max_time_s=1.0)
