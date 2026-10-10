"""Unit tests for services/world (pure math + LOS stub; no I/O)."""

from __future__ import annotations

import math

import pytest

from libraries.domain.position import ENUPosition, GeoPosition
from services.world import (
    DEFAULT_SAMPLES,
    WGS84_A,
    WGS84_E2,
    WGS84_F,
    LOSResult,
    ecef_to_geo,
    enu_to_geo,
    geo_to_ecef,
    geo_to_enu,
    line_of_sight,
)
from tests.contract.fakes.flat_geodata_provider import FlatGeodataProvider

WGS84_B = WGS84_A * (1.0 - WGS84_F)
ORIGIN = GeoPosition(lat=45.0, lon=6.0, alt_m=1000.0)

# Round-trip tolerances (spec 5.3).
DEG_TOL = 1e-9
ALT_TOL = 1e-6


class TestForwardTransform:
    """Closed-form reference points (spec 5.1). cos(90 deg) is not exactly 0
    in double precision, so residuals around 1e-10 are expected."""

    def test_equator_prime_meridian(self) -> None:
        x, y, z = geo_to_ecef(GeoPosition(0.0, 0.0, 0.0))
        assert (x, y, z) == (
            pytest.approx(WGS84_A, abs=1e-9),
            pytest.approx(0.0, abs=1e-9),
            0.0,
        )
        assert x == 6378137.0

    def test_north_pole(self) -> None:
        x, y, z = geo_to_ecef(GeoPosition(90.0, 0.0, 0.0))
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(0.0, abs=1e-9)
        assert z == pytest.approx(WGS84_B, abs=1e-9)
        assert z == pytest.approx(6356752.314245179, abs=1e-9)

    def test_equator_90_east(self) -> None:
        x, y, z = geo_to_ecef(GeoPosition(0.0, 90.0, 0.0))
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(6378137.0, abs=1e-9)
        assert z == pytest.approx(0.0, abs=1e-9)

    def test_constants(self) -> None:
        assert WGS84_E2 == pytest.approx(0.00669437999014, rel=1e-12)

    def test_altitude_adds_along_the_normal(self) -> None:
        x, _, _ = geo_to_ecef(GeoPosition(0.0, 0.0, 250.0))
        assert x == pytest.approx(WGS84_A + 250.0, abs=1e-9)


class TestENUSanityCases:
    """Origin (45N, 6E, 1000 m) -- spec 5.2. Expected values are derived
    independently from ellipsoid radii of curvature, not from the code."""

    @staticmethod
    def _radii(lat_deg: float) -> tuple[float, float]:
        s2 = math.sin(math.radians(lat_deg)) ** 2
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * s2)
        m = WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * s2) ** 1.5
        return m, n

    def test_origin_relative_to_itself_is_zero(self) -> None:
        enu = geo_to_enu(ORIGIN, ORIGIN)
        assert (enu.east_m, enu.north_m, enu.up_m) == (0.0, 0.0, 0.0)

    def test_point_north(self) -> None:
        enu = geo_to_enu(GeoPosition(45.001, 6.0, 1000.0), ORIGIN)
        m, _ = self._radii(45.0)
        assert enu.east_m == pytest.approx(0.0, abs=0.005)
        assert enu.north_m == pytest.approx((m + 1000.0) * math.radians(0.001), abs=0.005)
        assert enu.north_m == pytest.approx(111.15, abs=0.01)
        assert enu.up_m == pytest.approx(0.0, abs=0.005)  # ~-1 mm of curvature drop

    def test_point_east(self) -> None:
        enu = geo_to_enu(GeoPosition(45.0, 6.001, 1000.0), ORIGIN)
        _, n = self._radii(45.0)
        expected = (n + 1000.0) * math.cos(math.radians(45.0)) * math.radians(0.001)
        assert enu.east_m == pytest.approx(expected, abs=0.005)
        assert enu.east_m == pytest.approx(78.86, abs=0.01)
        assert enu.north_m == pytest.approx(0.0, abs=0.005)

    def test_point_above(self) -> None:
        enu = geo_to_enu(GeoPosition(45.0, 6.0, 1050.0), ORIGIN)
        assert enu.east_m == pytest.approx(0.0, abs=1e-6)
        assert enu.north_m == pytest.approx(0.0, abs=1e-6)
        assert enu.up_m == pytest.approx(50.0, abs=1e-6)


#: The seven round-trip points from spec 5.3.
ROUND_TRIP_POINTS = {
    "equator": GeoPosition(0.0, 0.0, 0.0),
    "mid_latitude": GeoPosition(45.0, 6.0, 1000.0),
    "sydney": GeoPosition(-33.8688, 151.2093, 58.0),
    "reykjavik": GeoPosition(64.1466, -21.9426, 15.0),
    "near_north_pole": GeoPosition(89.9999, 45.0, 100.0),
    "near_south_pole": GeoPosition(-89.9999, -120.0, 50.0),
    "antimeridian_everest_alt": GeoPosition(27.9881, 179.9999, 8848.86),
}


def _assert_same(got: GeoPosition, want: GeoPosition) -> None:
    dlon = abs((got.lon - want.lon + 180.0) % 360.0 - 180.0)  # wrap-safe
    assert abs(got.lat - want.lat) < DEG_TOL
    assert dlon < DEG_TOL
    assert abs(got.alt_m - want.alt_m) < ALT_TOL


def _nearby_origin(p: GeoPosition) -> GeoPosition:
    """An origin ~100 m from ``p`` (same hemisphere/region)."""
    lat = p.lat - 0.001 if p.lat > 0 else p.lat + 0.001
    return GeoPosition(lat, p.lon, p.alt_m + 10.0)


class TestRoundTrip:
    @pytest.mark.parametrize("name", ROUND_TRIP_POINTS)
    def test_geo_ecef_geo(self, name: str) -> None:
        p = ROUND_TRIP_POINTS[name]
        _assert_same(ecef_to_geo(*geo_to_ecef(p)), p)

    @pytest.mark.parametrize("name", ROUND_TRIP_POINTS)
    def test_geo_enu_geo_nearby_origin(self, name: str) -> None:
        p = ROUND_TRIP_POINTS[name]
        origin = _nearby_origin(p)
        _assert_same(enu_to_geo(geo_to_enu(p, origin), origin), p)

    @pytest.mark.parametrize("name", ROUND_TRIP_POINTS)
    def test_geo_enu_geo_own_origin(self, name: str) -> None:
        p = ROUND_TRIP_POINTS[name]
        enu = geo_to_enu(p, p)
        assert (enu.east_m, enu.north_m, enu.up_m) == (0.0, 0.0, 0.0)
        _assert_same(enu_to_geo(enu, p), p)

    @pytest.mark.parametrize("name", [n for n in ROUND_TRIP_POINTS if "pole" not in n])
    def test_geo_enu_geo_distant_origin(self, name: str) -> None:
        p = ROUND_TRIP_POINTS[name]
        _assert_same(enu_to_geo(geo_to_enu(p, ORIGIN), ORIGIN), p)

    def test_enu_geo_enu(self) -> None:
        enu = ENUPosition(east_m=1234.5, north_m=-987.6, up_m=42.0)
        back = geo_to_enu(enu_to_geo(enu, ORIGIN), ORIGIN)
        assert back.east_m == pytest.approx(enu.east_m, abs=1e-6)
        assert back.north_m == pytest.approx(enu.north_m, abs=1e-6)
        assert back.up_m == pytest.approx(enu.up_m, abs=1e-6)


class TestNearPole:
    @pytest.mark.parametrize("lat", [89.999, -89.999, 89.999999])
    @pytest.mark.parametrize("lon", [-180.0, -90.0, 0.0, 33.3, 179.999])
    def test_round_trip_close_to_pole(self, lat: float, lon: float) -> None:
        p = GeoPosition(lat, lon, 500.0)
        got = ecef_to_geo(*geo_to_ecef(p))
        _assert_same(got, p)

    def test_exactly_at_pole_does_not_crash(self) -> None:
        # Longitude is mathematically undefined at the pole: only demand sanity.
        for lat in (90.0, -90.0):
            got = ecef_to_geo(*geo_to_ecef(GeoPosition(lat, 77.0, 123.0)))
            assert got.lat == pytest.approx(lat, abs=1e-9)
            assert got.alt_m == pytest.approx(123.0, abs=1e-6)
            assert -180.0 <= got.lon <= 180.0

    def test_enu_near_pole_with_nearby_origin(self) -> None:
        origin = GeoPosition(89.999, 10.0, 0.0)
        p = GeoPosition(89.9991, -170.0, 20.0)
        _assert_same(enu_to_geo(geo_to_enu(p, origin), origin), p)

    def test_returned_position_is_always_valid(self) -> None:
        # GeoPosition validates ranges; last-ulp overshoot must never raise.
        for lat in (90.0, -90.0, 89.9999999999):
            ecef_to_geo(*geo_to_ecef(GeoPosition(lat, 180.0, 0.0)))


class WallGeodataProvider(FlatGeodataProvider):
    """Reuses the shared flat fake, but with a wall of terrain between 40% and
    60% of any path -- proves obstruction detection is not vacuous."""

    def __init__(self, wall_height_m: float = 500.0) -> None:
        super().__init__()
        self.wall_height_m = wall_height_m

    def elevation_profile(self, a: GeoPosition, b: GeoPosition, samples: int) -> list[float]:
        return [
            self.wall_height_m if 0.4 <= i / (samples - 1) <= 0.6 else 0.0 for i in range(samples)
        ]


class TestLineOfSight:
    A = GeoPosition(45.0, 6.0, 10.0)
    B = GeoPosition(45.1, 6.1, 10.0)

    def test_flat_terrain_is_clear(self) -> None:
        r = line_of_sight(self.A, self.B, FlatGeodataProvider())
        assert isinstance(r, LOSResult)
        assert r.clear is True
        assert r.min_clearance_m == pytest.approx(10.0)
        assert r.samples == DEFAULT_SAMPLES == 32

    def test_wall_obstructs_and_clearance_is_negative(self) -> None:
        r = line_of_sight(self.A, self.B, WallGeodataProvider(500.0))
        assert r.clear is False
        assert r.min_clearance_m == pytest.approx(10.0 - 500.0)
        assert r.min_clearance_m < 0
        assert 0.4 <= r.worst_fraction <= 0.6

    def test_wall_lower_than_line_is_clear(self) -> None:
        r = line_of_sight(self.A, self.B, WallGeodataProvider(5.0))
        assert r.clear is True
        assert r.min_clearance_m == pytest.approx(5.0)

    def test_touching_terrain_counts_as_clear(self) -> None:
        r = line_of_sight(self.A, self.B, WallGeodataProvider(10.0))
        assert r.clear is True
        assert r.min_clearance_m == pytest.approx(0.0)

    def test_identical_points_are_trivially_clear(self) -> None:
        r = line_of_sight(self.A, self.A, FlatGeodataProvider())
        assert r.clear is True
        assert r.min_clearance_m == pytest.approx(10.0)

    def test_different_altitudes_clear_over_flat_terrain(self) -> None:
        lo = GeoPosition(45.0, 6.0, 20.0)
        hi = GeoPosition(45.1, 6.1, 900.0)
        r = line_of_sight(lo, hi, FlatGeodataProvider())
        assert r.clear is True
        assert r.min_clearance_m == pytest.approx(20.0)  # at the low end, t = 0
        assert r.worst_fraction == 0.0

    def test_sloped_line_can_clear_a_wall_a_level_line_would_not(self) -> None:
        lo = GeoPosition(45.0, 6.0, 10.0)
        hi = GeoPosition(45.1, 6.1, 2000.0)
        assert line_of_sight(lo, hi, WallGeodataProvider(500.0)).clear is True  # 10+0.4*1990 > 500
        assert line_of_sight(lo, lo, WallGeodataProvider(500.0)).clear is False

    def test_endpoint_below_ground_is_obstructed_over_flat_terrain(self) -> None:
        r = line_of_sight(GeoPosition(45.0, 6.0, -5.0), self.B, FlatGeodataProvider())
        assert r.clear is False
        assert r.min_clearance_m == pytest.approx(-5.0)

    def test_samples_parameter_is_used(self) -> None:
        r = line_of_sight(self.A, self.B, FlatGeodataProvider(), samples=5)
        assert r.samples == 5

    @pytest.mark.parametrize("samples", [1, 0, -3])
    def test_too_few_samples_rejected(self, samples: int) -> None:
        with pytest.raises(ValueError, match="samples"):
            line_of_sight(self.A, self.B, FlatGeodataProvider(), samples=samples)

    def test_provider_returning_wrong_length_rejected(self) -> None:
        class Broken(FlatGeodataProvider):
            def elevation_profile(self, a, b, samples):  # type: ignore[no-untyped-def]
                return [0.0] * (samples - 1)

        with pytest.raises(ValueError, match="expected"):
            line_of_sight(self.A, self.B, Broken())

    def test_result_is_frozen(self) -> None:
        r = line_of_sight(self.A, self.B, FlatGeodataProvider())
        with pytest.raises(AttributeError):
            r.clear = False  # type: ignore[misc]
