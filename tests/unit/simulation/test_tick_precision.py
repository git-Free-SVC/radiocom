"""Regression test for a real bug found by stress-testing: scheduling each
tick as `previous_event.time_s + tick_interval_s` accumulates floating-point
rounding error over many ticks (observed: 999.9999999992356 instead of
exactly 1000.0 after 100,000 ticks at a 0.01s interval). Fixed by computing
each tick's time as `tick_count * tick_interval_s` — a single multiplication
per tick, which does not accumulate error."""

from __future__ import annotations

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import StubScenario


class _SilentEntity:
    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        self.count = 0

    def on_tick(self, t_s: float) -> None:
        self.count += 1


class TestTickPrecision:
    def test_long_run_clock_lands_on_exact_value(self) -> None:
        entity = _SilentEntity("A")
        engine = CoreSimulationEngine(tick_interval_s=0.01)
        engine.load(StubScenario("precision", seed=1, entities=[entity]))
        engine.start()
        engine.step(max_time_s=1000.0)

        assert engine.state.clock.now_s == 1000.0, (
            f"expected exactly 1000.0 after 100,000 ticks at 0.01s interval, "
            f"got {engine.state.clock.now_s!r} — tick time is drifting"
        )

    def test_entity_receives_correct_tick_count(self) -> None:
        entity = _SilentEntity("A")
        engine = CoreSimulationEngine(tick_interval_s=0.01)
        engine.load(StubScenario("precision", seed=1, entities=[entity]))
        engine.start()
        engine.step(max_time_s=1000.0)

        assert entity.count == 100_001  # includes the t=0.0 tick
