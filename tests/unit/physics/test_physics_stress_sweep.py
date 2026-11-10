"""Dense sweeps: every invariant on every grid point, no NaN/inf anywhere."""

from __future__ import annotations

import math

import pytest

from libraries.domain.rf_results import LinkBudgetInput
from libraries.physics.link_budget import compute_link_budget, noise_floor_dbm, watts_to_dbm
from libraries.physics.path_loss import free_space_path_loss_db


def _logspace(lo_exp: float, hi_exp: float, n: int) -> list[float]:
    return [10.0 ** (lo_exp + (hi_exp - lo_exp) * i / (n - 1)) for i in range(n)]


def test_sweep_distance_x_frequency_50k_points() -> None:
    dists = _logspace(-3, 9, 250)  # 1 mm .. 1e9 m
    freqs = _logspace(3, 11, 200)  # 1 kHz .. 100 GHz  -> 50,000 points
    prev_row: list[float] | None = None
    points = 0
    for d in dists:
        row = [free_space_path_loss_db(d, f) for f in freqs]
        assert all(math.isfinite(v) for v in row)
        assert row == sorted(row)  # strictly increasing with frequency
        if prev_row is not None:
            assert all(b > a for a, b in zip(prev_row, row))  # and with distance
        prev_row = row
        points += len(row)
    assert points >= 50_000


@pytest.mark.parametrize("bw", [1.0, 12.5e3, 1e6, 100e6])
def test_sweep_link_budget_grid_invariants(bw: float) -> None:
    for power_w in _logspace(-3, 3, 13):
        for pl in [float(x) for x in range(0, 301, 5)]:
            for nf in (0.0, 5.0, 12.0):
                b = LinkBudgetInput(
                    tx_power_dbm=watts_to_dbm(power_w),
                    tx_gain_dbi=3.0,
                    rx_gain_dbi=3.0,
                    path_loss_db=pl,
                    bandwidth_hz=bw,
                    noise_figure_db=nf,
                    sensitivity_dbm=-110.0,
                )
                r = compute_link_budget(b)
                assert all(
                    math.isfinite(v)
                    for v in (r.rx_power_dbm, r.noise_floor_dbm, r.snr_db, r.margin_db)
                )
                assert r.snr_db == pytest.approx(r.rx_power_dbm - noise_floor_dbm(bw, nf), abs=1e-9)
                assert r.margin_db == pytest.approx(r.rx_power_dbm + 110.0, abs=1e-9)
