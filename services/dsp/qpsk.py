"""Gray-coded QPSK codec with two bits per symbol and eight samples per symbol."""

from __future__ import annotations

import numpy as np

from ._analytic import ber_bpsk, check_ber_model, scaled_bandwidth
from ._single_carrier import SAMPLES_PER_SYMBOL, collapse_symbols, expand_symbols
from ._validation import DSPInputError, validate_bits, validate_sample_rate

_INV_SQRT_2 = 1.0 / np.sqrt(2.0)


def _bits_to_symbols(bits: np.ndarray) -> np.ndarray:
    if bits.size % 2:
        raise DSPInputError("QPSK bits length must be even")
    pairs = bits.reshape(-1, 2)
    i = np.where(pairs[:, 0] == 1, 1.0, -1.0)
    q = np.where(pairs[:, 1] == 1, 1.0, -1.0)
    return (i + 1j * q) * _INV_SQRT_2


class QPSKCodec:
    name = "qpsk"
    samples_per_symbol = SAMPLES_PER_SYMBOL

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        return expand_symbols(_bits_to_symbols(validate_bits(bits)))

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        symbols = collapse_symbols(iq)
        recovered = np.empty((symbols.size, 2), dtype=np.uint8)
        recovered[:, 0] = symbols.real > 0.0
        recovered[:, 1] = symbols.imag > 0.0
        return np.ascontiguousarray(recovered.reshape(-1))

    def ber(self, ebn0_db: float) -> float:
        return check_ber_model(ber_bpsk, ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        return scaled_bandwidth(symbol_rate_hz, 2.0)
