"""Shared validation for the public DSP API."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import numpy as np


class DSPInputError(ValueError):
    """Raised when a codec input violates its documented numeric contract."""


def finite_real(value: Any, name: str, *, positive: bool = False) -> float:
    """Return a finite Python float, with a parameter-specific error."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise DSPInputError(f"{name} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise DSPInputError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise DSPInputError(f"{name} must be greater than zero")
    return result


def validate_bits(bits: Any) -> np.ndarray:
    """Return a fresh, contiguous uint8 vector containing only 0 and 1."""
    try:
        values = np.asarray(bits)
    except Exception as exc:
        raise DSPInputError("bits must be a one-dimensional numeric array") from exc
    if values.ndim != 1:
        raise DSPInputError("bits must be one-dimensional")
    if values.dtype.kind in "biu":
        valid = np.logical_or(values == 0, values == 1)
    elif values.dtype.kind == "f":
        if not np.all(np.isfinite(values)):
            raise DSPInputError("bits must contain only finite 0/1 values")
        valid = np.logical_or(values == 0.0, values == 1.0)
    else:
        raise DSPInputError("bits must use boolean, integer, or floating dtype")
    if not bool(np.all(valid)):
        raise DSPInputError("bits must contain only 0 or 1")
    return np.ascontiguousarray(values, dtype=np.uint8)


def validate_iq(iq: Any) -> np.ndarray:
    """Return a fresh contiguous complex128 vector after checking all samples."""
    try:
        values = np.asarray(iq)
    except Exception as exc:
        raise DSPInputError("iq must be a one-dimensional numeric array") from exc
    if values.ndim != 1:
        raise DSPInputError("iq must be one-dimensional")
    if values.dtype.kind not in "biufc":
        raise DSPInputError("iq must use a real or complex numeric dtype")
    if not bool(np.all(np.isfinite(values))):
        raise DSPInputError("iq must contain only finite samples")
    try:
        result = np.ascontiguousarray(values, dtype=np.complex128)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DSPInputError("iq samples cannot be represented as complex128") from exc
    if not bool(np.all(np.isfinite(result))):
        raise DSPInputError("iq samples must remain finite as complex128")
    return result


def validate_sample_rate(sample_rate_hz: Any) -> float:
    return finite_real(sample_rate_hz, "sample_rate_hz", positive=True)


def validate_symbol_rate(symbol_rate_hz: Any) -> float:
    return finite_real(symbol_rate_hz, "symbol_rate_hz", positive=True)


def require_complete_groups(values: np.ndarray, group_size: int, name: str) -> None:
    if values.size % group_size:
        raise DSPInputError(f"{name} length {values.size} is not a multiple of {group_size}")
