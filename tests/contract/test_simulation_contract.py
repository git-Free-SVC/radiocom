"""Contract for SimulationEngine + SimulationScheduler.

    pytest tests/contract/test_simulation_contract.py --engine-impl=pkg:Engine --scheduler-impl=pkg:Sched
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from libraries.plugin_sdk.simulation import (
    EventKind,
    SimulationEngine,
    SimulationEvent,
    SimulationScheduler,
)


@dataclass
class RecordingEntity:
    entity_id: str
    ticks: list = field(default_factory=list)

    def on_tick(self, t_s: float) -> None:
        self.ticks.append(t_s)


@dataclass
class Scenario:
    name: str = "contract"
    seed: int = 7
    entities: list = field(default_factory=lambda: [RecordingEntity("r1"), RecordingEntity("r2")])


def _running(engine, **kw):
    sc = Scenario(**kw)
    engine.load(sc)
    engine.start()
    return sc


# ---------------- scheduler ----------------
def test_scheduler_is_abc_impl(scheduler):
    assert isinstance(scheduler, SimulationScheduler)


def test_scheduler_empty(scheduler):
    assert scheduler.pop_next() is None and scheduler.peek_time() is None


def test_scheduler_orders_by_time_then_seq(scheduler):
    K = EventKind.LINK_EVALUATE
    for t, s in [(3.0, 0), (1.0, 5), (1.0, 2), (2.0, 1)]:
        scheduler.schedule(SimulationEvent(t, s, K))
    assert scheduler.peek_time() == 1.0
    order = []
    while (e := scheduler.pop_next()) is not None:
        order.append((e.time_s, e.seq))
    assert order == [(1.0, 2), (1.0, 5), (2.0, 1), (3.0, 0)]


# ---------------- engine lifecycle ----------------
def test_engine_is_abc_impl(engine):
    assert isinstance(engine, SimulationEngine)


def test_state_before_load_raises(engine):
    with pytest.raises(RuntimeError):
        engine.state


@pytest.mark.parametrize("op", ["start", "pause", "resume", "reset", "step"])
def test_operations_before_load_raise(engine, op):
    with pytest.raises(RuntimeError):
        getattr(engine, op)()


def test_illegal_transitions_raise(engine):
    engine.load(Scenario())
    with pytest.raises(RuntimeError):
        engine.pause()  # loaded -> pause
    with pytest.raises(RuntimeError):
        engine.step(1.0)  # loaded -> step
    engine.start()
    with pytest.raises(RuntimeError):
        engine.start()  # already running
    with pytest.raises(RuntimeError):
        engine.resume()  # not paused
    engine.pause()
    with pytest.raises(RuntimeError):
        engine.step(1.0)  # paused -> step
    engine.resume()
    engine.step(1.0)


def test_state_exposes_clock_entities_rng(engine):
    _running(engine)
    st = engine.state
    assert callable(st.checkpoint) and callable(type(st).restore)
    assert st.clock.now_s == 0.0
    assert set(st.entities) == {"r1", "r2"}
    assert isinstance(st.rng_state, bytes)


# ---------------- run semantics ----------------
def test_step_advances_clock_to_max_time(engine):
    _running(engine)
    engine.step(max_time_s=5.0)
    assert engine.state.clock.now_s == 5.0


def test_step_into_past_raises(engine):
    _running(engine)
    engine.step(5.0)
    with pytest.raises(ValueError):
        engine.step(2.0)


def test_entity_ticks_are_ordered_and_bounded(engine):
    sc = _running(engine)
    engine.step(5.0)
    for ent in sc.entities:
        assert ent.ticks == sorted(ent.ticks)
        assert all(0 <= t <= 5.0 for t in ent.ticks)


def test_step_none_drains_queue_and_terminates(engine):
    _running(engine)
    engine.step(None)  # must return


def test_reset_returns_to_time_zero(engine):
    _running(engine)
    engine.step(5.0)
    engine.reset()
    assert engine.state.clock.now_s == 0.0
    engine.start()
    engine.step(5.0)  # runnable again


# ---------------- determinism (§14/§24) ----------------
def _run_and_checkpoint(engine_cls_instance, seed):
    _running(engine_cls_instance, seed=seed)
    engine_cls_instance.step(10.0)
    return engine_cls_instance.state.checkpoint()


def test_same_seed_same_checkpoint(request):
    cls = type(request.getfixturevalue("engine"))
    assert _run_and_checkpoint(cls(), 7) == _run_and_checkpoint(cls(), 7)


def test_checkpoint_roundtrip(engine):
    _running(engine)
    engine.step(3.0)
    st = engine.state
    blob = st.checkpoint()
    restored = type(st).restore(blob)
    assert restored.clock.now_s == st.clock.now_s
    assert restored.checkpoint() == blob
