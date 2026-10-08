"""The single most important test in this package — architecture doc §24's
eventual golden-file determinism gate checks exactly this property."""

from __future__ import annotations

from services.simulation import CoreSimulationEngine, derive_entity_seed
from tests.unit.simulation.conftest import RngEntity, StubScenario


def _run(seed: int) -> list[tuple[float, ...]]:
    engine = CoreSimulationEngine(tick_interval_s=1.0)
    entities = [RngEntity(eid, engine) for eid in ("A", "B", "C")]
    engine.load(StubScenario("determinism", seed=seed, entities=entities))
    engine.start()
    engine.step(max_time_s=10.0)
    return [tuple(e.draws) for e in entities]


class TestDeterminism:
    def test_same_seed_produces_identical_draws(self) -> None:
        assert _run(1234) == _run(1234)

    def test_different_seed_produces_different_draws(self) -> None:
        assert _run(1234) != _run(9999)

    def test_entity_seed_derivation_is_order_independent(self) -> None:
        # Deriving seeds for A then B must give the same result as B then A —
        # derive_entity_seed must not depend on call order (it's a pure hash).
        s1 = derive_entity_seed(42, "A")
        s2 = derive_entity_seed(42, "B")
        assert derive_entity_seed(42, "A") == s1
        assert derive_entity_seed(42, "B") == s2
        assert s1 != s2
