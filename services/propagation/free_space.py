"""Free-space propagation model (Friis).

Implements the frozen ``PropagationModel`` Protocol
(``libraries.plugin_sdk.propagation``). Radio -> link-budget mapping:

* frequency for path loss      : ``tx.frequency.center_hz``
* transmit power               : ``tx.transmitter.power_watt``
* cable loss                   : ``tx.transmitter.cable_loss_db``
* antenna gains                : ``tx.antenna.gain_dBi`` / ``rx.antenna.gain_dBi``

MVP simplifications (deliberate, do not "fix" here): antenna patterns and
polarization are ignored, atmospheric loss and shadowing are 0, ``height_m``
is not added to ``alt_m``, Doppler is 0 (``Radio`` carries no velocity).

A tx/rx centre-frequency mismatch does NOT raise: path loss is computed at the
transmitter's frequency. Whether the radios can hear each other is a
spectral-overlap question, not a propagation question.

Pure and deterministic: no randomness, no shared mutable state. ``seed`` is
accepted for interface compatibility and ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

from libraries.domain.radio import Radio
from libraries.domain.rf_results import PropagationResult
from libraries.physics.constants import MIN_DISTANCE_M, SPEED_OF_LIGHT_M_S
from libraries.physics.distance import slant_range_m
from libraries.physics.link_budget import received_power_dbm, watts_to_dbm
from libraries.physics.path_loss import free_space_path_loss_db


@dataclass(frozen=True, slots=True)
class FreeSpaceValidityDomain:
    """Concrete ``ValidityDomain`` for free space.

    Corners are chosen so free-space loss is >= 0 dB everywhere inside the
    domain (at 1 m / 30 MHz it is ~1.98 dB). The upper distance bound covers
    cislunar links; the frequency range is 30 MHz (VHF) to 100 GHz.
    """

    min_freq_hz: float = 30.0e6
    max_freq_hz: float = 100.0e9
    min_distance_m: float = MIN_DISTANCE_M
    max_distance_m: float = 1.0e9
    requires_terrain: bool = False


class FreeSpaceModel:
    """Friis free-space path loss between two radios."""

    name: str = "free_space"

    def validity_domain(self) -> FreeSpaceValidityDomain:
        return FreeSpaceValidityDomain()

    def evaluate(
        self,
        tx: Radio,
        rx: Radio,
        *,
        seed: int | None = None,
    ) -> PropagationResult:
        """Compute free-space path loss and received power.

        * ``path_loss_db``: FSPL at the slant range, with the distance clamped to
          at least ``MIN_DISTANCE_M`` and the result floored at 0 dB (a passive
          medium cannot provide gain; only matters outside the validity domain).
        * ``rx_power_dbm``: ``Pt + Gt + Gr - PL - Lcable``.
        * ``delay_s``: ``slant_range / c`` (unclamped).
        * ``doppler_hz=0.0``, ``los=True``, ``multipath=()``, ``fading_db=0.0``.

        Does not raise or warn outside the validity domain. Never returns
        NaN/inf.

        Raises:
            PhysicsInputError: invalid coordinates, frequency, or power.
        """
        del seed  # deterministic model: independent of the seed (see tests)

        distance_m = slant_range_m(tx.position, rx.position)
        effective_m = max(distance_m, MIN_DISTANCE_M)

        path_loss_db = max(0.0, free_space_path_loss_db(effective_m, tx.frequency.center_hz))
        rx_power_dbm = received_power_dbm(
            tx_power_dbm=watts_to_dbm(tx.transmitter.power_watt),
            tx_gain_dbi=tx.antenna.gain_dBi,
            rx_gain_dbi=rx.antenna.gain_dBi,
            path_loss_db=path_loss_db,
            cable_loss_db=tx.transmitter.cable_loss_db,
        )
        return PropagationResult(
            path_loss_db=path_loss_db,
            rx_power_dbm=rx_power_dbm,
            delay_s=distance_m / SPEED_OF_LIGHT_M_S,
            doppler_hz=0.0,
            los=True,
            multipath=(),
            fading_db=0.0,
        )
