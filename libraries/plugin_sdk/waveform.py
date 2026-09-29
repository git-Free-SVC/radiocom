"""WaveformCodec interface. Frozen after Wave 0 — see docs/adr/ADR-000.
Implementations: services/dsp/{am,fm,bpsk,qpsk,ofdm,...}.py and the
GNU Radio adapter in integrations/gnu-radio (§10)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class WaveformCodec(Protocol):
    """One modulation scheme. Two fidelity modes share this interface:
    analytical (ber() curve, no modulate/demodulate needed) and sample-level
    (modulate/demodulate real IQ, used for validation and SDR-like views)."""

    name: str  # e.g. "bpsk", "nbfm"

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        """bits (0/1 array) -> complex baseband IQ samples.
        Sample-level mode only; analytical-only codecs may raise NotImplementedError.
        """
        ...

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        """complex baseband IQ samples -> recovered bits (0/1 array)."""
        ...

    def ber(self, ebn0_db: float) -> float:
        """Theoretical/analytical bit error rate at a given Eb/N0. Always
        implemented — this is what the RF Core uses by default (§9/§10)."""
        ...

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        """Occupied bandwidth for a given symbol rate (e.g. Carson's rule
        for FM, (1+rolloff)*Rs for linear digital modulations)."""
        ...
