"""Regression tests for a real bug found by stress-testing: WallClock's
pacing logic (sleep_until_paced) existed but was never invoked by the
engine's step() loop, and real_time_factor was hardcoded to math.inf with
no way to configure it. A finite real_time_factor silently had zero effect
on actual run speed. Fixed by threading real_time_factor through
CoreSimulationEngine's constructor and calling clock.sleep_until_paced()
in step()'s loop."""

from __future__ import annotations

import time

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import CountingEntity, StubScenario


class TestPacing:
    def test_finite_real_time_factor_actually_paces(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=0.05, real_time_factor=1.0)
        entity = CountingEntity("A")
        engine.load(StubScenario("pacing", seed=1, entities=[entity]))
        engine.start()

        t0 = time.monotonic()
        engine.step(max_time_s=0.3)  # 6 ticks * 0.05s = 0.3 simulated seconds
        elapsed = time.monotonic() - t0

        assert abs(elapsed - 0.3) < 0.1, (
            f"real_time_factor=1.0 should pace ~0.3s wall time for 0.3s "
            f"simulated, got {elapsed:.3f}s — pacing is not wired in"
        )

    def test_default_unbounded_is_still_instant(self) -> None:
        # No real_time_factor given — must stay at the original fast/unbounded
        # default behavior; the pacing fix must not slow down the common case.
        engine = CoreSimulationEngine(tick_interval_s=0.05)
        entity = CountingEntity("A")
        engine.load(StubScenario("unbounded", seed=1, entities=[entity]))
        engine.start()

        t0 = time.monotonic()
        engine.step(max_time_s=0.5)
        elapsed = time.monotonic() - t0

        assert (
            elapsed < 0.05
        ), f"default (unbounded) run should be near-instant, took {elapsed:.3f}s"
