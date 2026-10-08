"""Concrete SimulationState (architecture doc §14 §5.5).

KNOWN LIMITATION, documented per the task prompt rather than hidden: entity
objects satisfying SimulationEntity are opaque third-party objects to this
package — we cannot generically serialize/deserialize their internal state
without knowing their concrete type. checkpoint()/restore() here fully
round-trip clock state and RNG state (root + every entity's derived
stream); entities themselves are NOT captured in the checkpoint blob.
CoreSimulationEngine.reset() works around this by re-deriving everything
from the originally loaded SimulationScenario rather than going through
SimulationState.restore() — see engine.py. A future agent wiring real
Radio entities may need to extend this (e.g. entities gaining their own
serialize/deserialize contract) if mid-run checkpointing of entity-internal
state becomes a real requirement.
"""

from __future__ import annotations

import pickle
import random
from typing import Any

from libraries.plugin_sdk.simulation import SimulationClock, SimulationEntity, SimulationState

from services.simulation.clock import WallClock


class InMemorySimulationState(SimulationState):
    def __init__(
        self,
        clock: SimulationClock,
        entities: dict[str, SimulationEntity],
        root_rng: random.Random,
        entity_rngs: dict[str, random.Random],
    ) -> None:
        self.clock = clock
        self.entities = entities
        self._root_rng = root_rng
        self._entity_rngs = entity_rngs

    @property
    def rng_state(self) -> bytes:
        payload: dict[str, Any] = {
            "root": self._root_rng.getstate(),
            "entities": {eid: r.getstate() for eid, r in self._entity_rngs.items()},
        }
        return pickle.dumps(payload)

    def checkpoint(self) -> bytes:
        payload: dict[str, Any] = {
            "now_s": self.clock.now_s,
            "real_time_factor": self.clock.real_time_factor,
            "rng": pickle.loads(self.rng_state),
            "entity_ids": sorted(
                self.entities.keys()
            ),  # sorted: stable, not insertion-order-dependent
        }
        return pickle.dumps(payload)

    @classmethod
    def restore(cls, blob: bytes) -> "InMemorySimulationState":
        payload = pickle.loads(blob)

        clock = WallClock(real_time_factor=payload["real_time_factor"])
        clock.advance_to(payload["now_s"])

        root_rng = random.Random()
        root_rng.setstate(payload["rng"]["root"])

        entity_rngs: dict[str, random.Random] = {}
        for eid, rng_state in payload["rng"]["entities"].items():
            r = random.Random()
            r.setstate(rng_state)
            entity_rngs[eid] = r

        # entities dict intentionally empty — see module docstring. The
        # engine re-attaches live entity references itself; this classmethod
        # alone cannot reconstruct opaque third-party entity objects.
        return cls(clock=clock, entities={}, root_rng=root_rng, entity_rngs=entity_rngs)
