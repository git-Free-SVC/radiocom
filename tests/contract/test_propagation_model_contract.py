"""Contract test for any PropagationModel implementation.

Run against a concrete implementation with:
    pytest tests/contract/test_propagation_model_contract.py --impl=services.propagation.free_space:FreeSpaceModel

Any Wave-1 agent implementing PropagationModel must pass this file unmodified.
"""

from __future__ import annotations

import importlib

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.plugin_sdk.propagation import PropagationModel


def _load_impl(impl_path: str) -> PropagationModel:
    module_path, _, cls_name = impl_path.partition(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)
    return cls()


@pytest.fixture
def model(request) -> PropagationModel:
    impl_path = request.config.getoption("--impl")
    return _load_impl(impl_path)


@pytest.fixture
def sample_radios() -> tuple[Radio, Radio]:
    antenna = Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0)
    tx = Radio(
        id="TX-01",
        frequency=Frequency(center_hz=145.5e6, bandwidth_hz=12.5e3),
        transmitter=Transmitter(power_watt=10.0),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=antenna,
        position=GeoPosition(lat=45.0, lon=6.0, alt_m=0.0),
    )
    rx = Radio(
        id="RX-01",
        frequency=tx.frequency,
        transmitter=tx.transmitter,
        receiver=tx.receiver,
        antenna=antenna,
        position=GeoPosition(lat=45.09, lon=6.0, alt_m=0.0),  # ~10 km north
    )
    return tx, rx


def test_conforms_to_protocol(model: PropagationModel) -> None:
    assert isinstance(model, PropagationModel)
    assert isinstance(model.name, str) and model.name


def test_evaluate_returns_result(model, sample_radios) -> None:
    tx, rx = sample_radios
    result = model.evaluate(tx, rx)
    assert result.path_loss_db > 0
    assert result.rx_power_dbm < 0  # sanity: never a positive received dBm here
    assert isinstance(result.los, bool)


def test_deterministic_with_seed(model, sample_radios) -> None:
    tx, rx = sample_radios
    r1 = model.evaluate(tx, rx, seed=42)
    r2 = model.evaluate(tx, rx, seed=42)
    assert r1 == r2, "same seed must produce identical PropagationResult (§14 determinism)"


def test_validity_domain_declared(model) -> None:
    domain = model.validity_domain()
    assert domain.min_freq_hz < domain.max_freq_hz
    assert domain.min_distance_m < domain.max_distance_m


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--impl",
        action="store",
        default="tests.contract.fakes.null_propagation_model:NullPropagationModel",
        help="module:ClassName of the PropagationModel implementation under test",
    )
