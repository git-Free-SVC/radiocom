"""Link-budget math: reference chain, identities, round trips, hostile inputs."""

from __future__ import annotations

import math
import random

import pytest

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality, LinkState
from libraries.physics.errors import PhysicsInputError
from libraries.physics.link_budget import (
    compute_link_budget,
    dbm_to_watts,
    eb_n0_db,
    link_margin_db,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
    watts_to_dbm,
)


def test_watts_to_dbm_known() -> None:
    assert watts_to_dbm(1.0) == pytest.approx(30.0, abs=1e-12)
    assert watts_to_dbm(10.0) == pytest.approx(40.0, abs=1e-12)
    assert watts_to_dbm(0.001) == pytest.approx(0.0, abs=1e-12)
    assert watts_to_dbm(100.0) == pytest.approx(50.0, abs=1e-12)


def test_dbm_to_watts_known() -> None:
    assert dbm_to_watts(30.0) == pytest.approx(1.0, rel=1e-12)
    assert dbm_to_watts(0.0) == pytest.approx(1e-3, rel=1e-12)
    assert dbm_to_watts(-174.0) == pytest.approx(3.98107170553497e-21, rel=1e-12)


def test_round_trips() -> None:
    rng = random.Random(5)
    for _ in range(10_000):
        w = 10.0 ** rng.uniform(-30, 12)
        assert dbm_to_watts(watts_to_dbm(w)) == pytest.approx(w, rel=1e-9)
        dbm = rng.uniform(-250, 250)
        assert watts_to_dbm(dbm_to_watts(dbm)) == pytest.approx(dbm, abs=1e-9)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf, -math.inf, "1", None])
def test_watts_to_dbm_bad(bad: object) -> None:
    with pytest.raises(PhysicsInputError, match="power_watt"):
        watts_to_dbm(bad)  # type: ignore[arg-type]


def test_watts_to_dbm_denormal_ok() -> None:
    assert math.isfinite(watts_to_dbm(5e-324))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 1e10, -1e10])
def test_dbm_to_watts_bad_or_out_of_range(bad: float) -> None:
    with pytest.raises(PhysicsInputError):
        dbm_to_watts(bad)


def test_reference_chain_from_architecture() -> None:
    """10 W (40 dBm), 2.15 dBi both ends, 10 km @ 145.5 MHz, 12.5 kHz, NF 5 dB."""
    pl = 95.6973
    pr = received_power_dbm(40.0, 2.15, 2.15, pl)
    assert pr == pytest.approx(-51.40, abs=0.01)
    n = noise_floor_dbm(12_500.0, 5.0)
    assert n == pytest.approx(-128.03, abs=0.01)
    assert snr_db(pr, n) == pytest.approx(76.63, abs=0.01)
    assert link_margin_db(pr, -120.0) == pytest.approx(68.60, abs=0.01)


def test_received_power_all_terms() -> None:
    assert received_power_dbm(30, 3, 2, 100, 1, 0.5, 0.25, 0.25) == pytest.approx(-67.0)


def test_noise_floor_known() -> None:
    assert noise_floor_dbm(1.0) == pytest.approx(-174.0)
    assert noise_floor_dbm(1e6, 0.0) == pytest.approx(-114.0)
    assert noise_floor_dbm(1e6, 6.0) == pytest.approx(-108.0)


def test_identities_random() -> None:
    rng = random.Random(6)
    for _ in range(10_000):
        pt, gt, gr = rng.uniform(-30, 60), rng.uniform(-10, 40), rng.uniform(-10, 40)
        pl, x = rng.uniform(20, 250), rng.uniform(0, 40)
        sens, nf, bw = rng.uniform(-150, -60), rng.uniform(0, 20), 10.0 ** rng.uniform(2, 9)
        pr = received_power_dbm(pt, gt, gr, pl)
        n = noise_floor_dbm(bw, nf)
        # margin = Pr - sensitivity ; SNR = Pr - N
        assert link_margin_db(pr, sens) == pytest.approx(pr - sens, abs=1e-12)
        assert snr_db(pr, n) == pytest.approx(pr - n, abs=1e-12)
        # adding X dB of ANY loss term lowers Pr and margin by exactly X
        for kw in ("cable_loss_db", "polarization_loss_db", "atmospheric_loss_db", "shadowing_db"):
            pr2 = received_power_dbm(pt, gt, gr, pl, **{kw: x})
            assert pr - pr2 == pytest.approx(x, abs=1e-9)
            assert link_margin_db(pr, sens) - link_margin_db(pr2, sens) == pytest.approx(
                x, abs=1e-9
            )
        assert pr - received_power_dbm(pt, gt, gr, pl + x) == pytest.approx(x, abs=1e-9)


def test_eb_n0() -> None:
    assert eb_n0_db(10.0, 12_500.0, 12_500.0) == pytest.approx(10.0)  # Eb/N0 = SNR
    assert eb_n0_db(10.0, 12_500.0, 1_250.0) == pytest.approx(20.0)
    assert eb_n0_db(10.0, 1_250.0, 12_500.0) == pytest.approx(0.0)
    assert math.isfinite(eb_n0_db(0.0, 1e300, 1e-300))


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
def test_bandwidth_and_rate_bad(bad: float) -> None:
    with pytest.raises(PhysicsInputError, match="bandwidth_hz"):
        noise_floor_dbm(bad)
    with pytest.raises(PhysicsInputError, match="bandwidth_hz"):
        eb_n0_db(0.0, bad, 1.0)
    with pytest.raises(PhysicsInputError, match="bit_rate_hz"):
        eb_n0_db(0.0, 1.0, bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_every_db_argument_rejects_nonfinite(bad: float) -> None:
    for pos in range(8):
        args = [0.0] * 8
        args[pos] = bad
        with pytest.raises(PhysicsInputError):
            received_power_dbm(*args)
    with pytest.raises(PhysicsInputError):
        noise_floor_dbm(1e3, bad)
    with pytest.raises(PhysicsInputError):
        snr_db(bad, 0.0)
    with pytest.raises(PhysicsInputError):
        snr_db(0.0, bad)
    with pytest.raises(PhysicsInputError):
        link_margin_db(bad, 0.0)
    with pytest.raises(PhysicsInputError):
        link_margin_db(0.0, bad)


def test_overflowing_sum_raises_not_inf() -> None:
    with pytest.raises(PhysicsInputError, match="received power"):
        received_power_dbm(1e308, 1e308, 1e308, 0.0)
    with pytest.raises(PhysicsInputError, match="SNR"):
        snr_db(1e308, -1e308)


def test_very_large_gain_still_finite() -> None:
    assert math.isfinite(received_power_dbm(30.0, 1e6, 1e6, 100.0))


# ------------------------- compute_link_budget -----------------------------
def _budget(**kw: float) -> LinkBudgetInput:
    base = {
        "tx_power_dbm": 40.0,
        "tx_gain_dbi": 2.15,
        "rx_gain_dbi": 2.15,
        "path_loss_db": 95.6973,
        "bandwidth_hz": 12_500.0,
        "noise_figure_db": 5.0,
        "sensitivity_dbm": -120.0,
    }
    base.update(kw)
    return LinkBudgetInput(**base)


def test_compute_link_budget_reference() -> None:
    r = compute_link_budget(_budget())
    assert r.rx_power_dbm == pytest.approx(-51.40, abs=0.01)
    assert r.noise_floor_dbm == pytest.approx(-128.03, abs=0.01)
    assert r.snr_db == pytest.approx(76.63, abs=0.01)
    assert r.margin_db == pytest.approx(68.60, abs=0.01)
    assert r.quality is LinkQuality.UP
    state = r.to_link_state()
    assert isinstance(state, LinkState)
    assert (state.snr_db, state.margin_db, state.quality) == (r.snr_db, r.margin_db, r.quality)


def test_compute_link_budget_quality_transitions() -> None:
    assert compute_link_budget(_budget(path_loss_db=170.0)).quality is LinkQuality.DOWN
    pl_marginal = 40.0 + 4.3 + 120.0 - 5.0  # margin = 5 dB
    assert compute_link_budget(_budget(path_loss_db=pl_marginal)).quality is LinkQuality.MARGINAL


def test_compute_link_budget_model_agnostic_mock_loss() -> None:
    """Any model's path loss (here: fixed mock values) flows through consistently."""
    for loss in (0.0, 50.0, 123.456, 300.0):
        r = compute_link_budget(_budget(path_loss_db=loss))
        assert r.rx_power_dbm == pytest.approx(40.0 + 4.3 - loss, abs=1e-12)
        assert r.margin_db == pytest.approx(r.rx_power_dbm + 120.0, abs=1e-12)
        assert r.snr_db == pytest.approx(r.rx_power_dbm - r.noise_floor_dbm, abs=1e-12)


def test_compute_link_budget_rejects_bad_bandwidth() -> None:
    with pytest.raises(PhysicsInputError):
        compute_link_budget(_budget(bandwidth_hz=0.0))
