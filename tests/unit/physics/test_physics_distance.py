"""Haversine surface distance and slant range."""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import pytest

from libraries.domain.position import GeoPosition
from libraries.physics.constants import EARTH_MEAN_RADIUS_M
from libraries.physics.distance import haversine_distance_m, slant_range_m
from libraries.physics.errors import PhysicsInputError

"""Haversine surface distance and slant range."""

ONE_DEGREE_M = math.pi * EARTH_MEAN_RADIUS_M / 180.0  # ~111194.9 m


def P(lat: float, lon: float, alt: float = 0.0) -> GeoPosition:
    return GeoPosition(lat=lat, lon=lon, alt_m=alt)


def raw(lat: object, lon: object, alt: object = 0.0) -> SimpleNamespace:
    """A position-like object that bypasses ``GeoPosition`` validation.

    The foundation's ``GeoPosition`` already rejects bad lat/lon at construction, so the
    physics functions' own validation (defence in depth, and for duck-typed callers) can only
    be exercised with an object that never went through that check.
    """
    return SimpleNamespace(lat=lat, lon=lon, alt_m=alt)


def test_contract_fixture_distance() -> None:
    d = haversine_distance_m(P(45.0, 6.0), P(45.09, 6.0))
    assert d == pytest.approx(10_007.5, abs=1.0)


def test_identical_points_zero() -> None:
    assert haversine_distance_m(P(12.3, 45.6), P(12.3, 45.6)) == 0.0


def test_one_degree_latitude() -> None:
    d = haversine_distance_m(P(0.0, 0.0), P(1.0, 0.0))
    assert d == pytest.approx(111_194.9, abs=1.0)
    assert d == pytest.approx(ONE_DEGREE_M, rel=1e-12)


def test_longitude_shrinks_with_cos_lat() -> None:
    for lat in (0.0, 30.0, 60.0, 80.0):
        d = haversine_distance_m(P(lat, 0.0), P(lat, 1.0))
        assert d == pytest.approx(ONE_DEGREE_M * math.cos(math.radians(lat)), rel=2e-4)


def test_antipodal_is_half_circumference_no_nan() -> None:
    d = haversine_distance_m(P(0.0, 0.0), P(0.0, 180.0))
    assert d == pytest.approx(math.pi * EARTH_MEAN_RADIUS_M, rel=1e-12)
    d2 = haversine_distance_m(P(45.0, 10.0), P(-45.0, -170.0))
    assert math.isfinite(d2)
    assert d2 == pytest.approx(math.pi * EARTH_MEAN_RADIUS_M, rel=1e-9)


def test_antimeridian_crossing() -> None:
    d = haversine_distance_m(P(0.0, 179.5), P(0.0, -179.5))
    assert d == pytest.approx(ONE_DEGREE_M, rel=1e-9)


def test_poles_independent_of_longitude() -> None:
    assert haversine_distance_m(P(90.0, 0.0), P(90.0, 123.0)) == pytest.approx(0.0, abs=1e-6)
    d = haversine_distance_m(P(90.0, 0.0), P(-90.0, 77.0))
    assert d == pytest.approx(math.pi * EARTH_MEAN_RADIUS_M, rel=1e-12)


def _rand_point(rng: random.Random) -> GeoPosition:
    return P(rng.uniform(-90, 90), rng.uniform(-180, 180), rng.uniform(-500, 40_000))


def test_symmetry_and_triangle_inequality() -> None:
    rng = random.Random(3)
    for _ in range(10_000):
        a, b, c = _rand_point(rng), _rand_point(rng), _rand_point(rng)
        ab = haversine_distance_m(a, b)
        assert ab == pytest.approx(haversine_distance_m(b, a), abs=1e-6)
        assert 0.0 <= ab <= math.pi * EARTH_MEAN_RADIUS_M + 1e-6
        assert ab <= haversine_distance_m(a, c) + haversine_distance_m(c, b) + 1e-6


@pytest.mark.parametrize("lat", [91.0, -91.0, 90.0000001, math.nan, math.inf, -math.inf])
def test_bad_latitude(lat: float) -> None:
    with pytest.raises(PhysicsInputError, match="lat"):
        haversine_distance_m(raw(lat, 0.0), raw(0.0, 0.0))
    with pytest.raises(PhysicsInputError, match="lat"):
        haversine_distance_m(raw(0.0, 0.0), raw(lat, 0.0))


@pytest.mark.parametrize("lon", [181.0, -181.0, 180.0001, math.nan, math.inf, -math.inf])
def test_bad_longitude(lon: float) -> None:
    with pytest.raises(PhysicsInputError, match="lon"):
        haversine_distance_m(raw(0.0, lon), raw(0.0, 0.0))


def test_non_numeric_coordinate() -> None:
    with pytest.raises(PhysicsInputError):
        haversine_distance_m(raw("a", 0.0), raw(0.0, 0.0))


# ----------------------------- slant range --------------------------------
def test_slant_equals_haversine_at_equal_altitude() -> None:
    a, b = P(45.0, 6.0, 120.0), P(45.09, 6.0, 120.0)
    assert slant_range_m(a, b) == pytest.approx(haversine_distance_m(a, b), abs=1e-9)


def test_slant_pythagoras() -> None:
    a, b = P(45.0, 6.0, 0.0), P(45.09, 6.0, 3000.0)
    s = haversine_distance_m(a, b)
    assert slant_range_m(a, b) == pytest.approx(math.hypot(s, 3000.0), rel=1e-12)


def test_slant_same_latlon_different_altitude_is_not_degenerate() -> None:
    assert slant_range_m(P(10.0, 20.0, 0.0), P(10.0, 20.0, 1000.0)) == pytest.approx(1000.0)


def test_slant_symmetric_and_ge_surface() -> None:
    rng = random.Random(4)
    for _ in range(10_000):
        a, b = _rand_point(rng), _rand_point(rng)
        assert slant_range_m(a, b) == pytest.approx(slant_range_m(b, a), rel=1e-12, abs=1e-9)
        assert slant_range_m(a, b) >= haversine_distance_m(a, b) - 1e-9


@pytest.mark.parametrize("alt", [math.nan, math.inf, -math.inf])
def test_slant_bad_altitude(alt: float) -> None:
    with pytest.raises(PhysicsInputError, match="alt_m"):
        slant_range_m(P(0.0, 0.0, alt), P(0.0, 0.0, 0.0))


def test_slant_altitude_difference_overflow() -> None:
    with pytest.raises(PhysicsInputError):
        slant_range_m(P(0.0, 0.0, 1e308), P(0.0, 0.0, -1e308))


def test_slant_huge_altitude_still_finite() -> None:
    assert math.isfinite(slant_range_m(P(0.0, 0.0, 1e300), P(0.0, 0.0, 0.0)))


@pytest.mark.parametrize(
    ("lat", "lon"), [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (math.nan, 0.0), (0.0, math.inf)]
)
def test_foundation_or_physics_rejects_bad_coordinates(lat: float, lon: float) -> None:
    """Whoever validates first wins: the foundation type, or this module. Never a number."""
    try:
        bad = P(lat, lon)
    except (ValueError, TypeError):
        return  # GeoPosition refused it at construction
    with pytest.raises(PhysicsInputError):
        haversine_distance_m(bad, P(0.0, 0.0))
