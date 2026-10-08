"""Regression test for a real bug found by stress-testing with genuine OS
threads (not just reentrant single-thread calls): unsynchronized heapq
operations on the same HeapScheduler, called from different threads at the
same time, reproducibly raised `RuntimeError('list changed size during
iteration')` — every one of 5 independent trials crashed within a few
thousand operations. Fixed with an internal threading.Lock. This test is
sized to run in well under a second while still genuinely exercising the
race (the original failure showed up within ~1000-3000 operations)."""

from __future__ import annotations

import random
import threading

from libraries.plugin_sdk.simulation import SimulationEvent, EventKind
from services.simulation.scheduler import HeapScheduler


class TestSchedulerConcurrency:
    def test_concurrent_push_and_pop_does_not_crash_or_corrupt(self) -> None:
        sch = HeapScheduler()
        errors: list[tuple[str, int, str]] = []
        popped_log: list[SimulationEvent] = []
        popped_lock = threading.Lock()
        stop_flag = threading.Event()

        for i in range(200):
            sch.schedule(
                SimulationEvent(time_s=random.uniform(0, 100), seq=i, kind=EventKind.MOBILITY_TICK)
            )

        def pusher(thread_id: int) -> None:
            rng = random.Random(1000 + thread_id)
            try:
                for i in range(500):
                    seq = 100_000 + thread_id * 500 + i
                    sch.schedule(
                        SimulationEvent(
                            time_s=rng.uniform(0, 100), seq=seq, kind=EventKind.MOBILITY_TICK
                        )
                    )
            except Exception as e:  # noqa: BLE001 - want to catch anything to fail the test cleanly
                errors.append(("push", thread_id, repr(e)))

        def popper(thread_id: int) -> None:
            try:
                count = 0
                while not stop_flag.is_set() and count < 500:
                    evt = sch.pop_next()
                    if evt is not None:
                        with popped_lock:
                            popped_log.append(evt)
                        count += 1
            except Exception as e:  # noqa: BLE001
                errors.append(("pop", thread_id, repr(e)))

        threads = [threading.Thread(target=pusher, args=(i,)) for i in range(4)]
        threads += [threading.Thread(target=popper, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
        stop_flag.set()

        still_alive = [t for t in threads if t.is_alive()]
        duplicate_seqs = len(popped_log) != len({e.seq for e in popped_log})

        assert not errors, f"concurrent push/pop raised: {errors}"
        assert not still_alive, "a thread did not finish within the timeout — possible deadlock"
        assert not duplicate_seqs, "the same event was popped more than once — heap corruption"
