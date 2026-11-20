from __future__ import annotations

import math
import random
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from services.dsp import AMCodec, BPSKCodec, FMCodec, OFDMCodec, QPSKCodec
from services.dsp._validation import DSPInputError
from services.dsp.ofdm import ACTIVE_BIN_INDICES, BITS_PER_FRAME, SAMPLES_PER_FRAME

CODECS = [BPSKCodec, QPSKCodec, AMCodec, FMCodec, OFDMCodec]
FS = 1_000_000.0


@pytest.mark.parametrize("codec_type", CODECS)
def test_public_codec_shape_and_output_dtypes(codec_type):
    codec = codec_type()
    bits = np.array([0, 1] * (16 if codec_type is OFDMCodec else 8), dtype=np.uint8)
    iq = codec.modulate(bits, FS)
    recovered = codec.demodulate(iq, FS)
    assert iq.dtype == np.complex128
    assert iq.flags.c_contiguous
    assert recovered.dtype == np.uint8
    assert recovered.flags.c_contiguous
    np.testing.assert_array_equal(recovered, bits)
    assert isinstance(codec.name, str) and codec.name


def test_bpsk_and_qpsk_fixed_constellation_vectors():
    bpsk = BPSKCodec().modulate(np.array([0, 1], dtype=np.uint8), FS)
    np.testing.assert_allclose(bpsk[:8], np.full(8, -1 + 0j), atol=0, rtol=0)
    np.testing.assert_allclose(bpsk[8:], np.full(8, 1 + 0j), atol=0, rtol=0)
    qpsk = QPSKCodec().modulate(np.array([0, 0, 0, 1, 1, 1, 1, 0], dtype=np.uint8), FS)
    expected = np.array([-1 - 1j, -1 + 1j, 1 + 1j, 1 - 1j]) / math.sqrt(2)
    np.testing.assert_allclose(qpsk.reshape(-1, 8)[:, 0], expected, atol=1e-15, rtol=0)


def test_ook_fixed_levels_and_threshold():
    codec = AMCodec()
    iq = codec.modulate(np.array([0, 1], dtype=np.uint8), FS)
    np.testing.assert_array_equal(iq[:8], np.zeros(8, dtype=np.complex128))
    np.testing.assert_array_equal(iq[8:], np.ones(8, dtype=np.complex128))
    np.testing.assert_array_equal(codec.demodulate(iq, FS), np.array([0, 1], np.uint8))


def test_fsk_has_continuous_phase_and_recovers_transitions():
    codec = FMCodec()
    bits = np.array([0, 1, 1, 0, 1, 0, 0, 1], dtype=np.uint8)
    iq = codec.modulate(bits, FS)
    np.testing.assert_array_equal(codec.demodulate(iq, FS), bits)
    phase_steps = np.angle(iq[1:] * np.conjugate(iq[:-1]))
    expected = np.repeat(np.where(bits == 1, np.pi / 8, -np.pi / 8), 8)[:-1]
    np.testing.assert_allclose(phase_steps, expected, atol=1e-14, rtol=0)


def test_ofdm_bins_frame_and_contract_payload():
    codec = OFDMCodec()
    assert tuple(ACTIVE_BIN_INDICES.tolist()) == tuple(range(56, 64)) + tuple(range(1, 9))
    bits = np.random.default_rng(0).integers(0, 2, 256, dtype=np.uint8)
    iq = codec.modulate(bits, FS)
    assert iq.size == 8 * SAMPLES_PER_FRAME
    assert codec.demodulate(iq, FS).size == bits.size
    np.testing.assert_array_equal(codec.demodulate(iq, FS), bits)
    with pytest.raises(DSPInputError, match="multiple of 32"):
        codec.modulate(bits[:-1], FS)
    with pytest.raises(DSPInputError, match="multiple of 80"):
        codec.demodulate(iq[:-1], FS)


def test_ofdm_active_carriers_are_orthogonal_and_guards_are_zero():
    codec = OFDMCodec()
    bits = np.array([1, 1] * 16, dtype=np.uint8)
    frame = codec.modulate(bits, FS)[:SAMPLES_PER_FRAME]
    useful = frame[codec.cyclic_prefix_samples :]
    spectrum = np.fft.fft(useful) / np.sqrt(codec.fft_size)
    inactive = np.ones(codec.fft_size, dtype=bool)
    inactive[ACTIVE_BIN_INDICES] = False
    np.testing.assert_allclose(
        spectrum[ACTIVE_BIN_INDICES], np.full(16, (1 + 1j) / math.sqrt(2)), atol=1e-14, rtol=0
    )
    np.testing.assert_allclose(
        spectrum[inactive], np.zeros(np.count_nonzero(inactive)), atol=1e-14, rtol=0
    )


def test_regression_ofdm_qpsk_bits_preserve_frame_axis():
    """Regression: flattening QPSK symbols assigned one value to 16 active bins."""
    codec = OFDMCodec()
    bits = np.random.default_rng(19).integers(0, 2, BITS_PER_FRAME * 3, dtype=np.uint8)
    iq = codec.modulate(bits, FS)
    assert iq.size == 3 * SAMPLES_PER_FRAME
    np.testing.assert_array_equal(codec.demodulate(iq, FS), bits)


def test_ber_golden_values_are_independent_anchors():
    bpsk = BPSKCodec()
    assert bpsk.ber(0.0) == pytest.approx(0.07864960352514257, abs=1e-15)
    assert bpsk.ber(10.0) == pytest.approx(3.872108215522035e-6, abs=1e-17)
    assert QPSKCodec().ber(0.0) == pytest.approx(0.07864960352514257, abs=1e-15)
    assert AMCodec().ber(0.0) == pytest.approx(0.15865525393145707, abs=1e-15)
    assert FMCodec().ber(0.0) == pytest.approx(0.15865525393145707, abs=1e-15)
    assert OFDMCodec().ber(0.0) == pytest.approx(0.07864960352514257, abs=1e-15)


def test_30_independent_ber_golden_points_across_all_five_codecs():
    # Values were generated in a separate stdlib-only calculation from
    # Q(x)=erfc(x/sqrt(2))/2, not by calling any production codec helper.
    bpsk_points = {
        -5.0: 0.21322801835762037,
        0.0: 0.078649603525142553,
        5.0: 0.0059538671477786615,
        10.0: 3.8721082155220378e-6,
        15.0: 9.1239573626280891e-16,
        30.0: 0.0,
    }
    orthogonal_points = {
        -5.0: 0.28694174372604853,
        0.0: 0.15865525393145702,
        5.0: 0.037678988147463385,
        10.0: 0.00078270112900127441,
        15.0: 9.3610399906851007e-9,
        30.0: 8.979163924003194e-220,
    }
    for codec_type in (BPSKCodec, QPSKCodec, OFDMCodec):
        for db, expected in bpsk_points.items():
            assert codec_type().ber(db) == pytest.approx(expected, rel=2e-13, abs=0.0)
    for codec_type in (AMCodec, FMCodec):
        for db, expected in orthogonal_points.items():
            assert codec_type().ber(db) == pytest.approx(expected, rel=2e-13, abs=0.0)


@pytest.mark.parametrize(
    "codec_type,scale",
    [
        (BPSKCodec, 2.0),
        (QPSKCodec, 2.0),
        (AMCodec, 2.0),
        (FMCodec, 2.0),
        (OFDMCodec, 16.0),
    ],
)
def test_bandwidth_formula_and_scaling(codec_type, scale):
    codec = codec_type()
    assert codec.occupied_bandwidth_hz(1_000.0) == pytest.approx(1_000.0 * scale)
    assert codec.occupied_bandwidth_hz(100_000_000.0) == pytest.approx(100_000_000.0 * scale)


@pytest.mark.parametrize("codec_type", CODECS)
def test_empty_payloads_and_determinism(codec_type):
    codec = codec_type()
    empty_bits = np.empty(0, dtype=np.uint8)
    empty_iq = codec.modulate(empty_bits, FS)
    assert empty_iq.size == 0 and empty_iq.dtype == np.complex128
    assert codec.demodulate(empty_iq, FS).size == 0
    payload = np.tile(np.array([0, 1], dtype=np.uint8), 16)
    if codec_type is OFDMCodec:
        payload = np.resize(payload, BITS_PER_FRAME * 2)
    first = codec.modulate(payload, FS)
    for _ in range(1000):
        again = codec.modulate(payload, FS)
        np.testing.assert_array_equal(again, first)


@pytest.mark.parametrize("codec_type", CODECS)
def test_seeded_roundtrip_stress_10000_bits_or_frames(codec_type):
    rng = np.random.default_rng(1234)
    codec = codec_type()
    if codec_type is OFDMCodec:
        bits = rng.integers(0, 2, BITS_PER_FRAME * 10_000, dtype=np.uint8)
    else:
        count = 10_000 if codec_type is not QPSKCodec else 10_000  # noqa: RUF034
        bits = rng.integers(0, 2, count, dtype=np.uint8)
        if codec_type is QPSKCodec and bits.size % 2:
            bits = np.append(bits, np.uint8(0))
    iq = codec.modulate(bits, FS)
    np.testing.assert_array_equal(codec.demodulate(iq, FS), bits)


@pytest.mark.parametrize("codec_type", CODECS)
def test_10000_seeded_monotonicity_and_bandwidth_properties(codec_type):
    codec = codec_type()
    rng = random.Random(1234)
    for _ in range(10_000):
        lower = rng.uniform(-100.0, 100.0)
        upper = lower + rng.random() * 100.0
        assert codec.ber(upper) <= codec.ber(lower) + 1e-15
        rate = 10.0 ** rng.uniform(0.0, 8.0)
        first = codec.occupied_bandwidth_hz(rate)
        second = codec.occupied_bandwidth_hz(rate * 2.0)
        assert second == pytest.approx(2.0 * first, rel=1e-14)


def test_50000_point_numeric_sweep_all_codec_models():
    codecs = [codec_type() for codec_type in CODECS]
    for i in range(50_000):
        codec = codecs[i % len(codecs)]
        ebn0 = -100.0 + (i % 20_001) * 0.01
        rate = 1.0 + ((i * 7919) % 100_000_000)
        ber = codec.ber(ebn0)
        bandwidth = codec.occupied_bandwidth_hz(float(rate))
        assert math.isfinite(ber) and 0.0 <= ber <= 0.5
        assert math.isfinite(bandwidth) and bandwidth > 0.0


@pytest.mark.parametrize("codec_type", CODECS)
def test_hostile_scalar_inputs(codec_type):
    codec = codec_type()
    for value in (0.0, -1.0, float("nan"), float("inf"), -float("inf")):
        with pytest.raises(DSPInputError, match="sample_rate_hz"):
            codec.modulate(np.array([0, 1], dtype=np.uint8), value)
    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(DSPInputError, match="ebn0_db"):
            codec.ber(value)
    assert codec.ber(1e300) == pytest.approx(0.0, abs=0.0)
    assert codec.ber(-1e300) == pytest.approx(0.5, abs=0.0)


@pytest.mark.parametrize("codec_type", CODECS)
def test_extreme_positive_finite_sample_rates_do_not_create_nonfinite_iq(codec_type):
    codec = codec_type()
    bits = np.array([0, 1] * (16 if codec_type is OFDMCodec else 4), dtype=np.uint8)
    for rate in (1e-300, float.fromhex("0x0.0000000000001p-1022"), 1e18, 1e300):
        iq = codec.modulate(bits, rate)
        assert np.all(np.isfinite(iq))
        np.testing.assert_array_equal(codec.demodulate(iq, rate), bits)


@pytest.mark.parametrize("codec_type", CODECS)
def test_hostile_bits_iq_and_frame_boundaries(codec_type):
    codec = codec_type()
    invalid_bits = [
        np.array(1),
        np.ones((2, 2)),
        np.array([0, 2]),
        np.array([0.5]),
        np.array([np.nan]),
        np.array([1 + 0j]),
    ]
    for bits in invalid_bits:
        with pytest.raises(DSPInputError):
            codec.modulate(bits, FS)
    with pytest.raises(DSPInputError, match="one-dimensional"):
        codec.demodulate(np.ones((2, 2), dtype=np.complex128), FS)
    with pytest.raises(DSPInputError, match="finite"):
        codec.demodulate(np.array([complex(float("nan"), 0)]), FS)
    if codec_type is QPSKCodec:
        with pytest.raises(DSPInputError, match="even"):
            codec.modulate(np.array([1], dtype=np.uint8), FS)
    if codec_type is OFDMCodec:
        with pytest.raises(DSPInputError, match="multiple of 32"):
            codec.modulate(np.ones(31, dtype=np.uint8), FS)
    else:
        with pytest.raises(DSPInputError, match="multiple of 8"):
            codec.demodulate(np.ones(1, dtype=np.complex128), FS)


def test_bandwidth_overflow_is_reported_not_returned_as_infinity():
    with pytest.raises(DSPInputError, match="non-finite bandwidth"):
        OFDMCodec().occupied_bandwidth_hz(1.7e308)


def test_concurrent_shared_codec_calls_are_identical_and_do_not_mutate_inputs():
    codec = OFDMCodec()
    bits = np.random.default_rng(7).integers(0, 2, BITS_PER_FRAME * 8, dtype=np.uint8)
    before = bits.copy()
    serial = codec.modulate(bits, FS)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: codec.modulate(bits, FS), range(32)))
    for result in results:
        np.testing.assert_array_equal(result, serial)
    np.testing.assert_array_equal(bits, before)


def _wilson_interval(errors: int, trials: int, z: float = 4.0) -> tuple[float, float]:
    phat = errors / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (phat + z2 / (2.0 * trials)) / denominator
    radius = (
        z * math.sqrt(phat * (1.0 - phat) / trials + z2 / (4.0 * trials * trials)) / denominator
    )
    return center - radius, center + radius


@pytest.mark.parametrize("codec_type,eb_per_bit", [(BPSKCodec, 8.0), (QPSKCodec, 4.0)])
def test_seeded_awgn_ber_matches_analytic_model_inside_wilson_interval(codec_type, eb_per_bit):
    codec = codec_type()
    rng = np.random.default_rng(1234)
    bits = rng.integers(0, 2, 30_000, dtype=np.uint8)
    if codec_type is QPSKCodec:
        bits = bits[: bits.size - bits.size % 2]
    iq = codec.modulate(bits, FS)
    ebn0_db = 0.0
    gamma = 10.0 ** (ebn0_db / 10.0)
    n0 = eb_per_bit / gamma
    sigma = math.sqrt(n0 / 2.0)
    noise = rng.normal(0.0, sigma, iq.size) + 1j * rng.normal(0.0, sigma, iq.size)
    recovered = codec.demodulate(iq + noise, FS)
    errors = int(np.count_nonzero(recovered != bits))
    interval = _wilson_interval(errors, bits.size)
    expected = 0.5 * math.erfc(math.sqrt(gamma))
    assert interval[0] <= expected <= interval[1]


def test_100000_symbol_and_200000_analytic_call_performance_budget():
    codec = BPSKCodec()
    bits = np.random.default_rng(10).integers(0, 2, 100_000, dtype=np.uint8)
    started = time.perf_counter()
    iq = codec.modulate(bits, FS)
    recovered = codec.demodulate(iq, FS)
    for index in range(100_000):
        codec.ber((index % 31) - 5.0)
        codec.occupied_bandwidth_hz(float(index + 1))
    elapsed = time.perf_counter() - started
    np.testing.assert_array_equal(recovered, bits)
    assert elapsed < 5.0
