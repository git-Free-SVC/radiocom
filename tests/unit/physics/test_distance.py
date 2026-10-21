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


def test_contract_fixture_haversine_distance() -> None:
    a = GeoPosition(lat=45.0, lon=6.0)
    b = GeoPosition(lat=45.09, lon=6.0)
    assert haversine_distance_m(a, b) == pytest.approx(10_007.5, abs=1.0)


def test_haversine_known_spherical_distances() -> None:
    equator = GeoPosition(lat=0.0, lon=0.0)
    one_degree_north = GeoPosition(lat=1.0, lon=0.0)
    assert haversine_distance_m(equator, one_degree_north) == pytest.approx(111_194.9266, abs=0.001)
    assert haversine_distance_m(
        GeoPosition(lat=0.0, lon=179.999), GeoPosition(lat=0.0, lon=-179.999)
    ) == pytest.approx(2.0 * math.pi * EARTH_MEAN_RADIUS_M / 180_000.0, abs=1e-6)


def test_antipodal_distance_and_poles_are_stable() -> None:
    a = GeoPosition(lat=0.0, lon=0.0)
    antipode = GeoPosition(lat=0.0, lon=180.0)
    assert haversine_distance_m(a, antipode) == pytest.approx(
        math.pi * EARTH_MEAN_RADIUS_M, abs=1e-7
    )
    assert (
        haversine_distance_m(GeoPosition(lat=90.0, lon=-180.0), GeoPosition(lat=90.0, lon=73.0))
        == 0.0
    )
    assert (
        haversine_distance_m(GeoPosition(lat=-90.0, lon=-180.0), GeoPosition(lat=-90.0, lon=73.0))
        == 0.0
    )


def test_slant_range_uses_altitude_delta() -> None:
    a = GeoPosition(lat=45.0, lon=6.0, alt_m=120.0)
    b = GeoPosition(lat=45.09, lon=6.0, alt_m=170.0)
    surface = haversine_distance_m(a, b)
    assert slant_range_m(a, b) == pytest.approx(math.hypot(surface, -50.0), abs=1e-9)
    assert slant_range_m(a, b) == slant_range_m(b, a)
    same_height = GeoPosition(lat=b.lat, lon=b.lon, alt_m=a.alt_m)
    assert slant_range_m(a, same_height) == pytest.approx(
        haversine_distance_m(a, same_height), abs=1e-9
    )


@pytest.mark.parametrize(
    ("position", "message"),
    [
        (SimpleNamespace(lat=91.0, lon=0.0, alt_m=0.0), "a.lat"),
        (SimpleNamespace(lat=0.0, lon=181.0, alt_m=0.0), "a.lon"),
        (SimpleNamespace(lat=float("nan"), lon=0.0, alt_m=0.0), "a.lat"),
        (SimpleNamespace(lat=0.0, lon=0.0, alt_m=float("inf")), "a.alt_m"),
    ],
)
def test_haversine_rejects_invalid_position_values(position, message: str) -> None:
    valid = GeoPosition(lat=0.0, lon=0.0)
    with pytest.raises(PhysicsInputError, match=message):
        haversine_distance_m(position, valid)


def test_slant_range_reports_altitude_subtraction_overflow() -> None:
    a = GeoPosition(lat=0.0, lon=0.0, alt_m=1.0e308)
    b = GeoPosition(lat=0.0, lon=0.0, alt_m=-1.0e308)
    with pytest.raises(PhysicsInputError, match="altitude difference"):
        slant_range_m(a, b)


def test_large_and_negative_finite_altitudes_are_supported() -> None:
    a = GeoPosition(lat=0.0, lon=0.0, alt_m=1.0e300)
    b = GeoPosition(lat=0.0, lon=0.0, alt_m=0.0)
    assert slant_range_m(a, b) == pytest.approx(1.0e300, rel=1e-15)
    assert slant_range_m(GeoPosition(lat=0.0, lon=0.0, alt_m=-100.0), b) == 100.0
