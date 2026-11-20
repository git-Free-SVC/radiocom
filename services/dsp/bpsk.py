"""BPSK codec: antipodal symbols with eight rectangular samples per symbol."""

from __future__ import annotations

import numpy as np

from ._analytic import ber_bpsk, check_ber_model, scaled_bandwidth
from ._single_carrier import SAMPLES_PER_SYMBOL, collapse_symbols, expand_symbols
from ._validation import validate_bits, validate_sample_rate


class BPSKCodec:
    name = "bpsk"
    samples_per_symbol = SAMPLES_PER_SYMBOL

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        values = validate_bits(bits)
        symbols = np.where(values == 1, 1.0, -1.0)
        return expand_symbols(symbols)

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        symbols = collapse_symbols(iq)
        return np.ascontiguousarray((symbols.real > 0.0).astype(np.uint8))

    def ber(self, ebn0_db: float) -> float:
        return check_ber_model(ber_bpsk, ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        return scaled_bandwidth(symbol_rate_hz, 2.0)
