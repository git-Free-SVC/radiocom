"""Concrete SimulationClock (architecture doc §14).

Design choice (not fixed by the Protocol, only the method signatures are):
`real_time_factor == math.inf` means "unbounded/accelerated" — run as fast
as possible with no wall-clock pacing. Any finite value paces so that one
simulated second takes `1 / real_time_factor` wall seconds (1.0 = real-time).
Pacing itself is driven by the engine's run loop (via `sleep_for_tick`),
not by the clock — the clock only tracks simulated time.
"""

from __future__ import annotations

import math
import time

from libraries.plugin_sdk.simulation import SimulationClock


class WallClock(SimulationClock):
    """Satisfies the SimulationClock Protocol structurally (duck-typed —
    SimulationClock is a plain Protocol, not a runtime_checkable one with
    isinstance enforcement needed here)."""

    def __init__(self, real_time_factor: float = math.inf) -> None:
        if real_time_factor <= 0:
            raise ValueError(f"real_time_factor must be positive, got {real_time_factor}")
        self._now_s = 0.0
        self._real_time_factor = real_time_factor
        self._wall_reference: float | None = None  # set lazily, first pacing call

    @property
    def now_s(self) -> float:
        return self._now_s

    def advance_to(self, t_s: float) -> None:
        if t_s < self._now_s:
            raise ValueError(f"cannot move simulation clock backward: {t_s} < {self._now_s}")
        self._now_s = t_s

    @property
    def real_time_factor(self) -> float:
        return self._real_time_factor

    def sleep_until_paced(self, event_time_s: float) -> None:
        """Block until wall-clock has caught up to `event_time_s` at the
        configured real_time_factor. No-op when unbounded (math.inf)."""
        if math.isinf(self._real_time_factor):
            return
        now_wall = time.monotonic()
        if self._wall_reference is None:
            self._wall_reference = now_wall - (self._now_s / self._real_time_factor)
        target_wall = self._wall_reference + (event_time_s / self._real_time_factor)
        delay = target_wall - now_wall
        if delay > 0:
            time.sleep(delay)
