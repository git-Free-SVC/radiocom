"""Unit tests for the free-space path-loss formula.

The reference values come from the architecture doc §24 ("10 km @ 145.5 MHz
~ 95.7 dB") and from an independent 60-digit ``decimal`` computation, not
from the implementation under test.
"""

from __future__ import annotations

import math

import pytest

from libraries.physics import (
    FSPL_CONSTANT_DB,
    MIN_DISTANCE_M,
    PhysicsInputError,
    free_space_path_loss_db,
)


def test_reference_case_ten_kilometres_at_145_5_megahertz() -> None:
    """Task brief §5.1: FSPL(10 km, 145.5 MHz) == 95.6973 dB +/- 0.001."""
    assert free_space_path_loss_db(10_000.0, 145.5e6) == pytest.approx(95.6973, abs=0.001)


def test_reference_case_at_the_contract_fixture_distance() -> None:
    """The contract fixture is 10 007.5 m apart, not exactly 10 km.

    Kept as a separate test on purpose: 10 km and 10 007.5 m are ~0.007 dB
    apart, and conflating them hides a real (if small) difference.
    """
    assert free_space_path_loss_db(10_007.5, 145.5e6) == pytest.approx(95.7038, abs=0.001)


def test_fspl_follows_the_textbook_form() -> None:
    distance_km = 12.5
    frequency_mhz = 900.0
    expected = 20.0 * math.log10(distance_km) + 20.0 * math.log10(frequency_mhz) + FSPL_CONSTANT_DB
    assert free_space_path_loss_db(distance_km * 1000.0, frequency_mhz * 1.0e6) == pytest.approx(
        expected, abs=1e-9
    )


def test_doubling_the_distance_adds_6_0206_db() -> None:
    base = free_space_path_loss_db(1_000.0, 145.5e6)
    assert free_space_path_loss_db(2_000.0, 145.5e6) - base == pytest.approx(
        6.020599913279624, abs=1e-9
    )


def test_ten_folding_the_distance_adds_20_db() -> None:
    base = free_space_path_loss_db(1_000.0, 145.5e6)
    assert free_space_path_loss_db(10_000.0, 145.5e6) - base == pytest.approx(20.0, abs=1e-9)


def test_doubling_the_frequency_adds_6_0206_db() -> None:
    base = free_space_path_loss_db(1_000.0, 145.5e6)
    assert free_space_path_loss_db(1_000.0, 291.0e6) - base == pytest.approx(
        6.020599913279624, abs=1e-9
    )


def test_ten_folding_the_frequency_adds_20_db() -> None:
    base = free_space_path_loss_db(1_000.0, 145.5e6)
    assert free_space_path_loss_db(1_000.0, 1.455e9) - base == pytest.approx(20.0, abs=1e-9)


def test_path_loss_increases_with_distance_and_frequency() -> None:
    assert free_space_path_loss_db(2_000.0, 145.5e6) > free_space_path_loss_db(1_000.0, 145.5e6)
    assert free_space_path_loss_db(1_000.0, 291.0e6) > free_space_path_loss_db(1_000.0, 145.5e6)


def test_distance_is_clamped_to_one_metre() -> None:
    """Co-located radios are degenerate but legal: 20*log10(0) is undefined."""
    assert MIN_DISTANCE_M == 1.0
    at_floor = free_space_path_loss_db(1.0, 145.5e6)
    assert free_space_path_loss_db(0.0, 145.5e6) == pytest.approx(at_floor, abs=1e-12)
    assert free_space_path_loss_db(0.5, 145.5e6) == pytest.approx(at_floor, abs=1e-12)
    assert free_space_path_loss_db(math.nextafter(1.0, 0.0), 145.5e6) == pytest.approx(
        at_floor, abs=1e-12
    )
    # One ULP above the clamp is *not* representable in the dB result: a
    # relative distance change of 2e-16 is only 8.7e-15 dB, below the
    # resolution of a ~15.7 dB float. The value must stay finite and
    # monotone, not necessarily strictly larger.
    just_above = free_space_path_loss_db(math.nextafter(1.0, math.inf), 145.5e6)
    assert just_above >= at_floor
    assert math.isfinite(just_above)
    assert free_space_path_loss_db(1.0000001, 145.5e6) > at_floor


def test_the_clamp_is_configurable() -> None:
    assert free_space_path_loss_db(0.0, 145.5e6, min_distance_m=10.0) == pytest.approx(
        free_space_path_loss_db(10.0, 145.5e6), abs=1e-12
    )


def test_raw_path_loss_can_be_negative_in_the_near_field() -> None:
    """Below ``c/(4*pi)`` the formula is outside its validity: it is the
    model's job to floor the result, not this function's."""
    assert free_space_path_loss_db(1.0, 1.0e3) < 0.0


def test_negative_distance_is_rejected() -> None:
    with pytest.raises(PhysicsInputError, match="distance_m"):
        free_space_path_loss_db(-1.0, 145.5e6)


@pytest.mark.parametrize("frequency", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_frequency_is_rejected(frequency: float) -> None:
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        free_space_path_loss_db(1_000.0, frequency)


def test_invalid_clamp_is_rejected() -> None:
    with pytest.raises(PhysicsInputError, match="min_distance_m"):
        free_space_path_loss_db(1_000.0, 145.5e6, min_distance_m=0.0)
