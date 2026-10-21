"""Deterministic free-space path-loss propagation model."""

from __future__ import annotations

from dataclasses import dataclass

from libraries.domain.radio import Radio
from libraries.domain.rf_results import LinkBudgetInput, PropagationResult
from libraries.physics import (
    SPEED_OF_LIGHT_M_S,
    dbm_from_watts,
    free_space_path_loss_db,
    received_power_dbm,
    slant_range_m,
)
from libraries.physics.errors import PhysicsInputError


@dataclass(frozen=True, slots=True)
class FreeSpaceValidityDomain:
    """Documented operating envelope for the MVP free-space model."""

    min_freq_hz: float = 30.0e6
    max_freq_hz: float = 100.0e9
    min_distance_m: float = 1.0
    max_distance_m: float = 1.0e9
    requires_terrain: bool = False


class FreeSpaceModel:
    """Free-space path loss with no terrain, fading, or multipath effects.

    Tx center frequency selects path loss when transmitter and receiver
    frequencies differ. Antenna patterns, polarization, antenna height,
    atmospheric loss, and shadowing are ignored in this MVP. The geometric
    range uses 3D slant distance, and path loss is floored at 0 dB because a
    passive free-space channel cannot provide gain. ``seed`` is accepted for
    Protocol compatibility and ignored because this model is deterministic.
    """

    name = "free_space"
    _VALIDITY_DOMAIN = FreeSpaceValidityDomain()

    def validity_domain(self) -> FreeSpaceValidityDomain:
        return self._VALIDITY_DOMAIN

    def evaluate(
        self,
        tx: Radio,
        rx: Radio,
        *,
        seed: int | None = None,
    ) -> PropagationResult:
        del seed
        if not isinstance(tx, Radio):
            raise PhysicsInputError(f"tx must be Radio; got {type(tx).__name__}")
        if not isinstance(rx, Radio):
            raise PhysicsInputError(f"rx must be Radio; got {type(rx).__name__}")

        distance = slant_range_m(tx.position, rx.position)
        raw_path_loss = free_space_path_loss_db(distance, tx.frequency.center_hz)
        path_loss = max(0.0, raw_path_loss)
        budget = LinkBudgetInput(
            tx_power_dbm=dbm_from_watts(tx.transmitter.power_watt),
            tx_gain_dbi=tx.antenna.gain_dBi,
            rx_gain_dbi=rx.antenna.gain_dBi,
            path_loss_db=path_loss,
            cable_loss_db=tx.transmitter.cable_loss_db,
            polarization_loss_db=0.0,
            atmospheric_loss_db=0.0,
            shadowing_db=0.0,
            bandwidth_hz=rx.frequency.bandwidth_hz,
            noise_figure_db=rx.receiver.noise_figure_dB,
            sensitivity_dbm=rx.receiver.sensitivity_dBm,
        )
        rx_power = received_power_dbm(budget)

        return PropagationResult(
            path_loss_db=path_loss,
            rx_power_dbm=rx_power,
            delay_s=distance / SPEED_OF_LIGHT_M_S,
            doppler_hz=0.0,
            los=True,
            multipath=(),
            fading_db=0.0,
        )
