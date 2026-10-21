"""Reusable dB arithmetic for RF link budgets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from libraries.domain.rf_results import LinkBudgetInput, LinkQuality

from .errors import PhysicsInputError

NOISE_DENSITY_DBM_HZ = -174.0
MARGINAL_MARGIN_DB = 0.0
UP_MARGIN_DB = 10.0


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}") from exc
    if not math.isfinite(number):
        raise PhysicsInputError(f"{name} must be finite; got {value!r}")
    return number


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise PhysicsInputError(f"{name} must be > 0; got {number!r}")
    return number


def _finite_result(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise PhysicsInputError(f"{name} result must be finite; got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class LinkBudgetResult:
    """Computed powers and ratios for one link-budget input."""

    received_power_dbm: float
    noise_floor_dbm: float
    snr_db: float
    margin_db: float
    eb_n0_db: float


def dbm_from_watts(power_watt: float) -> float:
    """Convert strictly positive power in watts to dBm."""
    power = _positive("power_watt", power_watt)
    return _finite_result("dbm_from_watts", 10.0 * math.log10(power) + 30.0)


def watts_from_dbm(power_dbm: float) -> float:
    """Convert dBm to watts, rejecting overflow and underflow to zero."""
    dbm = _finite("power_dbm", power_dbm)
    exponent = (dbm - 30.0) / 10.0
    try:
        watts = 10.0**exponent
    except OverflowError as exc:
        raise PhysicsInputError(
            f"power_dbm is too large to convert to finite watts; got {dbm!r}"
        ) from exc
    if not math.isfinite(watts) or watts == 0.0:
        raise PhysicsInputError(f"power_dbm is outside the representable watt range; got {dbm!r}")
    return watts


def received_power_dbm(budget: LinkBudgetInput) -> float:
    """Compute Pr = Pt + Gt + Gr - path and other link losses."""
    if not isinstance(budget, LinkBudgetInput):
        raise PhysicsInputError(f"budget must be LinkBudgetInput; got {type(budget).__name__}")
    tx_power = _finite("tx_power_dbm", budget.tx_power_dbm)
    tx_gain = _finite("tx_gain_dbi", budget.tx_gain_dbi)
    rx_gain = _finite("rx_gain_dbi", budget.rx_gain_dbi)
    path_loss = _finite("path_loss_db", budget.path_loss_db)
    cable_loss = _finite("cable_loss_db", budget.cable_loss_db)
    polarization_loss = _finite("polarization_loss_db", budget.polarization_loss_db)
    atmospheric_loss = _finite("atmospheric_loss_db", budget.atmospheric_loss_db)
    shadowing = _finite("shadowing_db", budget.shadowing_db)
    try:
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
    except OverflowError as exc:
        raise PhysicsInputError("received power result overflowed") from exc
    return _finite_result("received_power_dbm", result)


def noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float = 0.0) -> float:
    """Return thermal noise plus receiver noise figure in dBm."""
    bandwidth = _positive("bandwidth_hz", bandwidth_hz)
    noise_figure = _finite("noise_figure_db", noise_figure_db)
    result = NOISE_DENSITY_DBM_HZ + 10.0 * math.log10(bandwidth) + noise_figure
    return _finite_result("noise_floor_dbm", result)


def snr_db(received_power_dbm_value: float, noise_floor_dbm_value: float) -> float:
    """Return received power minus noise floor, in dB."""
    received = _finite("received_power_dbm", received_power_dbm_value)
    noise = _finite("noise_floor_dbm", noise_floor_dbm_value)
    return _finite_result("snr_db", received - noise)


def link_margin_db(received_power_dbm_value: float, sensitivity_dbm: float) -> float:
    """Return received power minus receiver sensitivity, in dB."""
    received = _finite("received_power_dbm", received_power_dbm_value)
    sensitivity = _finite("sensitivity_dbm", sensitivity_dbm)
    return _finite_result("link_margin_db", received - sensitivity)


def eb_n0_db(snr: float, bandwidth_hz: float, bit_rate_hz: float) -> float:
    """Return Eb/N0 using SNR + 10 log10(bandwidth / bit rate)."""
    snr_value = _finite("snr_db", snr)
    bandwidth = _positive("bandwidth_hz", bandwidth_hz)
    bit_rate = _positive("bit_rate_hz", bit_rate_hz)
    result = snr_value + 10.0 * (math.log10(bandwidth) - math.log10(bit_rate))
    return _finite_result("eb_n0_db", result)


def calculate_link_budget(
    budget: LinkBudgetInput, bit_rate_hz: float | None = None
) -> LinkBudgetResult:
    """Compute Pr, noise, SNR, margin and Eb/N0 from the frozen input type.

    If no bit rate is supplied, it defaults to the input bandwidth, making
    Eb/N0 equal to SNR.
    """
    if not isinstance(budget, LinkBudgetInput):
        raise PhysicsInputError(f"budget must be LinkBudgetInput; got {type(budget).__name__}")
    bandwidth = _positive("bandwidth_hz", budget.bandwidth_hz)
    received = received_power_dbm(budget)
    noise = noise_floor_dbm(bandwidth, budget.noise_figure_db)
    snr = snr_db(received, noise)
    margin = link_margin_db(received, budget.sensitivity_dbm)
    rate = bandwidth if bit_rate_hz is None else bit_rate_hz
    ebn0 = eb_n0_db(snr, bandwidth, rate)
    return LinkBudgetResult(received, noise, snr, margin, ebn0)


def link_quality(margin_db: float) -> LinkQuality:
    """Classify margin: UP at 10 dB, MARGINAL from 0 to under 10 dB, else DOWN.

    These MVP thresholds are explicit engineering conventions; the frozen
    interfaces do not define them yet.
    """
    margin = _finite("margin_db", margin_db)
    if margin >= UP_MARGIN_DB:
        return LinkQuality.UP
    if margin >= MARGINAL_MARGIN_DB:
        return LinkQuality.MARGINAL
    return LinkQuality.DOWN
