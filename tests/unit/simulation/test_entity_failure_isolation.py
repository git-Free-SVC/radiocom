"""Regression tests for a real bug found by stress-testing: an entity's
on_tick() raising used to (1) skip every entity sorted after it in the
SAME tick, and (2) never reschedule the next MOBILITY_TICK — leaving the
scheduler permanently empty, so every later step() call would silently do
nothing instead of raising. Fixed by rescheduling the next tick BEFORE the
entity loop and isolating each entity's on_tick() in its own try/except,
bundling any failures into a single ExceptionGroup raised after every
entity has had its turn."""

from __future__ import annotations

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import StubScenario


class _FlakyEntity:
    def __init__(self, entity_id: str, fail_on_tick: int) -> None:
        self.entity_id = entity_id
        self.tick_count = 0
        self._fail_on_tick = fail_on_tick

    def on_tick(self, t_s: float) -> None:
        self.tick_count += 1
        if self.tick_count == self._fail_on_tick:
            raise RuntimeError(f"{self.entity_id} failed on tick {self.tick_count}")


class _NormalEntity:
    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        self.ticks: list[float] = []

    def on_tick(self, t_s: float) -> None:
        self.ticks.append(t_s)


class TestEntityFailureIsolation:
    def test_one_failing_entity_does_not_skip_others_in_same_tick(self) -> None:
        flaky = _FlakyEntity("flaky", fail_on_tick=3)
        normal = _NormalEntity("normal")  # sorts after 'flaky' — the regression case
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        engine.load(StubScenario("isolation", seed=1, entities=[flaky, normal]))
        engine.start()

        try:
            engine.step(max_time_s=10.0)
        except ExceptionGroup:
            pass

        assert (
            2.0 in normal.ticks
        ), "normal entity should still be ticked at t=2.0 despite flaky's failure"

    def test_failure_raises_exceptiongroup_not_silently_swallowed(self) -> None:
        flaky = _FlakyEntity("flaky", fail_on_tick=1)
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        engine.load(StubScenario("isolation", seed=1, entities=[flaky]))
        engine.start()

        raised = None
        try:
            engine.step(max_time_s=5.0)
        except ExceptionGroup as eg:
            raised = eg

        assert raised is not None
        assert len(raised.exceptions) == 1
        assert "flaky failed" in str(raised.exceptions[0])

    def test_scheduler_not_left_empty_after_a_failure(self) -> None:
        flaky = _FlakyEntity("flaky", fail_on_tick=1)
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        engine.load(StubScenario("isolation", seed=1, entities=[flaky]))
        engine.start()

        try:
            engine.step(max_time_s=5.0)
        except ExceptionGroup:
            pass

        assert len(engine._scheduler) > 0, (
            "the recurring tick must still be scheduled after an entity "
            "failure — an empty scheduler here means the simulation is "
            "permanently and silently stalled"
        )

    def test_simulation_continues_advancing_after_a_failure(self) -> None:
        flaky = _FlakyEntity("flaky", fail_on_tick=3)
        engine = CoreSimulationEngine(tick_interval_s=1.0)
        engine.load(StubScenario("isolation", seed=1, entities=[flaky]))
        engine.start()

        try:
            engine.step(max_time_s=10.0)
        except ExceptionGroup:
            pass

        engine.step(max_time_s=10.0)  # must make real progress, not silently no-op
        assert engine.state.clock.now_s == 10.0
