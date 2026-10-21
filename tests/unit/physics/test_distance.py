"""Unit tests for the reusable distance helpers.

Covers the surface (haversine) distance, the 3D slant range and the input
validation contract of :mod:`libraries.physics.distance`.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from libraries.domain.position import GeoPosition
from libraries.physics import (
    EARTH_MEAN_RADIUS_M,
    PhysicsInputError,
    haversine_distance_m,
    slant_range_m,
)

# One degree of latitude on the mean-radius sphere.
ONE_DEGREE_M = EARTH_MEAN_RADIUS_M * math.pi / 180.0


def test_contract_fixture_distance_is_ten_kilometres_north() -> None:
    """The frozen contract fixture places RX 0.09 degrees north of TX."""
    tx = GeoPosition(lat=45.0, lon=6.0)
    rx = GeoPosition(lat=45.09, lon=6.0)
    assert haversine_distance_m(tx, rx) == pytest.approx(10_007.5, abs=1.0)


def test_one_degree_of_latitude_is_about_111_km() -> None:
    equator = GeoPosition(lat=0.0, lon=0.0)
    one_degree_north = GeoPosition(lat=1.0, lon=0.0)
    assert haversine_distance_m(equator, one_degree_north) == pytest.approx(111_194.93, abs=0.01)
    assert ONE_DEGREE_M == pytest.approx(111_194.93, abs=0.01)


def test_surface_distance_ignores_altitude() -> None:
    low = GeoPosition(lat=45.0, lon=6.0, alt_m=0.0)
    high = GeoPosition(lat=45.09, lon=6.0, alt_m=1000.0)
    assert haversine_distance_m(low, high) == haversine_distance_m(low, GeoPosition(45.09, 6.0))


def test_identical_points_have_zero_distance() -> None:
    point = GeoPosition(lat=12.5, lon=-33.25, alt_m=500.0)
    assert haversine_distance_m(point, point) == 0.0


def test_antimeridian_crossing_takes_the_short_way_round() -> None:
    east = GeoPosition(lat=0.0, lon=179.999)
    west = GeoPosition(lat=0.0, lon=-179.999)
    expected = 2.0 * math.pi * EARTH_MEAN_RADIUS_M / 180_000.0
    assert haversine_distance_m(east, west) == pytest.approx(expected, abs=1e-6)


def test_antipodal_points_are_half_the_earth_circumference() -> None:
    a = GeoPosition(lat=0.0, lon=0.0)
    b = GeoPosition(lat=0.0, lon=180.0)
    assert haversine_distance_m(a, b) == pytest.approx(math.pi * EARTH_MEAN_RADIUS_M, abs=1e-7)


@pytest.mark.parametrize("lat", [-90.0, 90.0])
def test_every_longitude_is_the_same_point_at_the_poles(lat: float) -> None:
    assert (
        haversine_distance_m(GeoPosition(lat=lat, lon=-180.0), GeoPosition(lat=lat, lon=73.0))
        == 0.0
    )


def test_slant_range_equals_surface_distance_at_equal_altitude() -> None:
    a = GeoPosition(lat=45.0, lon=6.0, alt_m=350.0)
    b = GeoPosition(lat=45.09, lon=6.0, alt_m=350.0)
    assert slant_range_m(a, b) == pytest.approx(haversine_distance_m(a, b), abs=1e-9)


def test_slant_range_follows_pythagoras() -> None:
    a = GeoPosition(lat=45.0, lon=6.0, alt_m=120.0)
    b = GeoPosition(lat=45.09, lon=6.0, alt_m=170.0)
    surface = haversine_distance_m(a, b)
    assert slant_range_m(a, b) == pytest.approx(math.hypot(surface, 50.0), abs=1e-9)


def test_slant_range_is_symmetric() -> None:
    a = GeoPosition(lat=45.0, lon=6.0, alt_m=120.0)
    b = GeoPosition(lat=45.09, lon=6.0, alt_m=170.0)
    assert slant_range_m(a, b) == slant_range_m(b, a)


def test_slant_range_of_identical_lat_lon_with_different_altitudes_is_the_altitude_gap() -> None:
    low = GeoPosition(lat=45.0, lon=6.0, alt_m=0.0)
    high = GeoPosition(lat=45.0, lon=6.0, alt_m=500.0)
    assert slant_range_m(low, high) == pytest.approx(500.0, abs=1e-9)
    assert haversine_distance_m(low, high) == 0.0


def test_large_and_negative_finite_altitudes_are_supported() -> None:
    base = GeoPosition(lat=0.0, lon=0.0, alt_m=0.0)
    high = GeoPosition(lat=0.0, lon=0.0, alt_m=1.0e300)
    low = GeoPosition(lat=0.0, lon=0.0, alt_m=-100.0)
    assert slant_range_m(base, high) == pytest.approx(1.0e300, rel=1e-15)
    assert slant_range_m(base, low) == pytest.approx(100.0, abs=1e-9)


@pytest.mark.parametrize(
    ("position", "message", "swapped_message"),
    [
        (SimpleNamespace(lat=91.0, lon=0.0, alt_m=0.0), "a.lat", "b.lat"),
        (SimpleNamespace(lat=-90.5, lon=0.0, alt_m=0.0), "a.lat", "b.lat"),
        (SimpleNamespace(lat=0.0, lon=180.5, alt_m=0.0), "a.lon", "b.lon"),
        (SimpleNamespace(lat=0.0, lon=-180.5, alt_m=0.0), "a.lon", "b.lon"),
    ],
)
def test_out_of_range_coordinates_are_rejected(
    position, message: str, swapped_message: str
) -> None:
    """The frozen ``GeoPosition`` already rejects these, but the physics layer
    must not rely on that: it validates its own inputs."""
    valid = GeoPosition(lat=0.0, lon=0.0)
    with pytest.raises(PhysicsInputError, match=message):
        haversine_distance_m(position, valid)
    with pytest.raises(PhysicsInputError, match=swapped_message):
        haversine_distance_m(valid, position)


def test_non_finite_altitude_is_rejected() -> None:
    valid = GeoPosition(lat=0.0, lon=0.0)
    with pytest.raises(PhysicsInputError, match="a.alt_m"):
        haversine_distance_m(GeoPosition(lat=0.0, lon=0.0, alt_m=float("nan")), valid)
    with pytest.raises(PhysicsInputError, match="b.alt_m"):
        haversine_distance_m(valid, GeoPosition(lat=0.0, lon=0.0, alt_m=float("inf")))


def test_altitude_difference_overflow_is_reported_as_a_physics_error() -> None:
    a = GeoPosition(lat=0.0, lon=0.0, alt_m=1.0e308)
    b = GeoPosition(lat=0.0, lon=0.0, alt_m=-1.0e308)
    with pytest.raises(PhysicsInputError, match="altitude difference"):
        slant_range_m(a, b)


def test_non_position_argument_is_rejected() -> None:
    with pytest.raises(PhysicsInputError, match="a must be a GeoPosition"):
        haversine_distance_m(None, GeoPosition(lat=0.0, lon=0.0))  # type: ignore[arg-type]
