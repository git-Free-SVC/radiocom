"""link_quality classifier: boundaries, monotonicity, exhaustiveness."""

from __future__ import annotations

import math
import random

import pytest

from libraries.domain.rf_results import LinkQuality
from libraries.physics.errors import PhysicsInputError
from libraries.physics.quality import link_quality

UP, MARGINAL, DOWN = LinkQuality.UP, LinkQuality.MARGINAL, LinkQuality.DOWN


@pytest.mark.parametrize(
    ("margin", "expected"),
    [
        (10.0, UP),
        (math.nextafter(10.0, math.inf), UP),
        (math.nextafter(10.0, -math.inf), MARGINAL),
        (0.0, MARGINAL),
        (-0.0, MARGINAL),
        (math.nextafter(0.0, math.inf), MARGINAL),
        (math.nextafter(0.0, -math.inf), DOWN),
        (68.6, UP),
        (5.0, MARGINAL),
        (-0.001, DOWN),
        (-300.0, DOWN),
        (math.inf, UP),
        (-math.inf, DOWN),
        (7, MARGINAL),
    ],
)
def test_boundaries(margin: float, expected: LinkQuality) -> None:
    assert link_quality(margin) is expected


@pytest.mark.parametrize("bad", [math.nan, "5", None, True])
def test_bad_inputs(bad: object) -> None:
    with pytest.raises(PhysicsInputError):
        link_quality(bad)  # type: ignore[arg-type]


def test_monotonic_and_exhaustive() -> None:
    order = {DOWN: 0, MARGINAL: 1, UP: 2}
    rng = random.Random(7)
    samples = sorted(rng.uniform(-100, 100) for _ in range(10_000))
    ranks = [order[link_quality(m)] for m in samples]  # exactly one class per value
    assert ranks == sorted(ranks)
