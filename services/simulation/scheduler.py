"""Concrete SimulationScheduler (architecture doc §14 §5.6 — plain heapq,
no over-engineering). SimulationEvent already has order=True with `seq` as
the tie-breaker, so heapq's natural ordering on the dataclass is correct.

Guarded by a lock: found by stress-testing with genuine concurrent threads
(not just reentrant single-threaded calls) that unsynchronized heapq.heappush
/ heappop on the same list, called from different threads at the same time,
reproducibly raised `RuntimeError('list changed size during iteration')` —
every one of 5 trials crashed within a few thousand operations. CPython's
GIL prevents low-level memory corruption but does NOT make a multi-step
operation like heappush/heappop atomic as a whole; a context switch mid-sift
is enough to break the heap's internal list iteration. A real caller of this
scheduler is expected to be a single driver thread calling pop_next()/
peek_time() in a loop (e.g. CoreSimulationEngine.step()), while a DIFFERENT
thread may legitimately call schedule() to inject an event (e.g. a future
subsystem reacting to a LINK_EVALUATE result) — that's exactly the pattern
that crashed, so the lock is not optional."""

from __future__ import annotations

import heapq
import threading

from libraries.plugin_sdk.simulation import SimulationEvent, SimulationScheduler


class HeapScheduler(SimulationScheduler):
    def __init__(self) -> None:
        self._heap: list[SimulationEvent] = []
        self._lock = threading.Lock()

    def schedule(self, event: SimulationEvent) -> None:
        with self._lock:
            heapq.heappush(self._heap, event)

    def pop_next(self) -> SimulationEvent | None:
        with self._lock:
            if not self._heap:
                return None
            return heapq.heappop(self._heap)

    def peek_time(self) -> float | None:
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0].time_s

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)
