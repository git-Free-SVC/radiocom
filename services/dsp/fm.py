"""Coherent orthogonal binary FSK represented by continuous-phase FM tones."""

from __future__ import annotations

import numpy as np

from ._analytic import ber_coherent_orthogonal, check_ber_model, scaled_bandwidth
from ._single_carrier import SAMPLES_PER_SYMBOL
from ._validation import (
    DSPInputError,
    require_complete_groups,
    validate_bits,
    validate_iq,
    validate_sample_rate,
)


class FMCodec:
    """Binary CPFSK with tones at +/-Rs/2 and a known initial phase of zero."""

    name = "fm"
    samples_per_symbol = SAMPLES_PER_SYMBOL

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        values = validate_bits(bits)
        if values.size == 0:
            return np.empty(0, dtype=np.complex128)
        # Rs=Fs/8, so +/-Rs/2 gives a phase increment of +/-pi/8 per sample.
        increments_per_symbol = np.where(values == 1, np.pi / 8.0, -np.pi / 8.0)
        increments = np.repeat(increments_per_symbol, SAMPLES_PER_SYMBOL)
        phase = np.empty(increments.size, dtype=np.float64)
        phase[0] = 0.0
        if phase.size > 1:
            phase[1:] = np.cumsum(increments[:-1], dtype=np.float64)
        output = np.exp(1j * phase).astype(np.complex128, copy=False)
        if not bool(np.all(np.isfinite(output))):
            raise DSPInputError("sample_rate_hz produced non-finite FSK samples")
        return np.ascontiguousarray(output)

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        samples = validate_iq(iq)
        require_complete_groups(samples, SAMPLES_PER_SYMBOL, "iq")
        if samples.size == 0:
            return np.empty(0, dtype=np.uint8)
        blocks = samples.reshape(-1, SAMPLES_PER_SYMBOL)
        offsets = np.arange(SAMPLES_PER_SYMBOL, dtype=np.float64)
        recovered = np.empty(blocks.shape[0], dtype=np.uint8)
        for index, block in enumerate(blocks):
            # Each 8-sample symbol advances phase by +/-pi, equal modulo 2pi.
            start_phase = np.pi if index % 2 else 0.0
            tone_zero = np.exp(1j * (start_phase - np.pi * offsets / 8.0))
            tone_one = np.exp(1j * (start_phase + np.pi * offsets / 8.0))
            score_zero = float(np.vdot(tone_zero, block).real)
            score_one = float(np.vdot(tone_one, block).real)
            recovered[index] = score_one > score_zero
        return np.ascontiguousarray(recovered)

    def ber(self, ebn0_db: float) -> float:
        return check_ber_model(ber_coherent_orthogonal, ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        # Carson: 2*(peak deviation + modulating frequency) with both = Rs/2.
        return scaled_bandwidth(symbol_rate_hz, 2.0)


FSKCodec = FMCodec
