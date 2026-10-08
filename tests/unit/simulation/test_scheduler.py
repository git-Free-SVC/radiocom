from __future__ import annotations

from libraries.plugin_sdk.simulation import EventKind, SimulationEvent
from services.simulation.scheduler import HeapScheduler


class TestHeapScheduler:
    def test_pops_in_time_order(self) -> None:
        sch = HeapScheduler()
        sch.schedule(SimulationEvent(time_s=3.0, seq=1, kind=EventKind.MOBILITY_TICK))
        sch.schedule(SimulationEvent(time_s=1.0, seq=2, kind=EventKind.MOBILITY_TICK))
        sch.schedule(SimulationEvent(time_s=2.0, seq=3, kind=EventKind.MOBILITY_TICK))
        times = [sch.pop_next().time_s for _ in range(3)]
        assert times == [1.0, 2.0, 3.0]

    def test_seq_breaks_ties_at_equal_time(self) -> None:
        sch = HeapScheduler()
        sch.schedule(SimulationEvent(time_s=1.0, seq=3, kind=EventKind.MOBILITY_TICK))
        sch.schedule(SimulationEvent(time_s=1.0, seq=1, kind=EventKind.MOBILITY_TICK))
        sch.schedule(SimulationEvent(time_s=1.0, seq=2, kind=EventKind.MOBILITY_TICK))
        seqs = [sch.pop_next().seq for _ in range(3)]
        assert seqs == [1, 2, 3]

    def test_peek_time_does_not_consume(self) -> None:
        sch = HeapScheduler()
        sch.schedule(SimulationEvent(time_s=5.0, seq=1, kind=EventKind.MOBILITY_TICK))
        assert sch.peek_time() == 5.0
        assert sch.peek_time() == 5.0  # still there
        assert len(sch) == 1

    def test_empty_scheduler(self) -> None:
        sch = HeapScheduler()
        assert sch.peek_time() is None
        assert sch.pop_next() is None
