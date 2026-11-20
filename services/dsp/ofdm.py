"""Small fixed-frame OFDM codec: 64-point transform, 16 active QPSK bins."""

from __future__ import annotations

import numpy as np

from ._analytic import ber_bpsk, check_ber_model, scaled_bandwidth
from ._validation import (
    DSPInputError,
    require_complete_groups,
    validate_bits,
    validate_iq,
    validate_sample_rate,
)

FFT_SIZE = 64
CYCLIC_PREFIX_SAMPLES = 16
ACTIVE_BIN_LABELS = tuple(range(-8, 0)) + tuple(range(1, 9))
ACTIVE_BIN_INDICES = np.asarray([k % FFT_SIZE for k in ACTIVE_BIN_LABELS], dtype=np.intp)
BITS_PER_FRAME = len(ACTIVE_BIN_LABELS) * 2
SAMPLES_PER_FRAME = FFT_SIZE + CYCLIC_PREFIX_SAMPLES
_INV_SQRT_2 = 1.0 / np.sqrt(2.0)


def _bits_to_qpsk(bits: np.ndarray) -> np.ndarray:
    pairs = bits.reshape(-1, 2)
    i = np.where(pairs[:, 0] == 1, 1.0, -1.0)
    q = np.where(pairs[:, 1] == 1, 1.0, -1.0)
    return (i + 1j * q) * _INV_SQRT_2


class OFDMCodec:
    """OFDM with fixed active bins -8..-1,+1..+8 and no pilots or coding."""

    name = "ofdm"
    fft_size = FFT_SIZE
    cyclic_prefix_samples = CYCLIC_PREFIX_SAMPLES
    active_bin_labels = ACTIVE_BIN_LABELS
    bits_per_frame = BITS_PER_FRAME
    samples_per_frame = SAMPLES_PER_FRAME

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        values = validate_bits(bits)
        if values.size == 0:
            return np.empty(0, dtype=np.complex128)
        if values.size % BITS_PER_FRAME:
            raise DSPInputError(f"OFDM bits length must be a multiple of {BITS_PER_FRAME}")
        data = _bits_to_qpsk(values).reshape(-1, len(ACTIVE_BIN_LABELS))
        spectra = np.zeros((data.shape[0], FFT_SIZE), dtype=np.complex128)
        spectra[:, ACTIVE_BIN_INDICES] = data
        useful = np.fft.ifft(spectra, axis=1) * np.sqrt(FFT_SIZE)
        framed = np.concatenate((useful[:, -CYCLIC_PREFIX_SAMPLES:], useful), axis=1)
        return np.ascontiguousarray(framed.reshape(-1), dtype=np.complex128)

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        validate_sample_rate(sample_rate_hz)
        samples = validate_iq(iq)
        require_complete_groups(samples, SAMPLES_PER_FRAME, "iq")
        if samples.size == 0:
            return np.empty(0, dtype=np.uint8)
        frames = samples.reshape(-1, SAMPLES_PER_FRAME)
        useful = frames[:, CYCLIC_PREFIX_SAMPLES:]
        spectra = np.fft.fft(useful, axis=1) / np.sqrt(FFT_SIZE)
        carriers = spectra[:, ACTIVE_BIN_INDICES]
        bits = np.empty((frames.shape[0], BITS_PER_FRAME), dtype=np.uint8)
        bits[:, 0::2] = carriers.real > 0.0
        bits[:, 1::2] = carriers.imag > 0.0
        return np.ascontiguousarray(bits.reshape(-1))

    def ber(self, ebn0_db: float) -> float:
        # Ideal QPSK carriers, perfect timing/frequency synchronization, no ICI.
        return check_ber_model(ber_bpsk, ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        # For OFDM this API argument means subcarrier spacing Delta-f.
        return scaled_bandwidth(symbol_rate_hz, float(len(ACTIVE_BIN_LABELS)))
