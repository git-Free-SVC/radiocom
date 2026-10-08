"""Regression tests for the engine's concurrency contract, established by
stress-testing with genuine OS threads: pause()/resume()/.state are safe
to call from a thread other than the one driving step(); step() itself is
single-writer (a second concurrent step() call fails fast rather than
racing); and load()/reset() BLOCK until any in-flight step() call finishes
rather than mutating state out from under it — found by testing that
without this, reset() from another thread while step() ran elsewhere
produced silent, confusing corruption (a hybrid of pre- and post-reset
state) with no exception raised at all. Every test here has a bounded
timeout: if a future change reintroduces a deadlock, these tests FAIL
cleanly instead of hanging the whole CI run."""

from __future__ import annotations

import threading
import time

from services.simulation import CoreSimulationEngine
from tests.unit.simulation.conftest import StubScenario


class _SlowEntity:
    """A deliberate per-tick delay so a background step() call stays
    in-flight long enough for another thread to interact with the engine
    while it's genuinely still running — a near-instant entity would let
    step() finish before the test gets a chance to race it."""

    def __init__(self, entity_id: str, delay_s: float = 0.002) -> None:
        self.entity_id = entity_id
        self.tick_count = 0
        self._delay_s = delay_s

    def on_tick(self, t_s: float) -> None:
        self.tick_count += 1
        time.sleep(self._delay_s)


class TestEngineConcurrency:
    def test_pause_from_separate_thread_stops_running_step(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=0.01)
        entity = _SlowEntity("A")
        engine.load(StubScenario("pause-thread", seed=1, entities=[entity]))
        engine.start()

        t = threading.Thread(target=lambda: engine.step(max_time_s=1000.0))
        t.start()
        time.sleep(0.02)
        engine.pause()
        t.join(timeout=5.0)

        assert not t.is_alive(), "pause() from another thread did not stop the running step()"

    def test_concurrent_step_calls_fail_fast(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=0.01)
        entity = _SlowEntity("A")
        engine.load(StubScenario("concurrent-step", seed=1, entities=[entity]))
        engine.start()

        errors: list[str] = []

        def run_step() -> None:
            try:
                engine.step(max_time_s=1.0)
            except RuntimeError as e:
                errors.append(str(e))

        t1 = threading.Thread(target=run_step)
        t2 = threading.Thread(target=run_step)
        t1.start()
        time.sleep(0.02)  # ensure t1 is genuinely running first
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        assert (
            len(errors) == 1
        ), f"expected exactly one rejected concurrent step() call, got {errors}"
        assert "already running" in errors[0]

    def test_reset_from_another_thread_waits_instead_of_corrupting(self) -> None:
        engine = CoreSimulationEngine(tick_interval_s=0.01)
        entity = _SlowEntity("A")
        engine.load(StubScenario("reset-thread", seed=1, entities=[entity]))
        engine.start()

        step_thread = threading.Thread(target=lambda: engine.step(max_time_s=1.0))
        step_thread.start()
        time.sleep(0.02)  # let step() get a few ticks in

        reset_done = threading.Event()
        reset_errors: list[Exception] = []

        def do_reset() -> None:
            try:
                engine.reset()
            except Exception as e:  # noqa: BLE001
                reset_errors.append(e)
            finally:
                reset_done.set()

        reset_thread = threading.Thread(target=do_reset)
        reset_thread.start()
        completed = reset_done.wait(timeout=5.0)
        step_thread.join(timeout=5.0)

        assert completed, "reset() did not complete within the timeout — possible deadlock"
        assert not reset_errors, f"reset() raised unexpectedly: {reset_errors}"
        assert engine.state.clock.now_s == 0.0, (
            "clock is not exactly 0.0 after reset() — this is the signature of the "
            "original corruption bug (a hybrid of pre- and post-reset state)"
        )

    def test_reentrant_reset_from_within_on_tick_fails_loud_not_deadlock(self) -> None:
        """An entity calling engine.reset() from its OWN on_tick() — the
        SAME thread already running step(), which already holds the step
        lock — must raise immediately, not block forever. A first version
        of this guard used a plain blocking `with self._step_lock:` in
        load()/reset() with no same-thread detection, which deadlocked this
        exact scenario silently and indefinitely (confirmed by running it
        with a daemon thread + timeout before the fix: still alive after
        3s with zero error output). This test uses the same safe pattern —
        a daemon thread with a bounded join — so if this regresses, the
        test fails cleanly instead of hanging the whole CI run."""
        caught: list[Exception] = []

        class ReentrantResetEntity:
            """Calls engine.reset() on EVERY tick, not just once — this is
            deliberate: it proves the guard keeps failing loud consistently
            on every repeated reentrant attempt, not just the first, and
            that a caught-and-ignored failure doesn't leave the engine in
            some half-broken state that behaves differently next time."""

            def __init__(self, entity_id: str, engine: CoreSimulationEngine) -> None:
                self.entity_id = entity_id
                self._engine = engine

            def on_tick(self, t_s: float) -> None:
                try:
                    self._engine.reset()
                except RuntimeError as e:
                    caught.append(e)

        engine = CoreSimulationEngine(tick_interval_s=1.0)
        entity = ReentrantResetEntity("A", engine)
        engine.load(StubScenario("reentrant-deadlock", seed=1, entities=[entity]))
        engine.start()

        t = threading.Thread(target=lambda: engine.step(max_time_s=5.0), daemon=True)
        t.start()
        t.join(timeout=3.0)

        assert not t.is_alive(), (
            "step() thread is still alive after the timeout — reentrant "
            "load()/reset() from within on_tick() is deadlocking again"
        )
        assert len(caught) == 6  # one per tick: t=0,1,2,3,4,5
        assert all("reentrant" in str(e).lower() for e in caught)
