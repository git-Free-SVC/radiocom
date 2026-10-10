"""ENUFrame API, numerical-safety guards and randomized accuracy for services/world."""

from __future__ import annotations

import dataclasses
import math
import random

import pytest

from libraries.domain.position import ENUPosition, GeoPosition
from services.world import (
    ENUFrame,
    ecef_to_geo,
    enu_to_geo,
    geo_to_ecef,
    geo_to_enu,
    line_of_sight,
)
from services.world.enu import _frame_for
from services.world.geodesy import ecef_to_geodetic_rad, geodetic_rad_to_ecef
from tests.contract.fakes.flat_geodata_provider import FlatGeodataProvider

ORIGIN = GeoPosition(45.0, 6.0, 1000.0)
DEG_TOL, ALT_TOL = 1e-9, 1e-6


def _random_positions(
    n: int, seed: int, lo: float = -500.0, hi: float = 12000.0
) -> list[GeoPosition]:
    rng = random.Random(seed)
    return [
        GeoPosition(rng.uniform(-80, 80), rng.uniform(-180, 180), rng.uniform(lo, hi))
        for _ in range(n)
    ]


class TestENUFrame:
    def test_matches_one_shot_functions_exactly(self) -> None:
        frame = ENUFrame(ORIGIN)
        for p in _random_positions(500, seed=1):
            assert frame.to_enu(p) == geo_to_enu(p, ORIGIN)
            enu = frame.to_enu(p)
            assert frame.to_geo(enu) == enu_to_geo(enu, ORIGIN)

    def test_batch_equals_single(self) -> None:
        frame = ENUFrame(ORIGIN)
        pts = _random_positions(300, seed=2)
        assert frame.to_enu_many(pts) == [frame.to_enu(p) for p in pts]
        enus = frame.to_enu_many(pts)
        assert frame.to_geo_many(enus) == [frame.to_geo(e) for e in enus]

    def test_batch_accepts_any_iterable_and_empty(self) -> None:
        frame = ENUFrame(ORIGIN)
        assert frame.to_enu_many([]) == []
        assert frame.to_enu_many(iter([ORIGIN])) == [ENUPosition(0.0, 0.0, 0.0)]

    def test_round_trip_through_a_reused_frame(self) -> None:
        rng = random.Random(3)
        frame = ENUFrame(ORIGIN)
        for _ in range(500):
            enu = ENUPosition(
                rng.uniform(-5e4, 5e4), rng.uniform(-5e4, 5e4), rng.uniform(-100, 3000)
            )
            back = frame.to_enu(frame.to_geo(enu))
            assert back.east_m == pytest.approx(enu.east_m, abs=1e-6)
            assert back.north_m == pytest.approx(enu.north_m, abs=1e-6)
            assert back.up_m == pytest.approx(enu.up_m, abs=1e-6)

    def test_is_immutable_and_compares_by_origin(self) -> None:
        frame = ENUFrame(ORIGIN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            frame.origin = GeoPosition(0.0, 0.0)  # type: ignore[misc]
        assert frame == ENUFrame(GeoPosition(45.0, 6.0, 1000.0))
        assert frame != ENUFrame(GeoPosition(45.0, 6.1, 1000.0))
        assert hash(frame) == hash(ENUFrame(ORIGIN))
        assert "origin" in repr(frame) and "_rot" not in repr(frame)

    def test_one_shot_functions_reuse_a_cached_frame(self) -> None:
        assert _frame_for(ORIGIN) is _frame_for(GeoPosition(45.0, 6.0, 1000.0))

    def test_axes_point_east_north_up(self) -> None:
        frame = ENUFrame(GeoPosition(10.0, 20.0, 0.0))
        east = frame.to_enu(GeoPosition(10.0, 20.001, 0.0))
        north = frame.to_enu(GeoPosition(10.001, 20.0, 0.0))
        up = frame.to_enu(GeoPosition(10.0, 20.0, 5.0))
        assert east.east_m > 100 and abs(east.north_m) < 0.01
        assert north.north_m > 100 and abs(north.east_m) < 0.01
        assert up.up_m == pytest.approx(5.0, abs=1e-6)


class TestRandomizedAccuracy:
    """Seeded sweeps: the 1e-12 rad early-exit must never cost accuracy."""

    @pytest.mark.parametrize(("lo", "hi"), [(-500.0, 12000.0), (-10000.0, 1_000_000.0)])
    def test_ecef_round_trip_sweep(self, lo: float, hi: float) -> None:
        for p in _random_positions(5000, seed=4, lo=lo, hi=hi):
            got = ecef_to_geo(*geo_to_ecef(p))
            assert abs(got.lat - p.lat) < DEG_TOL
            assert abs((got.lon - p.lon + 180.0) % 360.0 - 180.0) < DEG_TOL
            assert abs(got.alt_m - p.alt_m) < ALT_TOL

    @pytest.mark.parametrize("alt_m", [35_786_000.0, 384_400_000.0])
    def test_high_altitude_keeps_near_machine_precision(self, alt_m: float) -> None:
        # Geostationary and lunar distances. The spec only needs 1e-9 deg, but a
        # looser refinement threshold costs ~1e-12 deg here; pin the real precision.
        rng = random.Random(8)
        for _ in range(3000):
            p = GeoPosition(rng.uniform(-85, 85), rng.uniform(-180, 180), alt_m)
            got = ecef_to_geo(*geo_to_ecef(p))
            assert abs(got.lat - p.lat) < 1e-13
            assert abs(got.alt_m - p.alt_m) < 1e-5

    def test_points_extremely_close_to_the_poles(self) -> None:
        rng = random.Random(5)
        for _ in range(2000):
            sign = rng.choice((-1.0, 1.0))
            p = GeoPosition(
                sign * (90.0 - 10 ** rng.uniform(-9, -1)),
                rng.uniform(-180, 180),
                rng.uniform(0, 9000),
            )
            got = ecef_to_geo(*geo_to_ecef(p))
            assert abs(got.lat - p.lat) < DEG_TOL
            assert abs(got.alt_m - p.alt_m) < ALT_TOL

    def test_radian_level_api_agrees_with_geoposition_api(self) -> None:
        for p in _random_positions(200, seed=6):
            xyz = geodetic_rad_to_ecef(math.radians(p.lat), math.radians(p.lon), p.alt_m)
            assert xyz == geo_to_ecef(p)
            lat, lon, alt = ecef_to_geodetic_rad(*xyz)
            assert math.degrees(lat) == pytest.approx(p.lat, abs=DEG_TOL)
            assert abs((math.degrees(lon) - p.lon + 180.0) % 360.0 - 180.0) < DEG_TOL
            assert alt == pytest.approx(p.alt_m, abs=ALT_TOL)


class TestInverseTransformGuards:
    @pytest.mark.parametrize(
        "xyz",
        [
            (math.nan, 0.0, 0.0),
            (0.0, math.nan, 0.0),
            (0.0, 0.0, math.nan),
            (math.inf, 0.0, 0.0),
            (0.0, 0.0, -math.inf),
            (math.inf, -math.inf, 0.0),
        ],
    )
    def test_non_finite_input_is_rejected(self, xyz: tuple[float, float, float]) -> None:
        # Regression: clamping with min()/max() used to turn NaN into lat = 90.
        with pytest.raises(ValueError, match="finite"):
            ecef_to_geo(*xyz)

    def test_earth_centre_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="centre"):
            ecef_to_geo(0.0, 0.0, 0.0)

    def test_enu_to_geo_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            enu_to_geo(ENUPosition(math.nan, 0.0, 0.0), ORIGIN)

    def test_polar_axis_longitude_is_defined_as_zero(self) -> None:
        _, lon, _ = ecef_to_geodetic_rad(0.0, 0.0, 6_356_752.314245179)
        assert lon == 0.0

    def test_result_always_satisfies_geoposition_ranges(self) -> None:
        for p in (GeoPosition(90.0, 180.0, 0.0), GeoPosition(-90.0, -180.0, 0.0)):
            got = ecef_to_geo(*geo_to_ecef(p))
            assert -90.0 <= got.lat <= 90.0 and -180.0 <= got.lon <= 180.0


class TestLineOfSightSafety:
    A = GeoPosition(45.0, 6.0, 100.0)
    B = GeoPosition(45.2, 6.2, 100.0)

    @staticmethod
    def _provider(profile_fn):  # type: ignore[no-untyped-def]
        class P(FlatGeodataProvider):
            def elevation_profile(self, a, b, samples):  # type: ignore[no-untyped-def]
                return profile_fn(samples)

        return P()

    def test_all_nan_terrain_is_not_reported_clear(self) -> None:
        # Regression: nodata rasters arrive as NaN and nan < x is always False,
        # so the old min-search skipped every sample and returned clear=True.
        provider = self._provider(lambda n: [math.nan] * n)
        with pytest.raises(ValueError, match="missing data"):
            line_of_sight(self.A, self.B, provider)

    def test_single_nan_sample_is_not_skipped_and_is_named(self) -> None:
        provider = self._provider(lambda n: [0.0] * 7 + [math.nan] + [0.0] * (n - 8))
        with pytest.raises(ValueError, match=r"sample 7 of 32"):
            line_of_sight(self.A, self.B, provider)

    @pytest.mark.parametrize("bad", [math.inf, -math.inf])
    def test_infinite_elevation_rejected(self, bad: float) -> None:
        provider = self._provider(lambda n: [0.0, bad] + [0.0] * (n - 2))
        with pytest.raises(ValueError, match="sample 1"):
            line_of_sight(self.A, self.B, provider)

    def test_absurd_but_finite_elevations_are_rejected_not_misreported(self) -> None:
        provider = self._provider(lambda n: [1.7e308] * n)
        with pytest.raises(ValueError, match="too large"):
            line_of_sight(self.A, self.B, provider)

    @pytest.mark.parametrize("bad_alt", [math.nan, math.inf])
    def test_non_finite_endpoint_altitude_rejected(self, bad_alt: float) -> None:
        with pytest.raises(ValueError, match="altitudes must be finite"):
            line_of_sight(GeoPosition(45.0, 6.0, bad_alt), self.B, FlatGeodataProvider())
        with pytest.raises(ValueError, match="altitudes must be finite"):
            line_of_sight(self.A, GeoPosition(45.0, 6.0, bad_alt), FlatGeodataProvider())

    @pytest.mark.parametrize("samples", [32.0, "32", None, True])
    def test_non_int_samples_rejected(self, samples: object) -> None:
        with pytest.raises(TypeError, match="samples"):
            line_of_sight(self.A, self.B, FlatGeodataProvider(), samples=samples)  # type: ignore[arg-type]

    def test_worst_fraction_is_the_first_sample_on_ties(self) -> None:
        r = line_of_sight(self.A, self.B, FlatGeodataProvider())  # level line, flat ground
        assert r.worst_fraction == 0.0

    def test_two_samples_checks_exactly_the_endpoints(self) -> None:
        r = line_of_sight(self.A, self.B, self._provider(lambda n: [0.0, 150.0]), samples=2)
        assert r.clear is False
        assert r.min_clearance_m == pytest.approx(-50.0)
        assert r.worst_fraction == 1.0
