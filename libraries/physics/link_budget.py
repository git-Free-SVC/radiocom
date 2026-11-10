"""Link-budget math (architecture doc §9). Pure functions, no I/O.

    Pr(dBm)    = Pt + Gt + Gr - PL - Lcable - Lpol - Latm - Lshadow
    N(dBm)     = -174 + 10*log10(bandwidth_hz) + NF
    SNR(dB)    = Pr - N
    margin(dB) = Pr - sensitivity
    Eb/N0(dB)  = SNR + 10*log10(bandwidth_hz / bit_rate_hz)

Loss terms are *subtracted*. They are validated as finite but not sign-checked:
a negative value acts as a gain (shadowing may legitimately be negative).

Sources: Pozar, *Microwave Engineering*, ch. 14; Rappaport, *Wireless
Communications*, ch. 3-4; thermal noise ``kTB`` at T0 = 290 K.

Every function validates its inputs and raises ``PhysicsInputError``; no
function returns NaN or inf.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality, LinkState
from libraries.physics import _validate
from libraries.physics.constants import THERMAL_NOISE_DBM_PER_HZ
from libraries.physics.errors import PhysicsInputError
from libraries.physics.quality import link_quality

_DBM_PER_DBW: float = 30.0


@dataclass(frozen=True, slots=True)
class LinkBudgetResult:
    """Outputs of :func:`compute_link_budget`, all in dB / dBm."""

    rx_power_dbm: float
    noise_floor_dbm: float
    snr_db: float
    margin_db: float
    quality: LinkQuality

    def to_link_state(self) -> LinkState:
        """Project onto the frozen ``LinkState`` domain type."""
        return LinkState(snr_db=self.snr_db, margin_db=self.margin_db, quality=self.quality)


def watts_to_dbm(power_watt: float) -> float:
    """``dBm = 10*log10(P_W) + 30``. Requires finite ``power_watt > 0``."""
    p = _validate.positive("power_watt", power_watt)
    return 10.0 * math.log10(p) + _DBM_PER_DBW


def dbm_to_watts(power_dbm: float) -> float:
    """``P_W = 10**((dBm - 30) / 10)``.

    Raises ``PhysicsInputError`` if the result overflows or underflows to 0.
    """
    dbm = _validate.finite("power_dbm", power_dbm)
    try:
        watts = 10.0 ** ((dbm - _DBM_PER_DBW) / 10.0)
    except OverflowError as exc:
        raise PhysicsInputError(f"power_dbm={power_dbm!r} overflows linear watts") from exc
    if watts == 0.0 or not math.isfinite(watts):
        raise PhysicsInputError(f"power_dbm={power_dbm!r} is outside the representable range")
    return watts


def received_power_dbm(
    tx_power_dbm: float,
    tx_gain_dbi: float,
    rx_gain_dbi: float,
    path_loss_db: float,
    cable_loss_db: float = 0.0,
    polarization_loss_db: float = 0.0,
    atmospheric_loss_db: float = 0.0,
    shadowing_db: float = 0.0,
) -> float:
    """``Pr = Pt + Gt + Gr - PL - Lcable - Lpol - Latm - Lshadow`` (dBm)."""
    pr = (
        _validate.finite("tx_power_dbm", tx_power_dbm)
        + _validate.finite("tx_gain_dbi", tx_gain_dbi)
        + _validate.finite("rx_gain_dbi", rx_gain_dbi)
        - _validate.finite("path_loss_db", path_loss_db)
        - _validate.finite("cable_loss_db", cable_loss_db)
        - _validate.finite("polarization_loss_db", polarization_loss_db)
        - _validate.finite("atmospheric_loss_db", atmospheric_loss_db)
        - _validate.finite("shadowing_db", shadowing_db)
    )
    return _validate.finite_result("received power", pr)


def noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float = 0.0) -> float:
    """``N = -174 + 10*log10(bandwidth_hz) + NF`` (dBm)."""
    bw = _validate.positive("bandwidth_hz", bandwidth_hz)
    nf = _validate.finite("noise_figure_db", noise_figure_db)
    return _validate.finite_result(
        "noise floor", THERMAL_NOISE_DBM_PER_HZ + 10.0 * math.log10(bw) + nf
    )


def snr_db(rx_power_dbm: float, noise_floor_dbm_: float) -> float:
    """``SNR = Pr - N`` (dB)."""
    return _validate.finite_result(
        "SNR",
        _validate.finite("rx_power_dbm", rx_power_dbm)
        - _validate.finite("noise_floor_dbm", noise_floor_dbm_),
    )


def link_margin_db(rx_power_dbm: float, sensitivity_dbm: float) -> float:
    """``margin = Pr - sensitivity`` (dB). Positive means the link closes."""
    return _validate.finite_result(
        "link margin",
        _validate.finite("rx_power_dbm", rx_power_dbm)
        - _validate.finite("sensitivity_dbm", sensitivity_dbm),
    )


def eb_n0_db(snr_db_: float, bandwidth_hz: float, bit_rate_hz: float) -> float:
    """``Eb/N0 = SNR + 10*log10(bandwidth_hz / bit_rate_hz)`` (dB).

    Computed as a difference of logarithms so extreme ratios cannot overflow.
    BER curves per modulation are *not* computed here (see ``WaveformCodec``).
    """
    snr = _validate.finite("snr_db", snr_db_)
    bw = _validate.positive("bandwidth_hz", bandwidth_hz)
    rate = _validate.positive("bit_rate_hz", bit_rate_hz)
    return _validate.finite_result("Eb/N0", snr + 10.0 * math.log10(bw) - 10.0 * math.log10(rate))


def compute_link_budget(budget: LinkBudgetInput) -> LinkBudgetResult:
    """Evaluate the full §9 chain for one :class:`LinkBudgetInput`."""
    pr = received_power_dbm(
        budget.tx_power_dbm,
        budget.tx_gain_dbi,
        budget.rx_gain_dbi,
        budget.path_loss_db,
        budget.cable_loss_db,
        budget.polarization_loss_db,
        budget.atmospheric_loss_db,
        budget.shadowing_db,
    )
    noise = noise_floor_dbm(budget.bandwidth_hz, budget.noise_figure_db)
    snr = snr_db(pr, noise)
    margin = link_margin_db(pr, budget.sensitivity_dbm)
    return LinkBudgetResult(
        rx_power_dbm=pr,
        noise_floor_dbm=noise,
        snr_db=snr,
        margin_db=margin,
        quality=link_quality(margin),
    )
