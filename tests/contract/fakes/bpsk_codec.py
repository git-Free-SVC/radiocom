"""Reference WaveformCodec: BPSK, 1 sample/symbol, theoretical BER."""

from __future__ import annotations

import math

import numpy as np


class BpskCodec:
    name = "bpsk"
    rolloff = 0.35

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        return (2.0 * np.asarray(bits, dtype=float) - 1.0).astype(np.complex128)

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        return (np.real(iq) > 0).astype(np.uint8)

    def ber(self, ebn0_db: float) -> float:
        return 0.5 * math.erfc(math.sqrt(10 ** (ebn0_db / 10)))

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        return (1 + self.rolloff) * symbol_rate_hz
