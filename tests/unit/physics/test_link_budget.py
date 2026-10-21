from __future__ import annotations

import math

import pytest

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality
from libraries.physics import (
    PhysicsInputError,
    calculate_link_budget,
    dbm_from_watts,
    eb_n0_db,
    link_margin_db,
    link_quality,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
    watts_from_dbm,
)


def test_full_worked_link_budget_chain() -> None:
    budget = LinkBudgetInput(
        tx_power_dbm=dbm_from_watts(10.0),
        tx_gain_dbi=2.15,
        rx_gain_dbi=2.15,
        path_loss_db=95.703771841981,
        bandwidth_hz=12_500.0,
        noise_figure_db=5.0,
        sensitivity_dbm=-120.0,
    )
    result = calculate_link_budget(budget, bit_rate_hz=12_500.0)
    assert result.received_power_dbm == pytest.approx(-51.4038, abs=0.01)
    assert result.noise_floor_dbm == pytest.approx(-128.0309, abs=0.01)
    assert result.snr_db == pytest.approx(76.6271, abs=0.01)
    assert result.margin_db == pytest.approx(68.5962, abs=0.01)
    assert result.eb_n0_db == pytest.approx(result.snr_db, abs=1e-12)


def test_loss_terms_and_sensitivity_follow_link_budget_equations() -> None:
    base = LinkBudgetInput(
        tx_power_dbm=10.0,
        tx_gain_dbi=3.0,
        rx_gain_dbi=4.0,
        path_loss_db=80.0,
        cable_loss_db=1.0,
        polarization_loss_db=2.0,
        atmospheric_loss_db=3.0,
        shadowing_db=4.0,
        bandwidth_hz=1_000_000.0,
        noise_figure_db=5.0,
        sensitivity_dbm=-100.0,
    )
    received = received_power_dbm(base)
    noise = noise_floor_dbm(base.bandwidth_hz, base.noise_figure_db)
    assert received == pytest.approx(-73.0)
    assert noise == pytest.approx(-109.0)
    assert snr_db(received, noise) == pytest.approx(36.0)
    assert link_margin_db(received, base.sensitivity_dbm) == pytest.approx(27.0)
    assert eb_n0_db(36.0, 1_000_000.0, 100_000.0) == pytest.approx(46.0)


@pytest.mark.parametrize(
    ("margin", "expected"),
    [
        (-1.0, LinkQuality.DOWN),
        (math.nextafter(0.0, -math.inf), LinkQuality.DOWN),
        (-0.0, LinkQuality.MARGINAL),
        (0.0, LinkQuality.MARGINAL),
        (math.nextafter(10.0, -math.inf), LinkQuality.MARGINAL),
        (10.0, LinkQuality.UP),
        (math.nextafter(10.0, math.inf), LinkQuality.UP),
    ],
)
def test_link_quality_threshold_boundaries(margin: float, expected: LinkQuality) -> None:
    assert link_quality(margin) is expected


def test_watts_and_dbm_round_trip_reference_values() -> None:
    for power_watt in (1.0e-30, 1.0e-12, 1.0, 1.0e6, 1.0e30):
        round_trip = watts_from_dbm(dbm_from_watts(power_watt))
        assert round_trip == pytest.approx(power_watt, rel=1e-12)


@pytest.mark.parametrize("power", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_watts_to_dbm_rejects_invalid_power(power: float) -> None:
    with pytest.raises(PhysicsInputError, match="power_watt"):
        dbm_from_watts(power)


@pytest.mark.parametrize("dbm", [float("nan"), float("inf"), -float("inf"), 1.0e6, -1.0e6])
def test_dbm_to_watts_rejects_nonfinite_or_unrepresentable_power(dbm: float) -> None:
    with pytest.raises(PhysicsInputError, match="power_dbm"):
        watts_from_dbm(dbm)


@pytest.mark.parametrize("bandwidth", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_noise_floor_rejects_invalid_bandwidth(bandwidth: float) -> None:
    with pytest.raises(PhysicsInputError, match="bandwidth_hz"):
        noise_floor_dbm(bandwidth)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_eb_n0_rejects_invalid_bit_rate(rate: float) -> None:
    with pytest.raises(PhysicsInputError, match="bit_rate_hz"):
        eb_n0_db(0.0, 1.0, rate)


@pytest.mark.parametrize("margin", [float("nan"), float("inf"), -float("inf")])
def test_link_quality_rejects_nonfinite_margin(margin: float) -> None:
    with pytest.raises(PhysicsInputError, match="margin_db"):
        link_quality(margin)


def test_finite_extreme_bandwidth_and_rate_remain_finite() -> None:
    assert math.isfinite(noise_floor_dbm(1.0e-9))
    assert math.isfinite(noise_floor_dbm(1.0e18))
    assert math.isfinite(eb_n0_db(10.0, 1.0e18, 1.0e-9))
