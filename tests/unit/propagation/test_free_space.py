from __future__ import annotations

import math
from dataclasses import replace

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.domain.rf_results import PropagationResult
from libraries.physics import (
    MIN_DISTANCE_M,
    PhysicsInputError,
    free_space_path_loss_db,
    slant_range_m,
)
from libraries.plugin_sdk.propagation import PropagationModel, ValidityDomain
from services.propagation import FreeSpaceModel, FreeSpaceValidityDomain


def _radio(
    rid: str,
    lat: float,
    lon: float = 6.0,
    frequency_hz: float = 145.5e6,
    power_watt: float = 10.0,
    gain_dbi: float = 2.15,
    alt_m: float = 0.0,
) -> Radio:
    return Radio(
        id=rid,
        frequency=Frequency(center_hz=frequency_hz, bandwidth_hz=12_500.0),
        transmitter=Transmitter(power_watt=power_watt),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=Antenna(antenna_type="dipole", gain_dBi=gain_dbi, height_m=10.0),
        position=GeoPosition(lat=lat, lon=lon, alt_m=alt_m),
    )


def test_free_space_model_implements_frozen_protocol_and_result_shape() -> None:
    model = FreeSpaceModel()
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    result = model.evaluate(tx, rx)
    assert isinstance(model, PropagationModel)
    assert model.name == "free_space"
    assert isinstance(result, PropagationResult)
    assert result.path_loss_db == pytest.approx(95.7038, abs=0.01)
    assert result.rx_power_dbm == pytest.approx(-51.40, abs=0.01)
    assert result.delay_s == pytest.approx(
        slant_range_m(tx.position, rx.position) / 299_792_458.0, abs=1e-15
    )
    assert result.doppler_hz == 0.0
    assert result.los is True
    assert result.multipath == ()
    assert result.fading_db == 0.0


def test_validity_domain_has_positive_fspl_at_all_corners() -> None:
    domain = FreeSpaceModel().validity_domain()
    assert isinstance(domain, ValidityDomain)
    assert isinstance(domain, FreeSpaceValidityDomain)
    assert domain.min_freq_hz < domain.max_freq_hz
    assert 0.0 <= domain.min_distance_m < domain.max_distance_m
    assert domain.requires_terrain is False
    for distance in (domain.min_distance_m, domain.max_distance_m):
        for frequency in (domain.min_freq_hz, domain.max_freq_hz):
            assert free_space_path_loss_db(distance, frequency) >= 0.0


def test_coincident_positions_use_one_meter_clamp_without_domain_error() -> None:
    radio = _radio("same", 0.0, 0.0)
    result = FreeSpaceModel().evaluate(radio, radio)
    assert MIN_DISTANCE_M == 1.0
    assert math.isfinite(result.path_loss_db)
    assert result.path_loss_db == pytest.approx(
        free_space_path_loss_db(1.0, radio.frequency.center_hz), abs=1e-12
    )
    assert result.delay_s == 0.0


def test_near_field_raw_negative_fspl_is_floored_to_zero() -> None:
    tx = _radio("tx", 0.0, 0.0, frequency_hz=1.0e3)
    rx = _radio("rx", 0.0, 0.0, frequency_hz=1.0e3)
    assert free_space_path_loss_db(1.0, 1.0e3) < 0.0
    assert FreeSpaceModel().evaluate(tx, rx).path_loss_db == 0.0


def test_tx_frequency_is_used_for_path_loss_when_frequencies_differ() -> None:
    tx = _radio("tx", 45.0, frequency_hz=145.5e6)
    rx = _radio("rx", 45.09, frequency_hz=435.0e6)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.path_loss_db == pytest.approx(
        free_space_path_loss_db(slant_range_m(tx.position, rx.position), 145.5e6),
        abs=1e-12,
    )


def test_rx_power_mapping_uses_tx_cable_and_both_antenna_gains() -> None:
    tx = _radio("tx", 45.0, gain_dbi=3.0)
    tx = replace(tx, transmitter=Transmitter(power_watt=10.0, cable_loss_db=1.25))
    rx = _radio("rx", 45.09, gain_dbi=4.0)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.rx_power_dbm == pytest.approx(
        40.0 + 3.0 + 4.0 - result.path_loss_db - 1.25, abs=1e-12
    )


def test_result_is_independent_of_seed_and_repeatedly_bit_identical() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    expected = model.evaluate(tx, rx)
    for seed in (None, 0, 1, 42, -1, 2**63):
        assert model.evaluate(tx, rx, seed=seed) == expected
    assert all(model.evaluate(tx, rx) == expected for _ in range(1_000))


def test_symmetric_radios_give_symmetric_path_loss() -> None:
    a = _radio("a", 45.0)
    b = _radio("b", 45.09)
    model = FreeSpaceModel()
    assert model.evaluate(a, b).path_loss_db == model.evaluate(b, a).path_loss_db


def test_evaluate_does_not_mutate_frozen_radio_inputs() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    before = (tx, rx, tx.position, rx.position, tx.frequency, rx.frequency)
    FreeSpaceModel().evaluate(tx, rx)
    assert (tx, rx, tx.position, rx.position, tx.frequency, rx.frequency) == before


def test_invalid_transmit_power_and_frequency_raise_physics_input_error() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    bad_power = replace(tx, transmitter=Transmitter(power_watt=float("nan")))
    with pytest.raises(PhysicsInputError, match="power_watt"):
        FreeSpaceModel().evaluate(bad_power, rx)
    bad_frequency = replace(tx, frequency=Frequency(center_hz=float("nan"), bandwidth_hz=12_500.0))
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        FreeSpaceModel().evaluate(bad_frequency, rx)


def test_invalid_radio_argument_has_clear_error() -> None:
    with pytest.raises(PhysicsInputError, match="tx must be Radio"):
        FreeSpaceModel().evaluate(None, _radio("rx", 45.09))  # type: ignore[arg-type]
