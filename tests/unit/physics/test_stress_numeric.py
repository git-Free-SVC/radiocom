"""Category E of the stress campaign: sweeps and numeric accuracy.

Two independent things are checked here:

* the implementation agrees with a high-precision (``decimal``, 60-digit)
  reference over the whole operating range, and
* a dense grid of link budgets produces finite, invariant results.
"""

from __future__ import annotations

import math
import random
from decimal import Decimal, localcontext

import pytest

from libraries.domain.rf_results import LinkBudgetInput
from libraries.physics import (
    dbm_from_watts,
    free_space_path_loss_db,
    link_margin_db,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
)

# Golden values produced by an independent 60-digit Decimal computation of
#   FSPL(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44
# (see the PR description; the generator is not part of the implementation).
GOLDEN_FSPL_DB: tuple[tuple[float, float, float], ...] = (
    (1.0, 1.0e3, -87.56),
    (10.0, 1.0e3, -67.56),
    (1000.0, 1.0e3, -27.56),
    (1.0e6, 1.0e3, 32.44),
    (1.0, 1.0e6, -27.56),
    (100.0, 1.0e6, 12.44),
    (1.0e6, 1.0e6, 92.44),
    (1.0, 3.0e7, 1.9824250943932487),
    (10.0, 3.0e7, 21.98242509439325),
    (1000.0, 3.0e7, 61.98242509439325),
    (1.0e6, 3.0e7, 121.98242509439325),
    (1.0, 145.5e6, 15.697259866438522),
    (1000.0, 145.5e6, 75.69725986643853),
    (10_000.0, 145.5e6, 95.69725986643853),
    (10_007.5, 145.5e6, 95.70377184198138),
    (1.0e6, 145.5e6, 135.69725986643851),
    (1.0, 1.0e9, 32.44),
    (100.0, 1.0e9, 72.44),
    (1.0e6, 1.0e9, 152.44),
    (1.0, 1.0e10, 52.44),
    (1000.0, 1.0e10, 112.44),
    (1.0e6, 1.0e10, 172.44),
    (1.0, 1.0e11, 72.44),
    (1.0e6, 1.0e11, 192.44),
    (123.456, 725.0e6, 71.47700416397531),
    (3.5e7, 2.4e9, 190.92558572123764),
    (77_700.0, 868.0e6, 129.01881487954813),
    (999.0e6, 1.0e9, 212.43130976451965),
    (1.0, 1.0e12, 92.44),
    (1.0e9, 1.0e12, 272.44),
)


def decimal_fspl_db(distance_m: float, frequency_hz: float) -> float:
    """High-precision reference, independent of the float implementation."""
    with localcontext() as ctx:
        ctx.prec = 60
        distance_km = Decimal(distance_m) / Decimal(1000)
        frequency_mhz = Decimal(frequency_hz) / Decimal(1_000_000)
        return float(20 * (distance_km.log10() + frequency_mhz.log10()) + Decimal("32.44"))


@pytest.mark.parametrize(("distance", "frequency", "expected"), GOLDEN_FSPL_DB)
def test_fspl_matches_independent_decimal_golden_values(
    distance: float, frequency: float, expected: float
) -> None:
    """Tolerance: 1e-9 dB (the float implementation carries ~1e-13 dB)."""
    assert free_space_path_loss_db(distance, frequency) == pytest.approx(expected, abs=1e-9)


def test_maximum_error_against_the_decimal_reference_is_negligible() -> None:
    """Maximum observed absolute error over the golden set, in dB."""
    errors = [
        abs(free_space_path_loss_db(distance, frequency) - expected)
        for distance, frequency, expected in GOLDEN_FSPL_DB
    ]
    maximum_error_db = max(errors)
    print(f"maximum FSPL error vs decimal reference: {maximum_error_db:.3e} dB")
    assert maximum_error_db < 1e-9


def test_error_against_decimal_stays_small_on_a_wide_random_grid() -> None:
    rng = random.Random(20240521)
    maximum_error_db = 0.0
    for _ in range(2_000):
        # Distances stay at or above the 1 m clamp: below it the model
        # intentionally substitutes the clamp value (tested separately).
        distance = 10.0 ** rng.uniform(0.0, 9.0)
        frequency = 10.0 ** rng.uniform(3.0, 12.0)
        error = abs(
            free_space_path_loss_db(distance, frequency) - decimal_fspl_db(distance, frequency)
        )
        maximum_error_db = max(maximum_error_db, error)
    print(f"maximum FSPL error on random grid: {maximum_error_db:.3e} dB")
    assert maximum_error_db < 1e-9


def test_dense_grid_sweep_is_finite_and_invariant() -> None:
    """50 000 link budgets across distance x frequency x power x bandwidth."""
    distances = [10.0 ** (6.0 * index / 9.0) for index in range(10)]
    frequencies = [10.0 ** (3.0 + 8.0 * index / 9.0) for index in range(10)]
    powers = [10.0 ** (-6.0 + 18.0 * index / 9.0) for index in range(10)]
    bandwidths = [10.0 ** (-9.0 + 27.0 * index / 49.0) for index in range(50)]

    count = 0
    for distance in distances:
        for frequency in frequencies:
            path_loss = max(0.0, free_space_path_loss_db(distance, frequency))
            for power in powers:
                tx_power_dbm = dbm_from_watts(power)
                for bandwidth in bandwidths:
                    budget = LinkBudgetInput(
                        tx_power_dbm=tx_power_dbm,
                        tx_gain_dbi=2.15,
                        rx_gain_dbi=2.15,
                        path_loss_db=path_loss,
                        bandwidth_hz=bandwidth,
                        noise_figure_db=5.0,
                        sensitivity_dbm=-120.0,
                    )
                    received = received_power_dbm(budget)
                    noise = noise_floor_dbm(bandwidth, 5.0)
                    snr = snr_db(received, noise)
                    margin = link_margin_db(received, -120.0)
                    assert math.isfinite(path_loss)
                    assert math.isfinite(received)
                    assert math.isfinite(noise)
                    assert math.isfinite(snr)
                    assert math.isfinite(margin)
                    assert snr == pytest.approx(received - noise, abs=1e-9)
                    assert margin == pytest.approx(received + 120.0, abs=1e-9)
                    assert path_loss >= 0.0
                    count += 1
    assert count == 50_000
