"""Contract for any PropagationModel. Must pass UNMODIFIED.

    pytest tests/contract/test_propagation_model_contract.py --propagation-impl=pkg.mod:Class
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.domain.rf_results import PropagationResult
from libraries.plugin_sdk.propagation import PropagationModel, ValidityDomain


def _radio(rid: str, lat: float, freq_hz: float = 145.5e6) -> Radio:
    return Radio(
        id=rid,
        frequency=Frequency(center_hz=freq_hz, bandwidth_hz=12.5e3),
        transmitter=Transmitter(power_watt=10.0),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0),
        position=GeoPosition(lat=lat, lon=6.0),
    )


@pytest.fixture
def sample_radios():
    return _radio("TX-01", 45.0), _radio("RX-01", 45.09)  # ~10 km


def test_conforms_to_protocol(model):
    assert isinstance(model, PropagationModel)
    assert isinstance(model.name, str) and model.name


def test_evaluate_returns_well_formed_result(model, sample_radios):
    r = model.evaluate(*sample_radios)
    assert isinstance(r, PropagationResult)
    assert math.isfinite(r.path_loss_db) and r.path_loss_db > 0
    assert math.isfinite(r.rx_power_dbm) and r.rx_power_dbm < 0
    assert isinstance(r.los, bool)
    assert r.delay_s >= 0


def test_deterministic_with_seed(model, sample_radios):
    tx, rx = sample_radios
    assert model.evaluate(tx, rx, seed=42) == model.evaluate(
        tx, rx, seed=42
    ), "same seed must give identical PropagationResult (§14)"


def test_validity_domain_declared(model):
    d = model.validity_domain()
    assert isinstance(d, ValidityDomain)
    assert 0 < d.min_freq_hz < d.max_freq_hz
    assert 0 <= d.min_distance_m < d.max_distance_m
    assert isinstance(d.requires_terrain, bool)


def test_path_loss_grows_with_distance(model):
    d = model.validity_domain()
    if d.requires_terrain:
        pytest.skip("terrain-dependent models need not be monotonic")
    tx = _radio("TX", 45.0)
    near = model.evaluate(tx, _radio("N", 45.009), seed=1)  # ~1 km
    far = model.evaluate(tx, _radio("F", 45.09), seed=1)  # ~10 km
    assert far.path_loss_db > near.path_loss_db


def test_path_loss_grows_with_frequency(model):
    d = model.validity_domain()
    if d.requires_terrain:
        pytest.skip("terrain-dependent models need not be monotonic")
    lo_f, hi_f = 145.5e6, 435.0e6
    if not (d.min_freq_hz <= lo_f and hi_f <= d.max_freq_hz):
        pytest.skip("test frequencies outside validity domain")
    lo = model.evaluate(_radio("A", 45.0, lo_f), _radio("B", 45.09, lo_f), seed=1)
    hi = model.evaluate(_radio("A", 45.0, hi_f), _radio("B", 45.09, hi_f), seed=1)
    assert hi.path_loss_db >= lo.path_loss_db


def test_more_tx_power_more_rx_power(model, sample_radios):
    tx, rx = sample_radios
    strong = replace(tx, transmitter=Transmitter(power_watt=100.0))
    assert (
        model.evaluate(strong, rx, seed=1).rx_power_dbm
        > model.evaluate(tx, rx, seed=1).rx_power_dbm
    )
