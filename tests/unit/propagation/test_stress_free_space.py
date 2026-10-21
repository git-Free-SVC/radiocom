"""Categories D and F of the stress campaign: contract, determinism,
concurrency, sweeps and performance of the free-space model.
"""

from __future__ import annotations

import concurrent.futures
import math
import time
from dataclasses import replace

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.physics import SPEED_OF_LIGHT_M_S, free_space_path_loss_db, slant_range_m
from services.propagation import FreeSpaceModel


def _radio(
    rid: str,
    lat: float,
    lon: float = 6.0,
    frequency_hz: float = 145.5e6,
    alt_m: float = 0.0,
) -> Radio:
    return Radio(
        id=rid,
        frequency=Frequency(center_hz=frequency_hz, bandwidth_hz=12_500.0),
        transmitter=Transmitter(power_watt=10.0),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0),
        position=GeoPosition(lat=lat, lon=lon, alt_m=alt_m),
    )


def test_one_thousand_repeated_evaluations_are_bit_identical() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    expected = model.evaluate(tx, rx)
    for _ in range(1_000):
        assert model.evaluate(tx, rx) == expected


@pytest.mark.parametrize("seed", [None, 0, 1, 42, -1, 2**63])
def test_every_seed_gives_the_same_result(seed: int | None) -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    assert model.evaluate(tx, rx, seed=seed) == model.evaluate(tx, rx)


def test_concurrent_evaluations_on_shared_radios_are_deterministic() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    expected = model.evaluate(tx, rx)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: model.evaluate(tx, rx), range(2_000)))
    assert all(result == expected for result in results)
    # The frozen inputs must be untouched by concurrent callers.
    assert tx.position == GeoPosition(lat=45.0, lon=6.0)
    assert rx.position == GeoPosition(lat=45.09, lon=6.0)
    assert tx.frequency == Frequency(center_hz=145.5e6, bandwidth_hz=12_500.0)


def test_evaluation_order_does_not_matter() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    forward = model.evaluate(tx, rx)
    backward = model.evaluate(rx, tx)
    assert forward.path_loss_db == backward.path_loss_db
    assert forward.delay_s == backward.delay_s


def test_result_fields_have_the_documented_values() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.delay_s == pytest.approx(
        slant_range_m(tx.position, rx.position) / SPEED_OF_LIGHT_M_S, rel=1e-15
    )
    assert result.doppler_hz == 0.0
    assert result.fading_db == 0.0
    assert result.multipath == ()
    assert result.los is True
    assert result.path_loss_db >= 0.0
    assert math.isfinite(result.rx_power_dbm)


def test_validity_domain_satisfies_the_contract_checks() -> None:
    domain = FreeSpaceModel().validity_domain()
    assert 0 < domain.min_freq_hz < domain.max_freq_hz
    assert 0 <= domain.min_distance_m < domain.max_distance_m
    assert isinstance(domain.requires_terrain, bool)
    for distance in (domain.min_distance_m, domain.max_distance_m):
        for frequency in (domain.min_freq_hz, domain.max_freq_hz):
            assert free_space_path_loss_db(distance, frequency) >= 0.0


def test_rx_bandwidth_does_not_change_the_propagation_result() -> None:
    """Bandwidth matters for the noise floor, not for path loss."""
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    original = model.evaluate(tx, rx)
    for bandwidth in (1.0e-9, 1.0e18):
        changed = replace(
            rx, frequency=Frequency(center_hz=rx.frequency.center_hz, bandwidth_hz=bandwidth)
        )
        assert model.evaluate(tx, changed).rx_power_dbm == original.rx_power_dbm


def test_one_hundred_thousand_evaluations_stay_within_the_time_budget() -> None:
    """Generous bound (5 s) so CI does not flake on a loaded machine."""
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    start = time.perf_counter()
    for _ in range(100_000):
        result = model.evaluate(tx, rx)
        assert math.isfinite(result.path_loss_db)
    elapsed = time.perf_counter() - start
    nanoseconds_per_call = elapsed / 100_000 * 1e9
    print(f"100000 evaluate() calls in {elapsed:.3f} s ({nanoseconds_per_call:.0f} ns/call)")
    assert elapsed > 0.0
    assert elapsed < 5.0
