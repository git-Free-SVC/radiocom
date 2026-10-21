from __future__ import annotations

import concurrent.futures
import math
import time
from dataclasses import replace

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.physics import PhysicsInputError
from services.propagation import FreeSpaceModel


def _radio(rid: str, lat: float, lon: float = 6.0, frequency_hz: float = 145.5e6) -> Radio:
    return Radio(
        id=rid,
        frequency=Frequency(center_hz=frequency_hz, bandwidth_hz=12_500.0),
        transmitter=Transmitter(power_watt=10.0),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0),
        position=GeoPosition(lat=lat, lon=lon),
    )


def test_concurrent_shared_radio_calls_are_deterministic() -> None:
    model = FreeSpaceModel()
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    expected = model.evaluate(tx, rx)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: model.evaluate(tx, rx), range(2_000)))
    assert all(result == expected for result in results)
    assert tx.position == GeoPosition(lat=45.0, lon=6.0)
    assert rx.position == GeoPosition(lat=45.09, lon=6.0)


def test_evaluate_performance_100000_calls_under_five_seconds() -> None:
    model = FreeSpaceModel()
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    start = time.perf_counter()
    for _ in range(100_000):
        result = model.evaluate(tx, rx)
        assert math.isfinite(result.path_loss_db)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    assert elapsed > 0.0


def test_rx_bandwidth_does_not_change_propagation_received_power() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    original = model.evaluate(tx, rx)
    for bandwidth in (1.0e-9, 1.0e18):
        changed_rx = replace(
            rx,
            frequency=Frequency(center_hz=rx.frequency.center_hz, bandwidth_hz=bandwidth),
        )
        assert model.evaluate(tx, changed_rx).rx_power_dbm == original.rx_power_dbm


def test_zero_transmit_power_rejects_with_named_error() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    bad_power_tx = replace(tx, transmitter=Transmitter(power_watt=0.0))
    try:
        FreeSpaceModel().evaluate(bad_power_tx, rx)
    except PhysicsInputError as exc:
        assert "power_watt" in str(exc)
    else:
        raise AssertionError("zero transmit power must be rejected")
