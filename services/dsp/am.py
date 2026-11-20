"""Binary AM/ASK implemented as on-off keying (OOK)."""

from __future__ import annotations

import numpy as np

from ._analytic import ber_coherent_orthogonal, check_ber_model, scaled_bandwidth
from ._single_carrier import SAMPLES_PER_SYMBOL, collapse_symbols, expand_symbols
from ._validation import validate_bits, validate_sample_rate


class AMCodec:
    """Coherent OOK with equal prior bits and a 0.5 noiseless threshold."""

    name = "am"
    samples_per_symbol = SAMPLES_PER_SYMBOL

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        return expand_symbols(validate_bits(bits).astype(np.float64))

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        symbols = collapse_symbols(iq)
        return np.ascontiguousarray((symbols.real > 0.5).astype(np.uint8))

    def ber(self, ebn0_db: float) -> float:
        return check_ber_model(ber_coherent_orthogonal, ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        return scaled_bandwidth(symbol_rate_hz, 2.0)


OOKCodec = AMCodec
