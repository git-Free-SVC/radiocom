"""Free-space path loss: golden values, invariants, hostile inputs, accuracy."""

from __future__ import annotations

import math
import random
from decimal import Decimal, getcontext

import pytest

from libraries.physics.constants import SPEED_OF_LIGHT_M_S
from libraries.physics.errors import PhysicsInputError
from libraries.physics.path_loss import free_space_path_loss_db

# (distance_m, frequency_hz, expected_dB). Computed INDEPENDENTLY with 50-digit
# Decimal arithmetic from 20*log10(d_km) + 20*log10(f_MHz) + 32.44 — not by
# calling the code under test. Tolerance 1e-9 dB.
GOLDEN = [
    (1, 1e3, -87.56),
    (1, 100e9, 72.44),
    (10, 30e6, 21.9824250944),
    (1000, 2.4e9, 100.0442248342),
    (10007.5, 145.5e6, 95.7037718420),
    (1e5, 1e6, 72.44),
    (1e6, 100e9, 192.44),
    (1e6, 1e3, 32.44),
    (50, 433e6, 59.1491580138),
    (300, 868e6, 80.7528195979),
    (5000, 5.8e9, 121.6879599580),
    (2e4, 28e9, 147.4037605401),
    (1, 1e6, -27.56),
    (1000, 1e9, 92.44),
    (1e4, 10e9, 132.44),
    (1e5, 3e9, 141.9824250944),
    (1e6, 145.5e6, 135.6972598664),
    (250, 60e9, 115.9618251811),
    (7.5, 2.4e9, 57.5454501021),
    (3.6e7, 12e9, 205.1496749363),
    (1000, 3e5, 21.9824250944),
    (0.5, 1e9, 26.4194000867),
]


def test_golden_points_count() -> None:
    assert len(GOLDEN) >= 20


@pytest.mark.parametrize(("d", "f", "expected"), GOLDEN)
def test_golden_values(d: float, f: float, expected: float) -> None:
    assert free_space_path_loss_db(d, f) == pytest.approx(expected, abs=1e-9)


def test_spec_reference_case_10km_145_5mhz() -> None:
    # Architecture reference: 10 km @ 145.5 MHz = 95.6973 dB (+-0.001).
    assert free_space_path_loss_db(10_000.0, 145.5e6) == pytest.approx(95.6973, abs=1e-3)


@pytest.mark.parametrize(("d", "f", "_"), GOLDEN)
def test_consistent_with_exact_friis(d: float, f: float, _: float) -> None:
    # The rounded 32.44 constant differs from the exact one by < 0.008 dB.
    exact = 20.0 * math.log10(4.0 * math.pi * d * f / SPEED_OF_LIGHT_M_S)
    assert free_space_path_loss_db(d, f) == pytest.approx(exact, abs=0.008)


def test_max_error_vs_high_precision_reference() -> None:
    """Report the max error of the double-precision log10 form vs Decimal."""
    getcontext().prec = 60
    rng = random.Random(20260101)
    worst = 0.0
    for _ in range(5000):
        d = 10.0 ** rng.uniform(-3, 9)
        f = 10.0 ** rng.uniform(3, 11)
        ref = (
            20 * (Decimal(d) / 1000).log10()
            + 20 * (Decimal(f) / Decimal(10**6)).log10()
            + Decimal("32.44")
        )
        worst = max(worst, abs(free_space_path_loss_db(d, f) - float(ref)))
    print(f"\nMAX_NUMERIC_ERROR_DB={worst:.3e}")
    assert worst < 1e-12


def test_6db_per_distance_doubling_and_20db_per_decade() -> None:
    rng = random.Random(1)
    for _ in range(10_000):
        d = 10.0 ** rng.uniform(-3, 8)
        f = 10.0 ** rng.uniform(3, 11)
        base = free_space_path_loss_db(d, f)
        assert free_space_path_loss_db(2 * d, f) - base == pytest.approx(6.0206, abs=1e-4)
        assert free_space_path_loss_db(10 * d, f) - base == pytest.approx(20.0, abs=1e-9)
        assert free_space_path_loss_db(d, 2 * f) - base == pytest.approx(6.0206, abs=1e-4)
        assert free_space_path_loss_db(d, 10 * f) - base == pytest.approx(20.0, abs=1e-9)


def test_monotonic_in_distance_and_frequency() -> None:
    rng = random.Random(2)
    for _ in range(10_000):
        d = 10.0 ** rng.uniform(-3, 8)
        f = 10.0 ** rng.uniform(3, 11)
        k = 1.0 + rng.uniform(0.01, 5.0)
        assert free_space_path_loss_db(d * k, f) > free_space_path_loss_db(d, f)
        assert free_space_path_loss_db(d, f * k) > free_space_path_loss_db(d, f)


def test_symmetric_in_distance_frequency_swap() -> None:
    # The formula is symmetric in d[m] <-> f[Hz] numerics: FSPL(d,f) == FSPL(f,d).
    assert free_space_path_loss_db(1234.5, 98.7e6) == pytest.approx(
        free_space_path_loss_db(98.7e6, 1234.5), abs=1e-12
    )


@pytest.mark.parametrize("d", [5e-324, 1e-300, 1e300, 1.7976931348623157e308])
def test_extreme_finite_distances_stay_finite(d: float) -> None:
    value = free_space_path_loss_db(d, 1e9)
    assert math.isfinite(value)


@pytest.mark.parametrize("f", [5e-324, 1e-300, 1e-9, 1e18, 1e300])
def test_extreme_finite_frequencies_stay_finite(f: float) -> None:
    assert math.isfinite(free_space_path_loss_db(1000.0, f))


BAD = [0.0, -0.0, -1.0, -1e-300, math.nan, math.inf, -math.inf]


@pytest.mark.parametrize("bad", BAD)
def test_bad_distance_raises(bad: float) -> None:
    with pytest.raises(PhysicsInputError, match="distance_m"):
        free_space_path_loss_db(bad, 1e9)


@pytest.mark.parametrize("bad", BAD)
def test_bad_frequency_raises(bad: float) -> None:
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        free_space_path_loss_db(1000.0, bad)


@pytest.mark.parametrize("bad", ["10", None, [1.0], True])
def test_non_numeric_raises(bad: object) -> None:
    with pytest.raises(PhysicsInputError):
        free_space_path_loss_db(bad, 1e9)  # type: ignore[arg-type]


def test_near_field_raw_value_can_be_negative() -> None:
    # Documented: the raw formula is not clamped (the model clamps/floors).
    assert free_space_path_loss_db(1.0, 1e3) < 0.0
