"""Category G of the stress campaign: regression tests for the model.

These lock in the two policy decisions of the free-space model that the
stress campaign kept trying to break: the one-metre clamp for co-located
radios and the zero-decibel floor for the near field.
"""

from __future__ import annotations

import math

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.physics import MIN_DISTANCE_M, free_space_path_loss_db
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


def test_regression_coincident_radios_use_the_one_metre_clamp() -> None:
    """Two radios at the same position must not crash the model with
    ``ValueError: math domain error`` from ``log10(0)``."""
    radio = _radio("same", 45.0)
    result = FreeSpaceModel().evaluate(radio, radio)
    assert math.isfinite(result.path_loss_db)
    assert result.path_loss_db == pytest.approx(
        free_space_path_loss_db(MIN_DISTANCE_M, radio.frequency.center_hz), abs=1e-12
    )
    assert result.delay_s == 0.0


def test_regression_near_field_path_loss_is_floored_at_zero() -> None:
    """The raw formula goes negative below ``c/(4*pi)``; a passive medium
    cannot provide gain, so the model floors the result."""
    tx = _radio("tx", 45.0, frequency_hz=1.0e3)
    rx = _radio("rx", 45.09, frequency_hz=1.0e3)
    assert free_space_path_loss_db(1.0, 1.0e3) < 0.0
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.path_loss_db == 0.0
    assert math.isfinite(result.rx_power_dbm)


def test_regression_frequency_mismatch_uses_the_transmitter_frequency() -> None:
    """A Tx/Rx frequency mismatch must not raise: the path loss is computed
    at the transmitter's centre frequency."""
    tx = _radio("tx", 45.0, frequency_hz=145.5e6)
    rx = _radio("rx", 45.09, frequency_hz=435.0e6)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.path_loss_db == pytest.approx(95.7038, abs=0.01)
