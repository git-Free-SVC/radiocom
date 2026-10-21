"""Category G of the stress campaign: regression tests.

Every test in this file locks in a defect that the stress campaign found (or
a numerical trap that it exposed). The rule of the campaign is that a defect
is never "fixed" by weakening a test: it gets a named regression test
instead.
"""

from __future__ import annotations

import math

import pytest

from libraries.domain.position import GeoPosition
from libraries.physics import (
    EARTH_MEAN_RADIUS_M,
    MIN_DISTANCE_M,
    dbm_from_watts,
    eb_n0_db,
    free_space_path_loss_db,
    haversine_distance_m,
    watts_from_dbm,
)


def test_regression_antipodal_distance_avoids_cancellation() -> None:
    """The classic ``2*asin(sqrt(hav))`` form loses ~0.19 m at the antipode.

    Evaluating the complementary term directly (``1 - hav`` without the
    subtraction) keeps the full precision: the antipodal distance comes out
    exact to within a micrometre.
    """
    a = GeoPosition(lat=10.0, lon=20.0)
    b = GeoPosition(lat=-10.0, lon=-160.0)  # the antipode of a
    expected = math.pi * EARTH_MEAN_RADIUS_M
    assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-6)

    # The naive form, for the record: it is 0.19 m short.
    phi_a, phi_b = math.radians(10.0), math.radians(-10.0)
    delta_lambda = math.radians(-180.0)
    hav = (
        math.sin((phi_b - phi_a) / 2.0) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2.0) ** 2
    )
    naive = 2.0 * EARTH_MEAN_RADIUS_M * math.asin(math.sqrt(hav))
    assert abs(naive - expected) > 0.1
    assert abs(haversine_distance_m(a, b) - expected) < 1e-6


def test_regression_poles_have_no_longitude_residue() -> None:
    """``cos(pi/2)`` is 6.1e-17, not 0: without the pole short-circuit two
    poles at different longitudes would be 8e-10 m apart."""
    north = GeoPosition(lat=90.0, lon=0.0)
    north_other = GeoPosition(lat=90.0, lon=137.0)
    assert haversine_distance_m(north, north_other) == 0.0


def test_regression_denormal_distance_does_not_underflow_before_log10() -> None:
    """Converting metres to kilometres first underflows a denormal distance to
    zero, which would make ``log10(0)`` raise. The logarithm is taken on the
    original unit and the unit change is applied to the logarithm."""
    denormal = 5.0e-324
    assert denormal / 1000.0 == 0.0  # the naive conversion really does vanish
    result = free_space_path_loss_db(denormal, 145.5e6)
    assert math.isfinite(result)
    assert result == pytest.approx(free_space_path_loss_db(MIN_DISTANCE_M, 145.5e6), abs=1e-9)


def test_regression_fspl_below_the_clamp_uses_the_clamped_distance() -> None:
    """Below 1 m the model substitutes the clamp: a caller must not mistake
    the clamped value for the value at its own distance."""
    at_clamp = free_space_path_loss_db(MIN_DISTANCE_M, 145.5e6)
    for below in (0.0, 1.0e-6, 0.5):
        assert free_space_path_loss_db(below, 145.5e6) == pytest.approx(at_clamp, abs=1e-12)


def test_regression_one_ulp_above_the_clamp_is_not_representable_in_db() -> None:
    """A relative distance change of 2e-16 is 8.7e-15 dB, below the
    resolution of the dB result: the value must stay finite and monotone,
    but it is not *strictly* larger."""
    at_clamp = free_space_path_loss_db(MIN_DISTANCE_M, 145.5e6)
    just_above = free_space_path_loss_db(math.nextafter(MIN_DISTANCE_M, math.inf), 145.5e6)
    assert math.isfinite(just_above)
    assert just_above >= at_clamp
    assert free_space_path_loss_db(MIN_DISTANCE_M * 1.0000001, 145.5e6) > at_clamp


def test_regression_eb_n0_ratio_does_not_overflow() -> None:
    """``bandwidth / bit_rate`` overflows to infinity for extreme but finite
    inputs; the difference of the two logarithms does not."""
    assert 1.0e300 / 1.0e-300 == float("inf")
    result = eb_n0_db(0.0, 1.0e300, 1.0e-300)
    assert math.isfinite(result)
    assert result == pytest.approx(10.0 * (300.0 + 300.0), abs=1e-6)


def test_regression_longitude_spacing_uses_the_exact_great_circle_form() -> None:
    """``R*cos(lat)*dlon`` is only an approximation (1.2e-5 relative at one
    degree); the exact form is ``2R*asin(cos(lat)*sin(dlon/2))``."""
    lat = 74.9
    a = GeoPosition(lat=lat, lon=0.0)
    b = GeoPosition(lat=lat, lon=1.0)
    exact = (
        2.0
        * EARTH_MEAN_RADIUS_M
        * math.asin(math.cos(math.radians(lat)) * math.sin(math.radians(1.0) / 2.0))
    )
    assert haversine_distance_m(a, b) == pytest.approx(exact, abs=1e-6)


def test_regression_watts_dbm_round_trip_keeps_ten_decades_of_precision() -> None:
    """The round trip must hold over the whole practical range of powers."""
    for power_watt in (1.0e-30, 1.0e-15, 1.0, 1.0e15, 1.0e30):
        restored = watts_from_dbm(dbm_from_watts(power_watt))
        assert restored == pytest.approx(power_watt, rel=1e-9)
