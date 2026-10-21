"""Unit tests for the free-space propagation model."""

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
    SPEED_OF_LIGHT_M_S,
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


def test_model_implements_the_frozen_protocol() -> None:
    model = FreeSpaceModel()
    assert isinstance(model, PropagationModel)
    assert model.name == "free_space"
    assert isinstance(model.name, str) and model.name


def test_result_matches_the_worked_contract_fixture() -> None:
    """Task brief §5.3 / §5.9: every field of the result is filled in."""
    tx, rx = _radio("TX-01", 45.0), _radio("RX-01", 45.09)
    result = FreeSpaceModel().evaluate(tx, rx)

    assert isinstance(result, PropagationResult)
    assert result.path_loss_db == pytest.approx(95.7038, abs=0.01)
    assert result.rx_power_dbm == pytest.approx(-51.40, abs=0.01)
    assert result.delay_s == pytest.approx(33.38e-6, rel=1e-3)
    assert result.doppler_hz == 0.0
    assert result.los is True
    assert result.multipath == ()
    assert result.fading_db == 0.0


def test_delay_is_the_slant_range_over_the_speed_of_light() -> None:
    tx, rx = _radio("TX-01", 45.0), _radio("RX-01", 45.09)
    result = FreeSpaceModel().evaluate(tx, rx)
    expected = slant_range_m(tx.position, rx.position) / SPEED_OF_LIGHT_M_S
    assert result.delay_s == pytest.approx(expected, rel=1e-15)


def test_validity_domain_is_declared_and_consistent() -> None:
    domain = FreeSpaceModel().validity_domain()
    assert isinstance(domain, ValidityDomain)
    assert isinstance(domain, FreeSpaceValidityDomain)
    assert domain.min_freq_hz < domain.max_freq_hz
    assert 0.0 <= domain.min_distance_m < domain.max_distance_m
    assert domain.requires_terrain is False
    assert domain.min_freq_hz == 30.0e6
    assert domain.max_freq_hz == 100.0e9
    assert domain.min_distance_m == 1.0
    assert domain.max_distance_m == 1.0e9


def test_path_loss_is_non_negative_at_every_corner_of_the_validity_domain() -> None:
    domain = FreeSpaceModel().validity_domain()
    for distance in (domain.min_distance_m, domain.max_distance_m):
        for frequency in (domain.min_freq_hz, domain.max_freq_hz):
            assert free_space_path_loss_db(distance, frequency) >= 0.0


def test_coincident_positions_use_the_one_metre_clamp() -> None:
    """Degenerate but legal input: two radios at the same position."""
    radio = _radio("same", 0.0, 0.0)
    result = FreeSpaceModel().evaluate(radio, radio)

    assert MIN_DISTANCE_M == 1.0
    assert math.isfinite(result.path_loss_db)
    assert result.path_loss_db == pytest.approx(
        free_space_path_loss_db(1.0, radio.frequency.center_hz), abs=1e-12
    )
    assert result.delay_s == 0.0
    assert result.los is True


def test_near_field_path_loss_is_floored_at_zero() -> None:
    """The raw formula goes negative below ``c/(4*pi)``; a passive medium
    cannot provide gain."""
    tx = _radio("tx", 0.0, 0.0, frequency_hz=1.0e3)
    rx = _radio("rx", 0.0, 0.0, frequency_hz=1.0e3)
    assert free_space_path_loss_db(1.0, 1.0e3) < 0.0
    assert FreeSpaceModel().evaluate(tx, rx).path_loss_db == 0.0


def test_transmitter_frequency_selects_the_path_loss() -> None:
    """A frequency mismatch is a spectral-overlap question, not a propagation
    question: the model must not raise."""
    tx = _radio("tx", 45.0, frequency_hz=145.5e6)
    rx = _radio("rx", 45.09, frequency_hz=435.0e6)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.path_loss_db == pytest.approx(
        free_space_path_loss_db(slant_range_m(tx.position, rx.position), 145.5e6),
        abs=1e-12,
    )


def test_received_power_uses_transmitter_power_cable_loss_and_both_gains() -> None:
    tx = _radio("tx", 45.0, gain_dbi=3.0)
    tx = replace(tx, transmitter=Transmitter(power_watt=10.0, cable_loss_db=1.25))
    rx = _radio("rx", 45.09, gain_dbi=4.0)
    result = FreeSpaceModel().evaluate(tx, rx)
    assert result.rx_power_dbm == pytest.approx(
        40.0 + 3.0 + 4.0 - result.path_loss_db - 1.25, abs=1e-12
    )


def test_antenna_pattern_polarization_and_height_are_ignored() -> None:
    """MVP simplification: free space does not depend on them."""
    plain = Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0)
    fancy = Antenna(
        antenna_type="parabolic",
        gain_dBi=2.15,
        height_m=250.0,
        pattern=lambda az, el: -20.0,
        polarization="horizontal",
    )
    tx = _radio("tx", 45.0)
    rx = _radio("rx", 45.09)
    plain_result = FreeSpaceModel().evaluate(replace(tx, antenna=plain), replace(rx, antenna=plain))
    fancy_result = FreeSpaceModel().evaluate(replace(tx, antenna=fancy), replace(rx, antenna=fancy))
    assert plain_result == fancy_result


def test_result_does_not_depend_on_the_seed() -> None:
    """Free space has no stochastic component: the seed is a no-op."""
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    model = FreeSpaceModel()
    expected = model.evaluate(tx, rx)
    for seed in (None, 0, 1, 42, -1, 2**63):
        assert model.evaluate(tx, rx, seed=seed) == expected


def test_symmetric_radios_give_symmetric_path_loss() -> None:
    a, b = _radio("a", 45.0), _radio("b", 45.09)
    model = FreeSpaceModel()
    assert model.evaluate(a, b).path_loss_db == model.evaluate(b, a).path_loss_db


def test_evaluate_does_not_mutate_its_frozen_inputs() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    before = (tx, rx, tx.position, rx.position, tx.frequency, rx.frequency)
    FreeSpaceModel().evaluate(tx, rx)
    assert (tx, rx, tx.position, rx.position, tx.frequency, rx.frequency) == before


def test_invalid_radio_argument_is_reported() -> None:
    with pytest.raises(PhysicsInputError, match="tx must be Radio"):
        FreeSpaceModel().evaluate(None, _radio("rx", 45.09))  # type: ignore[arg-type]
    with pytest.raises(PhysicsInputError, match="rx must be Radio"):
        FreeSpaceModel().evaluate(_radio("tx", 45.0), None)  # type: ignore[arg-type]


def test_invalid_transmit_power_is_reported() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    bad = replace(tx, transmitter=Transmitter(power_watt=float("nan")))
    with pytest.raises(PhysicsInputError, match="power_watt"):
        FreeSpaceModel().evaluate(bad, rx)


def test_invalid_frequency_is_reported() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    bad = replace(tx, frequency=Frequency(center_hz=float("nan"), bandwidth_hz=12_500.0))
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        FreeSpaceModel().evaluate(bad, rx)


def test_zero_transmit_power_is_reported() -> None:
    tx, rx = _radio("tx", 45.0), _radio("rx", 45.09)
    bad = replace(tx, transmitter=Transmitter(power_watt=0.0))
    with pytest.raises(PhysicsInputError, match="power_watt"):
        FreeSpaceModel().evaluate(bad, rx)
