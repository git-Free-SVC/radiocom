"""Category C of the stress campaign: hostile inputs.

Every value below is either degenerate, non-finite or outside the physical
range. The contract is the same for all of them:

* the physics package raises :class:`PhysicsInputError` (never a bare
  ``ValueError: math domain error`` and never an ``OverflowError``), and
* the message names the offending argument and its value.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from libraries.domain.position import GeoPosition
from libraries.domain.rf_results import LinkBudgetInput, LinkQuality
from libraries.physics import (
    MIN_DISTANCE_M,
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

DENORMAL = 5.0e-324  # smallest positive subnormal float
HUGE = 1.0e300


# --------------------------------------------------------------------------
# distance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "distance",
    [
        -1.0,
        -1.0e-300,
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_hostile_distance_is_rejected(distance: float) -> None:
    with pytest.raises(PhysicsInputError, match="distance_m"):
        free_space_path_loss_db(distance, 145.5e6)


@pytest.mark.parametrize("distance", [0.0, 1.0e-300, DENORMAL, MIN_DISTANCE_M, HUGE])
def test_extreme_but_legal_distance_stays_finite(distance: float) -> None:
    assert math.isfinite(free_space_path_loss_db(distance, 145.5e6))


def test_distance_clamp_value_and_its_neighbouring_ulps() -> None:
    at_clamp = free_space_path_loss_db(MIN_DISTANCE_M, 145.5e6)
    below = free_space_path_loss_db(math.nextafter(MIN_DISTANCE_M, 0.0), 145.5e6)
    above = free_space_path_loss_db(math.nextafter(MIN_DISTANCE_M, math.inf), 145.5e6)
    assert below == at_clamp  # clamped
    assert above >= at_clamp
    assert math.isfinite(above)


def test_zero_distance_never_reaches_log10() -> None:
    """A co-located pair must not raise ``ValueError: math domain error``."""
    result = free_space_path_loss_db(0.0, 145.5e6)
    assert math.isfinite(result)
    assert result == pytest.approx(free_space_path_loss_db(1.0, 145.5e6), abs=1e-12)


# --------------------------------------------------------------------------
# frequency, bandwidth, bit rate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("frequency", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_hostile_frequency_is_rejected(frequency: float) -> None:
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        free_space_path_loss_db(1_000.0, frequency)


@pytest.mark.parametrize("frequency", [1.0e-9, 1.0e18, 1.0e-300])
def test_extreme_frequency_stays_finite(frequency: float) -> None:
    assert math.isfinite(free_space_path_loss_db(1.000, frequency))


@pytest.mark.parametrize("bandwidth", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_hostile_bandwidth_is_rejected(bandwidth: float) -> None:
    with pytest.raises(PhysicsInputError, match="bandwidth_hz"):
        noise_floor_dbm(bandwidth)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_hostile_bit_rate_is_rejected(rate: float) -> None:
    with pytest.raises(PhysicsInputError, match="bit_rate_hz"):
        eb_n0_db(0.0, 1_000.0, rate)


@pytest.mark.parametrize("bandwidth", [1.0e-9, 1.0e18])
def test_extreme_bandwidth_and_rate_stay_finite(bandwidth: float) -> None:
    assert math.isfinite(noise_floor_dbm(bandwidth))
    assert math.isfinite(eb_n0_db(10.0, bandwidth, bandwidth))


# --------------------------------------------------------------------------
# power
# --------------------------------------------------------------------------


@pytest.mark.parametrize("power", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_hostile_transmit_power_is_rejected(power: float) -> None:
    with pytest.raises(PhysicsInputError, match="power_watt"):
        dbm_from_watts(power)


@pytest.mark.parametrize("power", [1.0e-30, 1.0e30])
def test_extreme_transmit_power_stays_finite(power: float) -> None:
    assert math.isfinite(dbm_from_watts(power))


@pytest.mark.parametrize("dbm", [float("nan"), float("inf"), -float("inf"), 1.0e6, -1.0e6])
def test_unrepresentable_dbm_is_rejected(dbm: float) -> None:
    with pytest.raises(PhysicsInputError, match="power_dbm"):
        watts_from_dbm(dbm)


# --------------------------------------------------------------------------
# coordinates
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lat", [-90.0, 90.0, 0.0])
def test_pole_and_equator_coordinates_are_valid(lat: float) -> None:
    a = GeoPosition(lat=lat, lon=0.0)
    b = GeoPosition(lat=lat, lon=10.0)
    assert math.isfinite(haversine_distance_m(a, b))


@pytest.mark.parametrize(
    ("position", "argument"),
    [
        (SimpleNamespace(lat=91.0, lon=0.0, alt_m=0.0), "a.lat"),
        (SimpleNamespace(lat=0.0, lon=181.0, alt_m=0.0), "a.lon"),
        (SimpleNamespace(lat=float("nan"), lon=0.0, alt_m=0.0), "a.lat"),
        (SimpleNamespace(lat=0.0, lon=float("nan"), alt_m=0.0), "a.lon"),
        (SimpleNamespace(lat=0.0, lon=0.0, alt_m=float("nan")), "a.alt_m"),
        (SimpleNamespace(lat=0.0, lon=0.0, alt_m=float("inf")), "a.alt_m"),
    ],
)
def test_hostile_coordinates_are_rejected(position, argument: str) -> None:
    valid = GeoPosition(lat=0.0, lon=0.0)
    with pytest.raises(PhysicsInputError, match=argument):
        haversine_distance_m(position, valid)
    with pytest.raises(PhysicsInputError, match=argument.replace("a.", "b.")):
        haversine_distance_m(valid, position)
    with pytest.raises(PhysicsInputError, match=argument):
        slant_range_m(position, valid)


def test_antimeridian_crossing_is_valid_and_short() -> None:
    east = GeoPosition(lat=0.0, lon=179.999)
    west = GeoPosition(lat=0.0, lon=-179.999)
    assert 0.0 < haversine_distance_m(east, west) < 1_000.0


def test_identical_points_are_valid_and_zero_apart() -> None:
    point = GeoPosition(lat=10.0, lon=20.0, alt_m=0.0)
    assert haversine_distance_m(point, point) == 0.0
    assert slant_range_m(point, point) == 0.0


def test_identical_lat_lon_with_different_altitude_is_valid() -> None:
    low = GeoPosition(lat=10.0, lon=20.0, alt_m=0.0)
    high = GeoPosition(lat=10.0, lon=20.0, alt_m=1_000.0)
    assert slant_range_m(low, high) == pytest.approx(1_000.0, abs=1e-9)


@pytest.mark.parametrize("alt_m", [1.0e300, -1.0e300, 1.0e-300, -1.0e-300])
def test_very_large_or_negative_altitudes_are_supported(alt_m: float) -> None:
    base = GeoPosition(lat=0.0, lon=0.0, alt_m=0.0)
    other = GeoPosition(lat=0.0, lon=0.0, alt_m=alt_m)
    assert math.isfinite(slant_range_m(base, other))


# --------------------------------------------------------------------------
# link margin / quality
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("margin", "expected"),
    [
        (0.0, LinkQuality.MARGINAL),
        (-0.0, LinkQuality.MARGINAL),
        (math.nextafter(0.0, math.inf), LinkQuality.MARGINAL),
        (math.nextafter(0.0, -math.inf), LinkQuality.DOWN),
        (10.0, LinkQuality.UP),
        (math.nextafter(10.0, math.inf), LinkQuality.UP),
        (math.nextafter(10.0, -math.inf), LinkQuality.MARGINAL),
    ],
)
def test_margin_boundaries_map_to_exactly_one_band(margin: float, expected: LinkQuality) -> None:
    assert link_quality(margin) is expected


def test_nan_margin_is_rejected() -> None:
    with pytest.raises(PhysicsInputError, match="margin_db"):
        link_quality(float("nan"))


@pytest.mark.parametrize("margin", [float("inf"), -float("inf")])
def test_infinite_margin_is_rejected(margin: float) -> None:
    with pytest.raises(PhysicsInputError, match="margin_db"):
        link_quality(margin)


# --------------------------------------------------------------------------
# link budget terms
# --------------------------------------------------------------------------


def test_non_finite_link_budget_terms_are_rejected() -> None:
    base = LinkBudgetInput(
        tx_power_dbm=10.0,
        tx_gain_dbi=0.0,
        rx_gain_dbi=0.0,
        path_loss_db=50.0,
    )
    for field in (
        "tx_power_dbm",
        "tx_gain_dbi",
        "rx_gain_dbi",
        "path_loss_db",
        "cable_loss_db",
        "polarization_loss_db",
        "atmospheric_loss_db",
        "shadowing_db",
    ):
        values = {name: getattr(base, name) for name in base.__dataclass_fields__}
        values[field] = float("nan")
        with pytest.raises(PhysicsInputError, match=field):
            received_power_dbm(LinkBudgetInput(**values))


def test_snr_and_margin_reject_non_finite_arguments() -> None:
    with pytest.raises(PhysicsInputError, match="received_dbm"):
        snr_db(float("nan"), -100.0)
    with pytest.raises(PhysicsInputError, match="noise_dbm"):
        snr_db(-100.0, float("nan"))
    with pytest.raises(PhysicsInputError, match="received_dbm"):
        link_margin_db(float("inf"), -100.0)
    with pytest.raises(PhysicsInputError, match="sensitivity_dbm"):
        link_margin_db(-100.0, float("nan"))
