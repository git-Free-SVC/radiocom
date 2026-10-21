"""Link-budget arithmetic: received power, noise, SNR, margin, Eb/N0.

These functions are the reusable half of the RF core (architecture doc §9).
They know nothing about radios or propagation models, so a future TwoRay,
Hata or ITM model can reuse them unchanged.

The formulas, verbatim from the architecture doc §9::

    Pr(dBm)    = Pt + Gt + Gr - PL - Lcable - Lpol - Latm - Lshadow
    N(dBm)     = -174 + 10*log10(bandwidth_hz) + NF
    SNR(dB)    = Pr - N
    margin(dB) = Pr - sensitivity
    Eb/N0(dB)  = SNR + 10*log10(bandwidth_hz / bit_rate_hz)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality, LinkState

from ._validate import finite_float, finite_result, positive_float
from .constants import MARGINAL_MARGIN_DB, NOISE_DENSITY_DBM_HZ, UP_MARGIN_DB
from .errors import PhysicsInputError


@dataclass(frozen=True, slots=True)
class LinkBudgetResult:
    """Every quantity a link budget produces, for one link.

    Attributes:
        received_power_dbm: Pr at the receiver input.
        noise_floor_dbm: thermal noise plus receiver noise figure.
        snr_db: received power minus noise floor.
        margin_db: received power minus receiver sensitivity.
        eb_n0_db: energy per bit over noise density.
    """

    received_power_dbm: float
    noise_floor_dbm: float
    snr_db: float
    margin_db: float
    eb_n0_db: float


def dbm_from_watts(power_watt: float) -> float:
    """Convert a strictly positive power in watts to dBm.

    ``dBm = 10*log10(power_watt) + 30``.

    Raises:
        PhysicsInputError: if the power is not finite or not strictly positive
            (a radio that transmits 0 W or a negative power is a scenario
            bug, not a link budget).
    """
    power = positive_float("power_watt", power_watt)
    return finite_result("dbm_from_watts", 10.0 * math.log10(power) + 30.0)


def watts_from_dbm(power_dbm: float) -> float:
    """Convert a power in dBm back to watts.

    Raises:
        PhysicsInputError: if the value is not finite, or if the converted
            power is outside the representable float range (overflow to
            infinity, or underflow to zero).
    """
    dbm = finite_float("power_dbm", power_dbm)
    try:
        watts = 10.0 ** ((dbm - 30.0) / 10.0)
    except OverflowError as exc:
        raise PhysicsInputError(
            f"power_dbm is too large to convert to finite watts; got {dbm!r}"
        ) from exc
    if not math.isfinite(watts) or watts == 0.0:
        raise PhysicsInputError(f"power_dbm is outside the representable watt range; got {dbm!r}")
    return watts


def received_power_dbm(budget: LinkBudgetInput) -> float:
    """Return the received power ``Pr`` in dBm for ``budget``.

    ``Pr = Pt + Gt + Gr - PL - Lcable - Lpol - Latm - Lshadow``

    Raises:
        PhysicsInputError: if ``budget`` is not a :class:`LinkBudgetInput`, or
            if any term that takes part in the sum is not finite.
    """
    if not isinstance(budget, LinkBudgetInput):
        raise PhysicsInputError(f"budget must be LinkBudgetInput; got {type(budget).__name__}")

    tx_power = finite_float("tx_power_dbm", budget.tx_power_dbm)
    tx_gain = finite_float("tx_gain_dbi", budget.tx_gain_dbi)
    rx_gain = finite_float("rx_gain_dbi", budget.rx_gain_dbi)
    path_loss = finite_float("path_loss_db", budget.path_loss_db)
    cable_loss = finite_float("cable_loss_db", budget.cable_loss_db)
    polarization_loss = finite_float("polarization_loss_db", budget.polarization_loss_db)
    atmospheric_loss = finite_float("atmospheric_loss_db", budget.atmospheric_loss_db)
    shadowing = finite_float("shadowing_db", budget.shadowing_db)

    # fsum keeps the result exact to the last bit of the inputs instead of
    # accumulating the rounding error of eight separate additions.
    result = math.fsum(
        (
            tx_power,
            tx_gain,
            rx_gain,
            -path_loss,
            -cable_loss,
            -polarization_loss,
            -atmospheric_loss,
            -shadowing,
        )
    )
    return finite_result("received_power_dbm", result)


def noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float = 0.0) -> float:
    """Return the receiver noise floor in dBm.

    ``N = -174 + 10*log10(bandwidth_hz) + NF``

    Raises:
        PhysicsInputError: if the bandwidth is not finite and positive, or if
            the noise figure is not finite.
    """
    bandwidth = positive_float("bandwidth_hz", bandwidth_hz)
    noise_figure = finite_float("noise_figure_db", noise_figure_db)
    result = NOISE_DENSITY_DBM_HZ + 10.0 * math.log10(bandwidth) + noise_figure
    return finite_result("noise_floor_dbm", result)


def snr_db(received_dbm: float, noise_dbm: float) -> float:
    """Return the signal-to-noise ratio in dB: ``Pr - N``."""
    received = finite_float("received_dbm", received_dbm)
    noise = finite_float("noise_dbm", noise_dbm)
    return finite_result("snr_db", received - noise)


def link_margin_db(received_dbm: float, sensitivity_dbm: float) -> float:
    """Return the link margin in dB: ``Pr - sensitivity``.

    A positive margin means the receiver sensitivity is met with room to
    spare; a negative margin means the link does not close.
    """
    received = finite_float("received_dbm", received_dbm)
    sensitivity = finite_float("sensitivity_dbm", sensitivity_dbm)
    return finite_result("link_margin_db", received - sensitivity)


def eb_n0_db(snr: float, bandwidth_hz: float, bit_rate_hz: float) -> float:
    """Return Eb/N0 in dB.

    ``Eb/N0 = SNR + 10*log10(bandwidth_hz / bit_rate_hz)``

    Note this is a *link-budget* quantity only. Mapping Eb/N0 to a bit error
    rate is the job of ``WaveformCodec.ber()`` (architecture doc §9), which
    belongs to the DSP service, not to this package.

    Raises:
        PhysicsInputError: if the SNR, bandwidth or bit rate is not finite, or
            if the bandwidth or bit rate is not strictly positive.
    """
    snr_value = finite_float("snr_db", snr)
    bandwidth = positive_float("bandwidth_hz", bandwidth_hz)
    bit_rate = positive_float("bit_rate_hz", bit_rate_hz)
    # log10(bw) - log10(rate) instead of log10(bw / rate): the quotient can
    # underflow or overflow for extreme but finite inputs.
    result = snr_value + 10.0 * (math.log10(bandwidth) - math.log10(bit_rate))
    return finite_result("eb_n0_db", result)


def calculate_link_budget(
    budget: LinkBudgetInput, bit_rate_hz: float | None = None
) -> LinkBudgetResult:
    """Compute the whole link budget for ``budget``.

    Args:
        budget: the frozen link-budget input type.
        bit_rate_hz: symbol/bit rate used for Eb/N0. Defaults to the
            bandwidth of ``budget``, which makes Eb/N0 equal to the SNR.

    Raises:
        PhysicsInputError: for any invalid term, see the individual functions.
    """
    if not isinstance(budget, LinkBudgetInput):
        raise PhysicsInputError(f"budget must be LinkBudgetInput; got {type(budget).__name__}")
    bandwidth = positive_float("bandwidth_hz", budget.bandwidth_hz)
    received = received_power_dbm(budget)
    noise = noise_floor_dbm(bandwidth, budget.noise_figure_db)
    snr = snr_db(received, noise)
    margin = link_margin_db(received, budget.sensitivity_dbm)
    rate = bandwidth if bit_rate_hz is None else bit_rate_hz
    ebn0 = eb_n0_db(snr, bandwidth, rate)
    return LinkBudgetResult(
        received_power_dbm=received,
        noise_floor_dbm=noise,
        snr_db=snr,
        margin_db=margin,
        eb_n0_db=ebn0,
    )


def link_state(budget: LinkBudgetInput, bit_rate_hz: float | None = None) -> LinkState:
    """Return the frozen :class:`LinkState` for ``budget``.

    This is the "is the link up?" summary the scenario/event layer consumes:
    SNR, margin and a quality band.
    """
    result = calculate_link_budget(budget, bit_rate_hz=bit_rate_hz)
    return LinkState(
        snr_db=result.snr_db,
        margin_db=result.margin_db,
        quality=link_quality(result.margin_db),
    )


def link_quality(margin_db: float) -> LinkQuality:
    """Classify a link margin into a quality band.

    The bands are an engineering convention, not a frozen interface value
    (nothing in ``libraries/domain`` or ``libraries/plugin_sdk`` defines
    them), so they are called out here and in the PR description as a
    candidate for a future ADR:

    * ``UP``      -- margin >= 10 dB: the link closes with a usable buffer.
    * ``MARGINAL`` -- 0 dB <= margin < 10 dB: the link closes, but with
      little margin for fading or interference.
    * ``DOWN``    -- margin < 0 dB: the receiver sensitivity is not met.

    The function is exhaustive and monotonic: every finite margin maps to
    exactly one band, and a larger margin never maps to a worse band.

    Raises:
        PhysicsInputError: if the margin is not finite (a NaN margin has no
            meaningful band).
    """
    margin = finite_float("margin_db", margin_db)
    if margin >= UP_MARGIN_DB:
        return LinkQuality.UP
    if margin >= MARGINAL_MARGIN_DB:
        return LinkQuality.MARGINAL
    return LinkQuality.DOWN
