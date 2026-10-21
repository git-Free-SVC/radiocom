"""Category B of the stress campaign: invariants of the physics package.

Each property is checked on at least 10 000 seeded random cases. The seed is
fixed so a failure is always reproducible (``random.Random(1234)`` and
friends — ``hypothesis`` is not a dependency of this project and
``pyproject.toml`` is off-limits for this ticket).
"""

from __future__ import annotations

import itertools
import math
import random

import pytest

from libraries.domain.position import GeoPosition
from libraries.domain.rf_results import LinkBudgetInput, LinkQuality
from libraries.physics import (
    EARTH_MEAN_RADIUS_M,
    dbm_from_watts,
    eb_n0_db,
    free_space_path_loss_db,
    haversine_distance_m,
    link_margin_db,
    link_quality,
    noise_floor_dbm,
    received_power_dbm,
    slant_range_m,
    snr_db,
    watts_from_dbm,
)

CASES = 10_000
LOSS_FIELDS = (
    "path_loss_db",
    "cable_loss_db",
    "polarization_loss_db",
    "atmospheric_loss_db",
    "shadowing_db",
)


def _random_position(rng: random.Random) -> GeoPosition:
    return GeoPosition(
        lat=rng.uniform(-90.0, 90.0),
        lon=rng.uniform(-180.0, 180.0),
        alt_m=rng.uniform(-1_000.0, 1_000.0),
    )


def _random_budget(rng: random.Random) -> LinkBudgetInput:
    return LinkBudgetInput(
        tx_power_dbm=rng.uniform(-100.0, 80.0),
        tx_gain_dbi=rng.uniform(-20.0, 40.0),
        rx_gain_dbi=rng.uniform(-20.0, 40.0),
        path_loss_db=rng.uniform(0.0, 220.0),
        cable_loss_db=rng.uniform(0.0, 30.0),
        polarization_loss_db=rng.uniform(0.0, 10.0),
        atmospheric_loss_db=rng.uniform(0.0, 10.0),
        shadowing_db=rng.uniform(0.0, 40.0),
        bandwidth_hz=10.0 ** rng.uniform(-9.0, 18.0),
        noise_figure_db=rng.uniform(-10.0, 30.0),
        sensitivity_dbm=rng.uniform(-160.0, -20.0),
    )


def _with_extra_loss(budget: LinkBudgetInput, field: str, delta: float) -> LinkBudgetInput:
    values = {name: getattr(budget, name) for name in budget.__dataclass_fields__}
    values[field] += delta
    return LinkBudgetInput(**values)


def test_fspl_is_strictly_increasing_with_distance() -> None:
    rng = random.Random(1234)
    for _ in range(CASES):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        factor = 1.0 + rng.uniform(1e-9, 100.0)
        assert free_space_path_loss_db(distance * factor, frequency) > free_space_path_loss_db(
            distance, frequency
        )


def test_fspl_is_strictly_increasing_with_frequency() -> None:
    rng = random.Random(1235)
    for _ in range(CASES):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        factor = 1.0 + rng.uniform(1e-9, 100.0)
        assert free_space_path_loss_db(distance, frequency * factor) > free_space_path_loss_db(
            distance, frequency
        )


def test_fspl_distance_scaling_laws() -> None:
    """Doubling adds 6.0206 dB, ten-folding adds 20 dB."""
    rng = random.Random(1236)
    for _ in range(CASES):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        base = free_space_path_loss_db(distance, frequency)
        assert free_space_path_loss_db(2.0 * distance, frequency) - base == pytest.approx(
            6.020599913, abs=1e-8
        )
        assert free_space_path_loss_db(10.0 * distance, frequency) - base == pytest.approx(
            20.0, abs=1e-8
        )


def test_fspl_frequency_scaling_laws() -> None:
    rng = random.Random(1237)
    for _ in range(CASES):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        base = free_space_path_loss_db(distance, frequency)
        assert free_space_path_loss_db(distance, 2.0 * frequency) - base == pytest.approx(
            6.020599913, abs=1e-8
        )
        assert free_space_path_loss_db(distance, 10.0 * frequency) - base == pytest.approx(
            20.0, abs=1e-8
        )


def test_haversine_is_symmetric() -> None:
    rng = random.Random(1238)
    for _ in range(CASES):
        a, b = _random_position(rng), _random_position(rng)
        assert haversine_distance_m(a, b) == pytest.approx(haversine_distance_m(b, a), abs=1e-7)


def test_haversine_of_a_point_with_itself_is_zero() -> None:
    rng = random.Random(1239)
    for _ in range(CASES):
        a = _random_position(rng)
        assert haversine_distance_m(a, a) == 0.0


def test_haversine_obeys_the_triangle_inequality() -> None:
    rng = random.Random(1240)
    for _ in range(CASES):
        a, b, c = (_random_position(rng) for _ in range(3))
        ab = haversine_distance_m(a, b)
        bc = haversine_distance_m(b, c)
        ac = haversine_distance_m(a, c)
        assert ac <= ab + bc + 1e-6


def test_one_degree_of_latitude_is_about_111_19_km() -> None:
    rng = random.Random(1241)
    expected = EARTH_MEAN_RADIUS_M * math.pi / 180.0
    assert expected == pytest.approx(111_194.93, abs=0.01)
    for _ in range(CASES):
        lat = rng.uniform(-89.0, 89.0)
        a = GeoPosition(lat=lat, lon=rng.uniform(-180.0, 180.0))
        b = GeoPosition(lat=lat + 1.0, lon=a.lon)
        assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-6)


def test_longitude_spacing_shrinks_with_cosine_of_latitude() -> None:
    rng = random.Random(1242)
    equatorial_degree = EARTH_MEAN_RADIUS_M * math.pi / 180.0
    for _ in range(CASES):
        lat = rng.uniform(-89.0, 89.0)
        a = GeoPosition(lat=lat, lon=0.0)
        b = GeoPosition(lat=lat, lon=1.0)
        spacing = haversine_distance_m(a, b)
        # Exact great-circle distance between two points on the same parallel.
        expected = (
            2.0
            * EARTH_MEAN_RADIUS_M
            * math.asin(math.cos(math.radians(lat)) * math.sin(math.radians(1.0) / 2.0))
        )
        assert spacing == pytest.approx(expected, abs=1e-6)
        # ... and it scales with cos(latitude).
        assert spacing == pytest.approx(
            equatorial_degree * math.cos(math.radians(lat)), rel=1e-4, abs=1e-6
        )
        assert spacing <= equatorial_degree + 1e-6


def test_antipodal_points_are_half_the_circumference_and_never_nan() -> None:
    rng = random.Random(1243)
    expected = math.pi * EARTH_MEAN_RADIUS_M
    for _ in range(CASES):
        lat = rng.uniform(-90.0, 90.0)
        lon = rng.uniform(-180.0, 180.0)
        a = GeoPosition(lat=lat, lon=lon)
        b = GeoPosition(lat=-lat, lon=math.remainder(lon + 180.0, 360.0))
        distance = haversine_distance_m(a, b)
        assert math.isfinite(distance)
        assert distance == pytest.approx(expected, abs=1e-6)


def test_antimeridian_crossing_uses_the_short_path() -> None:
    rng = random.Random(1244)
    for _ in range(CASES):
        lat = rng.uniform(-89.0, 89.0)
        a = GeoPosition(lat=lat, lon=179.999)
        b = GeoPosition(lat=lat, lon=-179.999)
        expected = (
            2.0
            * EARTH_MEAN_RADIUS_M
            * math.asin(math.cos(math.radians(lat)) * math.sin(math.radians(0.002) / 2.0))
        )
        assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-6)


def test_all_longitudes_coincide_at_the_poles() -> None:
    rng = random.Random(1245)
    for _ in range(CASES):
        lon_a = rng.uniform(-180.0, 180.0)
        lon_b = rng.uniform(-180.0, 180.0)
        for lat in (-90.0, 90.0):
            assert (
                haversine_distance_m(
                    GeoPosition(lat=lat, lon=lon_a), GeoPosition(lat=lat, lon=lon_b)
                )
                == 0.0
            )


def test_slant_range_equals_surface_range_at_equal_altitude() -> None:
    rng = random.Random(1246)
    for _ in range(CASES):
        a, b = _random_position(rng), _random_position(rng)
        a = GeoPosition(a.lat, a.lon, 350.0)
        b = GeoPosition(b.lat, b.lon, 350.0)
        assert slant_range_m(a, b) == pytest.approx(haversine_distance_m(a, b), abs=1e-7)


def test_slant_range_satisfies_pythagoras() -> None:
    rng = random.Random(1247)
    for _ in range(CASES):
        a, b = _random_position(rng), _random_position(rng)
        a = GeoPosition(a.lat, a.lon, rng.uniform(-1.0e6, 1.0e6))
        b = GeoPosition(b.lat, b.lon, rng.uniform(-1.0e6, 1.0e6))
        surface = haversine_distance_m(a, b)
        expected = math.hypot(surface, a.alt_m - b.alt_m)
        assert slant_range_m(a, b) == pytest.approx(expected, rel=1e-14, abs=1e-7)


def test_slant_range_is_symmetric() -> None:
    rng = random.Random(1248)
    for _ in range(CASES):
        a, b = _random_position(rng), _random_position(rng)
        assert slant_range_m(a, b) == pytest.approx(slant_range_m(b, a), abs=1e-7)


def test_margin_is_received_power_minus_sensitivity() -> None:
    rng = random.Random(1249)
    for _ in range(CASES):
        budget = _random_budget(rng)
        received = received_power_dbm(budget)
        assert link_margin_db(received, budget.sensitivity_dbm) == pytest.approx(
            received - budget.sensitivity_dbm, abs=1e-12
        )


def test_snr_is_received_power_minus_noise_floor() -> None:
    rng = random.Random(1250)
    for _ in range(CASES):
        budget = _random_budget(rng)
        received = received_power_dbm(budget)
        noise = noise_floor_dbm(budget.bandwidth_hz, budget.noise_figure_db)
        assert snr_db(received, noise) == pytest.approx(received - noise, abs=1e-12)


def test_every_extra_loss_term_lowers_power_and_margin_by_exactly_itself() -> None:
    rng = random.Random(1251)
    for _ in range(CASES):
        budget = _random_budget(rng)
        received = received_power_dbm(budget)
        margin = link_margin_db(received, budget.sensitivity_dbm)
        delta = rng.uniform(0.01, 50.0)
        for field in LOSS_FIELDS:
            degraded = _with_extra_loss(budget, field, delta)
            degraded_received = received_power_dbm(degraded)
            assert degraded_received == pytest.approx(received - delta, abs=1e-10)
            assert link_margin_db(degraded_received, budget.sensitivity_dbm) == pytest.approx(
                margin - delta, abs=1e-10
            )


def test_eb_n0_equals_snr_when_bit_rate_equals_bandwidth() -> None:
    rng = random.Random(1252)
    for _ in range(CASES):
        budget = _random_budget(rng)
        received = received_power_dbm(budget)
        noise = noise_floor_dbm(budget.bandwidth_hz, budget.noise_figure_db)
        snr = snr_db(received, noise)
        assert eb_n0_db(snr, budget.bandwidth_hz, budget.bandwidth_hz) == pytest.approx(
            snr, abs=1e-12
        )


def test_link_quality_is_monotonic_and_exhaustive() -> None:
    rng = random.Random(1253)
    ranks = {LinkQuality.DOWN: 0, LinkQuality.MARGINAL: 1, LinkQuality.UP: 2}
    margins = sorted(rng.uniform(-1.0e6, 1.0e6) for _ in range(CASES))
    qualities = [link_quality(margin) for margin in margins]
    assert all(isinstance(quality, LinkQuality) for quality in qualities)
    assert all(ranks[left] <= ranks[right] for left, right in itertools.pairwise(qualities))
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    assert link_quality(largest) is LinkQuality.UP
    assert link_quality(-largest) is LinkQuality.DOWN


def test_watts_dbm_watts_round_trip_within_1e_9_relative() -> None:
    rng = random.Random(1254)
    for _ in range(CASES):
        power = 10.0 ** rng.uniform(-30.0, 30.0)
        assert watts_from_dbm(dbm_from_watts(power)) == pytest.approx(power, rel=1e-9)
