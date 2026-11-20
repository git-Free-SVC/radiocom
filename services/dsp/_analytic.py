"""Numerically stable scalar BER and bandwidth helpers."""

from __future__ import annotations

import math
from typing import Callable

from ._validation import DSPInputError, finite_real, validate_symbol_rate


def _gamma_from_db(ebn0_db: float) -> float:
    db = finite_real(ebn0_db, "ebn0_db")
    exponent = db / 10.0
    # The BER has already rounded to 0 or 0.5 long before these limits.
    if exponent > 300.0:
        return math.inf
    if exponent < -300.0:
        return 0.0
    try:
        return 10.0**exponent
    except OverflowError:
        return math.inf


def ber_bpsk(ebn0_db: float) -> float:
    gamma = _gamma_from_db(ebn0_db)
    return 0.5 * math.erfc(math.sqrt(gamma))


def ber_coherent_orthogonal(ebn0_db: float) -> float:
    gamma = _gamma_from_db(ebn0_db)
    return 0.5 * math.erfc(math.sqrt(gamma / 2.0))


def scaled_bandwidth(symbol_rate_hz: float, scale: float) -> float:
    rate = validate_symbol_rate(symbol_rate_hz)
    result = rate * scale
    if not math.isfinite(result) or result <= 0.0:
        raise DSPInputError("symbol_rate_hz produces a non-finite bandwidth")
    return result


def check_ber_model(model: Callable[[float], float], ebn0_db: float) -> float:
    """Guard the shared BER contract even if a model is changed later."""
    result = model(ebn0_db)
    if not math.isfinite(result) or not 0.0 <= result <= 0.5:
        raise DSPInputError("ebn0_db produced an invalid BER")
    return result
