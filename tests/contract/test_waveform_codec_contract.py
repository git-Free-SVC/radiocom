"""Contract for any WaveformCodec.

    pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=pkg.mod:Class
"""

from __future__ import annotations

import numpy as np
import pytest

from libraries.plugin_sdk.waveform import WaveformCodec

FS = 1e6


def test_conforms_to_protocol(codec):
    assert isinstance(codec, WaveformCodec)
    assert isinstance(codec.name, str) and codec.name


def test_ber_is_probability(codec):
    for e in (-5, 0, 5, 10, 15):
        assert 0.0 <= codec.ber(e) <= 0.5 + 1e-12


def test_ber_non_increasing_with_ebn0(codec):
    vals = [codec.ber(e) for e in range(-5, 21)]
    assert all(b <= a + 1e-15 for a, b in zip(vals, vals[1:]))


def test_occupied_bandwidth_positive_and_monotonic(codec):
    bws = [codec.occupied_bandwidth_hz(r) for r in (1e3, 1e4, 1e5)]
    assert all(b > 0 for b in bws) and bws == sorted(bws)


def test_noiseless_roundtrip(codec):
    bits = np.random.default_rng(0).integers(0, 2, 256).astype(np.uint8)
    try:
        iq = codec.modulate(bits, FS)
    except NotImplementedError:
        pytest.skip("analytical-only codec")
    assert np.iscomplexobj(iq)
    out = np.asarray(codec.demodulate(iq, FS))[: len(bits)]
    assert np.array_equal(out, bits)
