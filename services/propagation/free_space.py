"""Free-space propagation model — the MVP propagation model of the project.

Free space is the baseline medium: an unobstructed path between two radios
with no terrain, no reflections, no shadowing and no fading. It is the model
the scenario engine selects by default, and the reference against which the
terrain-aware models (TwoRay, Hata, ITM, ray tracing) will be compared.

Scope of this model (task brief §5.8 - §5.11):

* Path loss is computed at the **transmitter's** centre frequency. When the
  two radios sit on different frequencies the model does not raise: whether
  they can hear each other is a spectral-overlap question for the
  interference engine, not a propagation question.
* The range used for path loss is the 3D **slant range** between the two
  ``GeoPosition`` values (surface distance plus altitude difference).
* ``Antenna.pattern`` (radiation pattern), ``Antenna.polarization`` and
  ``Antenna.height_m`` are ignored: free space does not depend on them in the
  MVP. Polarization loss, atmospheric loss and shadowing are 0 dB.
* Receive-side cable loss is 0 dB: the frozen ``Receiver`` type has no
  cable-loss field, only ``Transmitter`` does.
* ``seed`` is accepted for ``PropagationModel`` compatibility and ignored:
  free space has no stochastic component, so the result does not depend on a
  seed at all. Inventing randomness here would make the model less correct.
* Path loss is floored at 0 dB — a passive medium cannot provide gain.
"""

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
    """Operating envelope of the free-space model.

    The frozen ``ValidityDomain`` is a Protocol, so a concrete type is needed
    somewhere. The corners are chosen so that free-space path loss is
    non-negative everywhere inside the box (see ``__post_init__``-style note
    in the module docstring of the model):

    * ``min_distance_m = 1 m`` is the model clamp: below it the geometry is
      degenerate, and it is also the smallest distance for which the model
      is meant to be used.
    * ``min_freq_hz = 30 MHz`` is the lowest carrier the MVP cares about
      (VHF and up). At the near corner (1 m, 30 MHz) the path loss is
      ``+1.98 dB``, i.e. still non-negative.
    * ``max_freq_hz = 100 GHz`` covers everything from VHF to mm-wave.
    * ``max_distance_m = 1e9 m`` (1 000 000 km) keeps the model usable for
      space links; the path-loss formula itself has no upper distance
      limit, and the model never consults terrain, so there is nothing to
      invalidate at long range.

    Attributes:
        min_freq_hz: lowest supported carrier frequency, hertz.
        max_freq_hz: highest supported carrier frequency, hertz.
        min_distance_m: shortest supported separation, metres.
        max_distance_m: longest supported separation, metres.
        requires_terrain: always False — free space never reads terrain.
    """

    min_freq_hz: float = 30.0e6
    max_freq_hz: float = 100.0e9
    min_distance_m: float = 1.0
    max_distance_m: float = 1.0e9
    requires_terrain: bool = False


class FreeSpaceModel:
    """Deterministic free-space path-loss model.

    Implements the frozen ``PropagationModel`` Protocol
    (``libraries/plugin_sdk/propagation.py``): a pure function of
    ``(tx, rx)`` plus an optional seed that this model ignores.
    """

    name = "free_space"

    #: Shared, immutable validity domain. The dataclass is frozen, so a
    #: single instance can be handed out to concurrent callers safely.
    _VALIDITY_DOMAIN = FreeSpaceValidityDomain()

    def validity_domain(self) -> FreeSpaceValidityDomain:
        """Return the frequency/distance envelope this model is valid for.

        The RF core uses this to warn or refuse a model selection outside
        the envelope; ``evaluate()`` itself never raises for an
        out-of-domain point.
        """
        return self._VALIDITY_DOMAIN

    def evaluate(
        self,
        tx: Radio,
        rx: Radio,
        *,
        seed: int | None = None,
    ) -> PropagationResult:
        """Compute path loss and channel effects between ``tx`` and ``rx``.

        Args:
            tx: transmitting radio.
            rx: receiving radio.
            seed: accepted for Protocol compatibility and deliberately
                ignored — free space has no stochastic component, so the
                result is identical for every seed (including ``None``).

        Returns:
            A :class:`PropagationResult` whose every field is filled in:
            ``path_loss_db`` (floored at 0 dB), ``rx_power_dbm``,
            ``delay_s`` (slant range / c), ``doppler_hz`` (0 — the frozen
            ``Radio`` type carries no velocity), ``los`` (True — free space
            assumes an unobstructed path), ``multipath`` (empty) and
            ``fading_db`` (0).

        Raises:
            PhysicsInputError: if a radio argument is not a ``Radio``, or if
                the transmit power, frequency or position is not usable.
        """
        del seed  # free space is deterministic; the seed is irrelevant here.

        if not isinstance(tx, Radio):
            raise PhysicsInputError(f"tx must be Radio; got {type(tx).__name__}")
        if not isinstance(rx, Radio):
            raise PhysicsInputError(f"rx must be Radio; got {type(rx).__name__}")

        distance_m = slant_range_m(tx.position, rx.position)
        # Free space is passive: it can attenuate but never amplify, so the
        # path loss is floored at 0 dB (the raw formula goes negative in the
        # near field, where the radiating-field approximation breaks down).
        path_loss_db = max(0.0, free_space_path_loss_db(distance_m, tx.frequency.center_hz))

        budget = LinkBudgetInput(
            tx_power_dbm=dbm_from_watts(tx.transmitter.power_watt),
            tx_gain_dbi=tx.antenna.gain_dBi,
            rx_gain_dbi=rx.antenna.gain_dBi,
            path_loss_db=path_loss_db,
            cable_loss_db=tx.transmitter.cable_loss_db,
            polarization_loss_db=0.0,
            atmospheric_loss_db=0.0,
            shadowing_db=0.0,
            bandwidth_hz=rx.frequency.bandwidth_hz,
            noise_figure_db=rx.receiver.noise_figure_dB,
            sensitivity_dbm=rx.receiver.sensitivity_dBm,
        )

        return PropagationResult(
            path_loss_db=path_loss_db,
            rx_power_dbm=received_power_dbm(budget),
            delay_s=distance_m / SPEED_OF_LIGHT_M_S,
            doppler_hz=0.0,
            los=True,
            multipath=(),
            fading_db=0.0,
        )
