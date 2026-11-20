"""Shared rectangular-pulse helpers for single-carrier codecs."""

from __future__ import annotations

import numpy as np

from ._validation import require_complete_groups, validate_iq

SAMPLES_PER_SYMBOL = 8


def expand_symbols(symbols: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(
        np.repeat(np.asarray(symbols, dtype=np.complex128), SAMPLES_PER_SYMBOL),
        dtype=np.complex128,
    )


def collapse_symbols(iq: np.ndarray) -> np.ndarray:
    samples = validate_iq(iq)
    require_complete_groups(samples, SAMPLES_PER_SYMBOL, "iq")
    if samples.size == 0:
        return np.empty(0, dtype=np.complex128)
    return samples.reshape(-1, SAMPLES_PER_SYMBOL).mean(axis=1)
