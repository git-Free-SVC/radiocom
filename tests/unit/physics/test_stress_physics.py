from __future__ import annotations

import math
import random

import pytest

from libraries.domain.position import GeoPosition
from libraries.domain.rf_results import LinkBudgetInput, LinkQuality
from libraries.physics import (
    EARTH_MEAN_RADIUS_M,
    PhysicsInputError,
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


GOLDEN_FSPL_DB = [
    (1.0, 1.0e3, -87.560000000000),
    (10.0, 1.0e3, -67.560000000000),
    (1000.0, 1.0e3, -27.560000000000),
    (1.0e6, 1.0e3, 32.440000000000),
    (1.0, 1.0e6, -27.560000000000),
    (100.0, 1.0e6, 12.440000000000),
    (1.0e6, 1.0e6, 92.440000000000),
    (1.0, 3.0e7, 1.982425094393),
    (10.0, 3.0e7, 21.982425094393),
    (1000.0, 3.0e7, 61.982425094393),
    (1.0e6, 3.0e7, 121.982425094393),
    (1.0, 145.5e6, 15.697259866439),
    (1000.0, 145.5e6, 75.697259866439),
    (10_000.0, 145.5e6, 95.697259866439),
    (10_007.5, 145.5e6, 95.703771841981),
    (1.0e6, 145.5e6, 135.697259866439),
    (1.0, 1.0e9, 32.440000000000),
    (100.0, 1.0e9, 72.440000000000),
    (1.0e6, 1.0e9, 152.440000000000),
    (1.0, 1.0e10, 52.440000000000),
    (1000.0, 1.0e10, 112.440000000000),
    (1.0e6, 1.0e10, 172.440000000000),
    (1.0, 1.0e11, 72.440000000000),
    (1.0e6, 1.0e11, 192.440000000000),
]


@pytest.mark.parametrize(("distance", "frequency", "expected"), GOLDEN_FSPL_DB)
def test_fspl_independent_decimal_golden_values(
    distance: float, frequency: float, expected: float
) -> None:
    # Expected values were generated independently with 60-digit Decimal.ln,
    # using 20(log10(d_km) + log10(f_MHz)) + 32.44.
    assert free_space_path_loss_db(distance, frequency) == pytest.approx(expected, abs=1e-9)


def test_fspl_is_strictly_increasing_with_distance_for_10000_samples() -> None:
    rng = random.Random(1234)
    for _ in range(10_000):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        factor = 1.0 + rng.uniform(1e-8, 100.0)
        assert free_space_path_loss_db(distance * factor, frequency) > (
            free_space_path_loss_db(distance, frequency)
        )


def test_fspl_is_strictly_increasing_with_frequency_for_10000_samples() -> None:
    rng = random.Random(4321)
    for _ in range(10_000):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        factor = 1.0 + rng.uniform(1e-8, 100.0)
        assert free_space_path_loss_db(distance, frequency * factor) > (
            free_space_path_loss_db(distance, frequency)
        )


def test_fspl_distance_scaling_laws_for_10000_samples() -> None:
    rng = random.Random(41)
    for _ in range(10_000):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        base = free_space_path_loss_db(distance, frequency)
        double_delta = free_space_path_loss_db(2.0 * distance, frequency) - base
        tenfold_delta = free_space_path_loss_db(10.0 * distance, frequency) - base
        assert double_delta == pytest.approx(6.020599913, abs=1e-8)
        assert tenfold_delta == pytest.approx(20.0, abs=1e-8)


def test_fspl_frequency_scaling_laws_for_10000_samples() -> None:
    rng = random.Random(42)
    for _ in range(10_000):
        distance = 10.0 ** rng.uniform(0.0, 6.0)
        frequency = 10.0 ** rng.uniform(3.0, 11.0)
        base = free_space_path_loss_db(distance, frequency)
        double_delta = free_space_path_loss_db(distance, 2.0 * frequency) - base
        tenfold_delta = free_space_path_loss_db(distance, 10.0 * frequency) - base
        assert double_delta == pytest.approx(6.020599913, abs=1e-8)
        assert tenfold_delta == pytest.approx(20.0, abs=1e-8)


def _random_position(rng: random.Random) -> GeoPosition:
    return GeoPosition(
        lat=rng.uniform(-90.0, 90.0),
        lon=rng.uniform(-180.0, 180.0),
        alt_m=rng.uniform(-1_000.0, 1_000.0),
    )


def test_haversine_symmetry_for_10000_samples() -> None:
    rng = random.Random(100)
    for _ in range(10_000):
        a, b = _random_position(rng), _random_position(rng)
        assert haversine_distance_m(a, b) == pytest.approx(haversine_distance_m(b, a), abs=1e-7)


def test_haversine_identity_for_10000_samples() -> None:
    rng = random.Random(101)
    for _ in range(10_000):
        a = _random_position(rng)
        assert haversine_distance_m(a, a) == 0.0


def test_haversine_triangle_inequality_for_10000_samples() -> None:
    rng = random.Random(102)
    for _ in range(10_000):
        a, b, c = (_random_position(rng) for _ in range(3))
        ab = haversine_distance_m(a, b)
        bc = haversine_distance_m(b, c)
        ac = haversine_distance_m(a, c)
        assert ac <= ab + bc + 1e-5


def test_one_degree_latitude_for_10000_samples() -> None:
    rng = random.Random(103)
    expected = EARTH_MEAN_RADIUS_M * math.pi / 180.0
    for _ in range(10_000):
        lat = rng.uniform(-89.0, 89.0)
        a = GeoPosition(lat=lat, lon=rng.uniform(-180.0, 180.0))
        b = GeoPosition(lat=lat + 1.0, lon=a.lon)
        assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-6)


def test_longitude_spacing_scales_with_cos_latitude_for_10000_samples() -> None:
    rng = random.Random(104)
    # equatorial_degree = EARTH_MEAN_RADIUS_M * math.pi / 180.0
    for _ in range(10_000):
        lat = rng.uniform(-89.9, 89.9)
        a = GeoPosition(lat=lat, lon=0.0)
        b = GeoPosition(lat=lat, lon=1.0)
        phi = math.radians(lat)
        expected = (
            2.0 * EARTH_MEAN_RADIUS_M * math.asin(math.cos(phi) * math.sin(math.radians(1.0) / 2.0))
        )
        assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-7)


def test_regression_antipodal_haversine_cancellation_for_10000_samples() -> None:
    rng = random.Random(105)
    expected = math.pi * EARTH_MEAN_RADIUS_M
    for _ in range(10_000):
        lat = rng.uniform(-90.0, 90.0)
        lon = rng.uniform(-180.0, 180.0)
        a = GeoPosition(lat=lat, lon=lon)
        b = GeoPosition(lat=-lat, lon=math.remainder(lon + 180.0, 360.0))
        distance = haversine_distance_m(a, b)
        assert math.isfinite(distance)
        assert distance == pytest.approx(expected, abs=1e-6)


def test_antimeridian_crossings_for_10000_samples() -> None:
    rng = random.Random(106)
    for _ in range(10_000):
        lat = rng.uniform(-89.9, 89.9)
        a = GeoPosition(lat=lat, lon=179.999)
        b = GeoPosition(lat=lat, lon=-179.999)
        expected = (
            2.0
            * EARTH_MEAN_RADIUS_M
            * math.asin(math.cos(math.radians(lat)) * math.sin(math.radians(0.002) / 2.0))
        )
        assert haversine_distance_m(a, b) == pytest.approx(expected, abs=1e-6)


def test_pole_longitudes_coincide_for_10000_samples() -> None:
    rng = random.Random(112)
    for _ in range(10_000):
        lon_a = rng.uniform(-180.0, 180.0)
        lon_b = rng.uniform(-180.0, 180.0)
        for lat in (-90.0, 90.0):
            a = GeoPosition(lat=lat, lon=lon_a)
            b = GeoPosition(lat=lat, lon=lon_b)
            assert haversine_distance_m(a, b) == 0.0


def test_slant_equals_surface_range_at_equal_altitude_for_10000_samples() -> None:
    rng = random.Random(113)
    for _ in range(10_000):
        a, b = _random_position(rng), _random_position(rng)
        a = GeoPosition(a.lat, a.lon, 350.0)
        b = GeoPosition(b.lat, b.lon, 350.0)
        assert slant_range_m(a, b) == pytest.approx(haversine_distance_m(a, b), abs=1e-7)


def test_slant_range_pythagoras_for_10000_samples() -> None:
    rng = random.Random(107)
    for _ in range(10_000):
        a, b = _random_position(rng), _random_position(rng)
        a = GeoPosition(a.lat, a.lon, rng.uniform(-1.0e6, 1.0e6))
        b = GeoPosition(b.lat, b.lon, rng.uniform(-1.0e6, 1.0e6))
        surface = haversine_distance_m(a, b)
        expected = math.hypot(surface, a.alt_m - b.alt_m)
        assert slant_range_m(a, b) == pytest.approx(expected, rel=1e-14, abs=1e-7)


def test_slant_range_symmetry_for_10000_samples() -> None:
    rng = random.Random(108)
    for _ in range(10_000):
        a, b = _random_position(rng), _random_position(rng)
        assert slant_range_m(a, b) == pytest.approx(slant_range_m(b, a), abs=1e-7)


def test_link_budget_equations_and_loss_delta_for_10000_samples() -> None:
    rng = random.Random(109)
    loss_fields = (
        "path_loss_db",
        "cable_loss_db",
        "polarization_loss_db",
        "atmospheric_loss_db",
        "shadowing_db",
    )
    for _ in range(10_000):
        budget = LinkBudgetInput(
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
        received = received_power_dbm(budget)
        noise = noise_floor_dbm(budget.bandwidth_hz, budget.noise_figure_db)
        margin = link_margin_db(received, budget.sensitivity_dbm)
        assert margin == pytest.approx(received - budget.sensitivity_dbm, abs=1e-12)
        assert snr_db(received, noise) == pytest.approx(received - noise, abs=1e-12)
        eb_n0 = eb_n0_db(received - noise, budget.bandwidth_hz, budget.bandwidth_hz)
        assert eb_n0 == pytest.approx(received - noise, abs=1e-12)
        delta = rng.uniform(0.01, 50.0)
        for field in loss_fields:
            higher_loss = budget.__class__(
                **{
                    name: getattr(budget, name) + (delta if name == field else 0.0)
                    for name in budget.__dataclass_fields__
                }
            )
            assert received_power_dbm(higher_loss) == pytest.approx(received - delta, abs=1e-10)
            assert link_margin_db(
                received_power_dbm(higher_loss), budget.sensitivity_dbm
            ) == pytest.approx(margin - delta, abs=1e-10)


def test_link_quality_is_monotonic_and_exhaustive_for_10000_samples() -> None:
    rng = random.Random(110)
    margins = sorted(rng.uniform(-1.0e6, 1.0e6) for _ in range(10_000))
    ranks = {LinkQuality.DOWN: 0, LinkQuality.MARGINAL: 1, LinkQuality.UP: 2}
    qualities = [link_quality(margin) for margin in margins]
    assert all(ranks[left] <= ranks[right] for left, right in zip(qualities, qualities[1:]))
    assert all(isinstance(quality, LinkQuality) for quality in qualities)
    maximum_float = float.fromhex("0x1.fffffffffffffp+1023")
    assert link_quality(maximum_float) is LinkQuality.UP
    assert link_quality(-maximum_float) is LinkQuality.DOWN


def test_watts_dbm_round_trip_for_10000_samples() -> None:
    rng = random.Random(111)
    for _ in range(10_000):
        power = 10.0 ** rng.uniform(-30.0, 30.0)
        restored = watts_from_dbm(dbm_from_watts(power))
        assert restored == pytest.approx(power, rel=1e-9)


@pytest.mark.parametrize(
    "distance",
    [
        0.0,
        1.0e-300,
        5.0e-324,
        math.nextafter(1.0, 0.0),
        1.0,
        math.nextafter(1.0, math.inf),
        1.0e300,
    ],
)
def test_distance_clamping_edges_are_finite(distance: float) -> None:
    assert math.isfinite(free_space_path_loss_db(distance, 145.5e6))


def test_distance_clamp_value_and_adjacent_ulps() -> None:
    at_clamp = free_space_path_loss_db(1.0, 145.5e6)
    below = free_space_path_loss_db(math.nextafter(1.0, 0.0), 145.5e6)
    above = free_space_path_loss_db(math.nextafter(1.0, math.inf), 145.5e6)
    assert below == at_clamp
    assert above >= at_clamp


@pytest.mark.parametrize("distance", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_distance_hostile_values_raise_named_error(distance: float) -> None:
    with pytest.raises(PhysicsInputError, match="distance_m"):
        free_space_path_loss_db(distance, 145.5e6)


@pytest.mark.parametrize(
    "frequency",
    [0.0, -1.0, float("nan"), float("inf"), -float("inf")],
)
def test_frequency_hostile_values_raise_named_error(frequency: float) -> None:
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        free_space_path_loss_db(1000.0, frequency)


@pytest.mark.parametrize("frequency", [1.0e-9, 1.0e18])
def test_finite_frequency_extremes_do_not_overflow(frequency: float) -> None:
    assert math.isfinite(free_space_path_loss_db(1.0e6, frequency))


def test_50k_distance_frequency_power_bandwidth_sweep_is_finite() -> None:
    distances = [10.0 ** (6.0 * idx / 9.0) for idx in range(10)]
    frequencies = [10.0 ** (3.0 + 8.0 * idx / 9.0) for idx in range(10)]
    powers = [10.0 ** (-6.0 + 18.0 * idx / 9.0) for idx in range(10)]
    bandwidths = [10.0 ** (-9.0 + 27.0 * idx / 49.0) for idx in range(50)]
    count = 0
    for d_idx, distance in enumerate(distances):
        for f_idx, frequency in enumerate(frequencies):
            for p_idx, power in enumerate(powers):
                for b_idx, bandwidth in enumerate(bandwidths):
                    path_loss = free_space_path_loss_db(distance, frequency)
                    budget = LinkBudgetInput(
                        tx_power_dbm=dbm_from_watts(power),
                        tx_gain_dbi=2.15,
                        rx_gain_dbi=2.15,
                        path_loss_db=max(0.0, path_loss),
                        bandwidth_hz=bandwidth,
                        noise_figure_db=5.0,
                        sensitivity_dbm=-120.0,
                    )
                    received = received_power_dbm(budget)
                    noise = noise_floor_dbm(bandwidth, budget.noise_figure_db)
                    values = (path_loss, received, noise, received - noise)
                    assert all(math.isfinite(value) for value in values)
                    count += 1
    assert count == 50_000
