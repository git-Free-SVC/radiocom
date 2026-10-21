"""Unit tests for the link-budget helpers (architecture doc §9 formulas)."""

from __future__ import annotations

import math

import pytest

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality, LinkState
from libraries.physics import (
    MARGINAL_MARGIN_DB,
    NOISE_DENSITY_DBM_HZ,
    UP_MARGIN_DB,
    PhysicsInputError,
    calculate_link_budget,
    dbm_from_watts,
    eb_n0_db,
    link_margin_db,
    link_quality,
    link_state,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
    watts_from_dbm,
)

# The worked example of task brief §5.3, using the frozen contract fixture.
CONTRACT_BUDGET = LinkBudgetInput(
    tx_power_dbm=40.0,  # 10 W
    tx_gain_dbi=2.15,
    rx_gain_dbi=2.15,
    path_loss_db=95.7038,
    bandwidth_hz=12_500.0,
    noise_figure_db=5.0,
    sensitivity_dbm=-120.0,
)


def test_worked_link_budget_chain_matches_the_brief() -> None:
    """Pr, N, SNR and margin of the contract fixture, to +/- 0.01 dB."""
    result = calculate_link_budget(CONTRACT_BUDGET, bit_rate_hz=12_500.0)
    assert result.received_power_dbm == pytest.approx(-51.40, abs=0.01)
    assert result.noise_floor_dbm == pytest.approx(-128.03, abs=0.01)
    assert result.snr_db == pytest.approx(76.63, abs=0.01)
    assert result.margin_db == pytest.approx(68.60, abs=0.01)
    assert result.eb_n0_db == pytest.approx(result.snr_db, abs=1e-9)


def test_link_budget_equations_with_every_loss_term() -> None:
    budget = LinkBudgetInput(
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
    received = received_power_dbm(budget)
    noise = noise_floor_dbm(budget.bandwidth_hz, budget.noise_figure_db)
    assert received == pytest.approx(10.0 + 3.0 + 4.0 - 80.0 - 1.0 - 2.0 - 3.0 - 4.0)
    assert noise == pytest.approx(NOISE_DENSITY_DBM_HZ + 10.0 * math.log10(1e6) + 5.0)
    assert snr_db(received, noise) == pytest.approx(received - noise)
    assert link_margin_db(received, budget.sensitivity_dbm) == pytest.approx(
        received - budget.sensitivity_dbm
    )
    # Eb/N0 = SNR + 10*log10(bandwidth / bit_rate)
    assert eb_n0_db(36.0, 1_000_000.0, 100_000.0) == pytest.approx(46.0)


def test_eb_n0_equals_snr_when_bit_rate_equals_bandwidth() -> None:
    result = calculate_link_budget(CONTRACT_BUDGET)
    assert result.eb_n0_db == pytest.approx(result.snr_db, abs=1e-12)


def test_watts_to_dbm_conversion() -> None:
    assert dbm_from_watts(1.0) == pytest.approx(30.0)
    assert dbm_from_watts(10.0) == pytest.approx(40.0)
    assert dbm_from_watts(0.001) == pytest.approx(0.0)


def test_watts_dbm_round_trip() -> None:
    for power_watt in (1.0e-30, 1.0e-12, 1.0, 1.0e6, 1.0e30):
        restored = watts_from_dbm(dbm_from_watts(power_watt))
        assert restored == pytest.approx(power_watt, rel=1e-12)


def test_link_state_uses_the_frozen_result_type() -> None:
    state = link_state(CONTRACT_BUDGET)
    assert isinstance(state, LinkState)
    assert state.quality is LinkQuality.UP
    assert state.snr_db == pytest.approx(76.63, abs=0.01)
    assert state.margin_db == pytest.approx(68.60, abs=0.01)


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


def test_link_quality_thresholds_are_the_documented_convention() -> None:
    assert (UP_MARGIN_DB, MARGINAL_MARGIN_DB) == (10.0, 0.0)


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


def test_link_budget_rejects_a_non_budget_argument() -> None:
    with pytest.raises(PhysicsInputError, match="budget must be LinkBudgetInput"):
        received_power_dbm(object())  # type: ignore[arg-type]
    with pytest.raises(PhysicsInputError, match="budget must be LinkBudgetInput"):
        calculate_link_budget(None)  # type: ignore[arg-type]


def test_finite_extreme_bandwidth_and_rate_stay_finite() -> None:
    assert math.isfinite(noise_floor_dbm(1.0e-9))
    assert math.isfinite(noise_floor_dbm(1.0e18))
    assert math.isfinite(eb_n0_db(10.0, 1.0e18, 1.0e-9))
