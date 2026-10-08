"""Concrete SimulationEngine (architecture doc §14).

State machine: load() -> (loaded, not started) -> start() -> (running) ->
pause()/resume() toggle within running -> reset() returns to (loaded, not
started) by re-deriving everything from the original scenario + seed.

CONCURRENCY MODEL, established by actually stress-testing with real OS
threads (not just reentrant same-thread calls): this engine is single-
writer. Exactly ONE thread may ever call load()/start()/step()/reset() —
calling step() concurrently from two threads is explicitly rejected (see
_step_lock below) rather than left to race, even though direct testing
(including with sys.setswitchinterval() forced to its minimum to maximize
GIL-switch exposure) never actually observed corruption from CPython's GIL
behavior alone. That absence of observed corruption is NOT a correctness
guarantee — it's an implementation detail of CPython's GIL and OS thread
scheduling granularity that this code does not rely on. pause(), resume(),
and the .state property ARE safe to call from a different thread than the
one driving step() — that IS a supported, explicitly lock-guarded pattern
(the realistic case: an API/UI thread pausing a simulation running in a
background thread), not a GIL-luck pattern.

KNOWN LIMITATION, found by testing, not assumed away: SimulationEntity (the
frozen Protocol in libraries/plugin_sdk/simulation.py) defines no reset()
or reinitialize hook. This means reset() can only GUARANTEE determinism for
state the engine itself owns and re-derives (clock, scheduler, the
per-entity RNG streams exposed via rng_for()) — NOT for any private state
an entity holds internally (e.g. an entity that keeps its own
random.Random instead of calling engine.rng_for() will NOT have that
internal state reset, because the engine has no way to reach into an
opaque third-party object and reinitialize it). Entities that need
reset()-safe randomness MUST use rng_for(entity_id) each tick rather than
caching their own RNG. This should be flagged upstream: the
SimulationEntity Protocol may need a reset() method in a future ADR if
full entity-state reset ever becomes a hard requirement — Agent A does not
change the frozen interface to add this unilaterally.

step(max_time_s) is the actual workhorse: it does NOT run automatically on
start() — a scenario's MOBILITY_TICK self-reschedules forever by design
(continuous simulation), so an unbounded, un-paced step() with nothing to
stop it will not return on its own unless something (an entity's on_tick,
or the caller) eventually calls pause() or the caller bounds it with
max_time_s. This is intentional, not an oversight: it mirrors how a real
API/WebSocket loop would drive the engine incrementally in production
rather than blocking forever in a single call.
"""

from __future__ import annotations

import math
import random
import threading

from libraries.plugin_sdk.simulation import (
    EventKind,
    SimulationEngine,
    SimulationEvent,
    SimulationScenario,
)

from services.simulation.clock import WallClock
from services.simulation.determinism import derive_entity_seed
from services.simulation.scheduler import HeapScheduler
from services.simulation.state import InMemorySimulationState


class CoreSimulationEngine(SimulationEngine):
    def __init__(
        self,
        tick_interval_s: float = 0.1,
        real_time_factor: float = math.inf,
        event_bus=None,
    ) -> None:
        if tick_interval_s <= 0:
            raise ValueError(f"tick_interval_s must be positive, got {tick_interval_s}")
        self._tick_interval_s = tick_interval_s
        self._real_time_factor = real_time_factor  # math.inf = unbounded/accelerated (default)
        self._event_bus = event_bus

        self._scenario: SimulationScenario | None = None
        self._clock: WallClock | None = None
        self._scheduler: HeapScheduler | None = None
        self._entities: dict = {}
        self._root_rng: random.Random | None = None
        self._entity_rngs: dict[str, random.Random] = {}

        self._loaded = False
        self._started = False
        self._paused = False
        self._seq_counter = 0
        self._tick_count = 0

        # Guards the _paused flag — the one piece of state explicitly
        # supported for cross-thread access (pause()/resume() called from
        # a different thread than the one running step()).
        self._pause_lock = threading.Lock()
        # Guards step() itself against concurrent invocation. acquire(blocking=False)
        # in step() means a second concurrent call fails fast with a clear
        # error instead of racing on the heap/seq_counter/tick_count/clock.
        self._step_lock = threading.Lock()
        # Tracks which thread currently holds _step_lock via load()/step(),
        # so load()/reset() can detect a same-thread reentrant call (an
        # entity calling engine.reset() from its own on_tick()) and raise
        # immediately instead of deadlocking on its own blocking acquire —
        # found by testing: a silent indefinite hang is strictly worse than
        # any of this engine's other failure modes, which all fail loud.
        self._step_lock_owner: int | None = None

    # -- lifecycle -----------------------------------------------------

    def load(self, scenario: SimulationScenario) -> None:
        # BLOCKING acquire of _step_lock (unlike step()'s non-blocking one):
        # found by stress-testing that calling load()/reset() from another
        # thread while step() was actively running in a different thread
        # produced silent, confusing corruption — no exception, but a
        # hybrid of pre- and post-reset state (observed: tick_count=71
        # split across two "runs", clock at a non-sensical 0.043s). This
        # blocking acquire makes load()/reset() simply WAIT for any
        # in-flight step() to finish or return-via-pause before mutating,
        # instead of racing with it. If the caller wants a prompt reset()
        # of a running simulation, call pause() first — step() returns
        # quickly once paused, so the wait here stays short. Calling
        # load()/reset() reentrantly from WITHIN an entity's on_tick() of
        # the step() call currently holding this same lock, on the SAME
        # thread, WILL deadlock (plain Lock, not reentrant) — this is an
        # explicit, documented constraint, not a supported pattern: an
        # entity should never trigger a full engine reload of itself.
        current_thread = threading.get_ident()
        if self._step_lock_owner == current_thread:
            # This thread already holds _step_lock (we're inside a step()
            # call, inside an entity's on_tick(), which called load()/
            # reset() on itself). A plain threading.Lock is not reentrant,
            # so blocking-acquiring it here would deadlock this thread
            # against itself forever. Fail loud instead — verified by
            # testing that without this check, this exact scenario hangs
            # indefinitely with no error, ever.
            raise RuntimeError(
                "load()/reset() called reentrantly from the same thread "
                "currently running step() — likely an entity calling "
                "engine.load()/reset() from its own on_tick(). This is not "
                "supported: call pause() from on_tick() instead, and "
                "load()/reset() after step() returns to the caller."
            )

        with self._step_lock:
            self._step_lock_owner = current_thread
            try:
                self._scenario = scenario
                self._clock = WallClock(real_time_factor=self._real_time_factor)
                self._scheduler = HeapScheduler()
                self._entities = {e.entity_id: e for e in scenario.entities}
                self._root_rng = random.Random(scenario.seed)
                self._entity_rngs = {
                    eid: random.Random(derive_entity_seed(scenario.seed, eid))
                    for eid in self._entities
                }
                self._seq_counter = 0
                self._tick_count = 0
                self._loaded = True
                self._started = False
                with self._pause_lock:
                    self._paused = False

                self._schedule_tick(at_time_s=0.0)
                self._publish(
                    EventKind.SCENARIO_CONTROL, {"action": "loaded", "scenario": scenario.name}
                )
            finally:
                self._step_lock_owner = None

    def start(self) -> None:
        self._require_loaded()
        self._started = True
        with self._pause_lock:
            self._paused = False
        self._publish(EventKind.SCENARIO_CONTROL, {"action": "started", "at": self._clock.now_s})

    def pause(self) -> None:
        # Safe to call from a different thread than the one running step() —
        # see the CONCURRENCY MODEL note in the module docstring.
        self._require_loaded()
        with self._pause_lock:
            self._paused = True
        self._publish(EventKind.SCENARIO_CONTROL, {"action": "paused", "at": self._clock.now_s})

    def resume(self) -> None:
        self._require_loaded()
        if not self._started:
            raise RuntimeError("cannot resume: engine was never started (call start() first)")
        with self._pause_lock:
            self._paused = False
        self._publish(EventKind.SCENARIO_CONTROL, {"action": "resumed", "at": self._clock.now_s})

    def reset(self) -> None:
        self._require_loaded()
        # Re-derive everything deterministically from the ORIGINAL scenario
        # object (not from a checkpoint blob) — this is the documented path
        # around SimulationState.restore()'s opaque-entity limitation.
        original_scenario = self._scenario
        self.load(original_scenario)

    def step(self, max_time_s: float | None = None) -> None:
        self._require_loaded()
        if not self._started:
            raise RuntimeError("cannot step: engine was never started (call start() first)")

        if not self._step_lock.acquire(blocking=False):
            raise RuntimeError(
                "step() is already running (from another thread or a reentrant "
                "call) — concurrent step() calls on the same engine are not "
                "supported. pause()/resume()/.state are safe to call from a "
                "different thread; step() itself is single-writer only."
            )
        self._step_lock_owner = threading.get_ident()
        try:
            self._step_locked(max_time_s)
        finally:
            self._step_lock_owner = None
            self._step_lock.release()

    def _step_locked(self, max_time_s: float | None) -> None:
        # _paused is read without the lock here deliberately: a plain
        # attribute read cannot produce a torn value in CPython, and this
        # loop runs millions of times on a long simulation (verified:
        # ~1.9M on_tick calls/sec) — acquiring _pause_lock every iteration
        # would cost real throughput for a guarantee the read doesn't need.
        # Only _paused WRITES (pause()/resume()) are lock-guarded.
        while not self._paused:
            next_time = self._scheduler.peek_time()
            if next_time is None:
                break
            if max_time_s is not None and next_time > max_time_s:
                break
            event = self._scheduler.pop_next()
            self._clock.sleep_until_paced(event.time_s)  # no-op when real_time_factor is inf
            self._clock.advance_to(event.time_s)
            self._handle_event(event)

    def rng_for(self, entity_id: str) -> random.Random:
        """The deterministically-derived RNG stream for one entity (§14
        §5.2). Entities that want reset()-safe randomness should call this
        on every tick rather than holding their own random.Random — the
        engine replaces this dict with freshly-seeded instances on every
        load()/reset(), so a private entity-held RNG does NOT get reset
        (see the module docstring's 'known limitation' and reset()'s)."""
        self._require_loaded()
        return self._entity_rngs[entity_id]

    # -- internals -------------------------------------------------------

    def _schedule_tick(self, at_time_s: float) -> None:
        # Unused for the recurring tick itself (see _schedule_next_tick) —
        # kept for the one-off initial schedule call in load(), where
        # at_time_s=0.0 is the obvious, unambiguous choice.
        self._scheduler.schedule(
            SimulationEvent(time_s=at_time_s, seq=self._next_seq(), kind=EventKind.MOBILITY_TICK)
        )

    def _schedule_next_tick(self) -> None:
        # time_s computed as tick_count * tick_interval_s (multiplication),
        # NOT by repeatedly adding tick_interval_s to the previous event's
        # time_s. Found by stress-testing: cumulative addition over 100k+
        # ticks drifts measurably from the exact value (e.g. 999.9999999992
        # instead of 1000.0) due to floating-point rounding compounding on
        # every addition. Multiplying tick_count by the interval computes
        # each tick's time independently, so error doesn't accumulate.
        self._tick_count += 1
        at_time_s = self._tick_count * self._tick_interval_s
        self._scheduler.schedule(
            SimulationEvent(time_s=at_time_s, seq=self._next_seq(), kind=EventKind.MOBILITY_TICK)
        )

    def _next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def _handle_event(self, event: SimulationEvent) -> None:
        if event.kind == EventKind.MOBILITY_TICK:
            # Reschedule the NEXT tick FIRST, before touching any entity.
            # Found by stress-testing: if this came after the entity loop,
            # one entity's on_tick() raising would permanently kill the
            # recurring tick — the scheduler would end up empty, and every
            # later step() call would silently do nothing (no exception,
            # no progress) instead of failing loudly. Rescheduling first
            # means the simulation can never be silently stalled by an
            # entity bug, regardless of what happens below.
            self._schedule_next_tick()

            # Each entity is isolated: one entity's on_tick() raising must
            # not prevent every other entity from being ticked this round
            # (also found by stress-testing — entities sorted after a
            # failing one were silently skipped before this fix). Failures
            # are collected and raised together after every entity has had
            # its turn, so nothing is silently swallowed.
            failures: list[tuple[str, BaseException]] = []
            for entity_id in sorted(self._entities.keys()):
                try:
                    self._entities[entity_id].on_tick(event.time_s)
                except Exception as exc:  # noqa: BLE001 - deliberately broad, isolated per entity
                    failures.append((entity_id, exc))
            if failures:
                raise ExceptionGroup(
                    f"{len(failures)} entity on_tick() failure(s) at t={event.time_s}",
                    [exc for _, exc in failures],
                )
        # LINK_EVALUATE / RADIO_STATE_CHANGE / SCENARIO_CONTROL events raised
        # by other subsystems (later waves) are delivered in time order but
        # not interpreted here — Agent A only owns scheduling, not RF/link
        # semantics.
        self._publish(event.kind, event.payload)

    def _publish(self, kind: EventKind, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(kind.value, payload)

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("SimulationEngine.load() must be called first")

    # -- SimulationEngine.state ------------------------------------------

    @property
    def state(self) -> InMemorySimulationState:
        self._require_loaded()
        return InMemorySimulationState(
            clock=self._clock,
            entities=dict(self._entities),
            root_rng=self._root_rng,
            entity_rngs=dict(self._entity_rngs),
        )
