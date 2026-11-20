from __future__ import annotations

import json

import numpy as np
import pytest

from integrations.gnu_radio.codec_adapter import GnuRadioCodecAdapter
from integrations.gnu_radio.errors import (
    WorkerExecutionError,
    WorkerProtocolError,
    WorkerTimeoutError,
)
from integrations.gnu_radio.protocol import (
    FrameError,
    RemoteWorkerError,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from integrations.gnu_radio.worker import _malformed_request_response, process_request
from services.dsp import BPSKCodec


class FakeTransport:
    def __init__(self, codec=None):
        self.codec = codec or BPSKCodec()
        self.started = 0
        self.closed = 0
        self.bad_version = False
        self.fail = False

    def start(self):
        self.started += 1

    def exchange(self, frames):
        request = decode_request(frames)
        if self.fail:
            return encode_response(request, error=RuntimeError("fake backend failure"))
        result = process_request(self.codec, request)
        if self.bad_version:
            metadata = json.loads(result[0].decode())
            metadata["version"] = 99
            result = (json.dumps(metadata).encode(), result[1])
        return result

    def close(self):
        self.closed += 1


def test_adapter_uses_worker_for_iq_and_reference_for_analytics():
    reference = BPSKCodec()
    transport = FakeTransport(reference)
    adapter = GnuRadioCodecAdapter(reference, transport)
    bits = np.array([0, 1, 1, 0], dtype=np.uint8)
    iq = adapter.modulate(bits, 1_000_000.0)
    recovered = adapter.demodulate(iq, 1_000_000.0)
    np.testing.assert_array_equal(recovered, bits)
    assert iq.dtype == np.complex128
    assert adapter.ber(5.0) == pytest.approx(reference.ber(5.0))
    assert adapter.occupied_bandwidth_hz(10_000.0) == pytest.approx(
        reference.occupied_bandwidth_hz(10_000.0)
    )
    assert transport.started == 2
    adapter.close()
    adapter.close()
    assert transport.closed == 1
    with pytest.raises(WorkerExecutionError, match="closed"):
        adapter.modulate(bits, 1_000_000.0)


def test_adapter_maps_remote_and_protocol_errors():
    reference = BPSKCodec()
    failed = FakeTransport(reference)
    failed.fail = True
    with pytest.raises(WorkerExecutionError, match="fake backend failure"):
        GnuRadioCodecAdapter(reference, failed).modulate(np.array([1], np.uint8), 8.0)
    malformed = FakeTransport(reference)
    malformed.bad_version = True
    with pytest.raises(WorkerProtocolError, match="version"):
        GnuRadioCodecAdapter(reference, malformed).modulate(np.array([1], np.uint8), 8.0)


def test_adapter_propagates_worker_timeout_with_transport_context():
    class TimedOutTransport(FakeTransport):
        def exchange(self, frames):
            raise WorkerTimeoutError("fake timeout after 5 ms")

    adapter = GnuRadioCodecAdapter(BPSKCodec(), TimedOutTransport())
    with pytest.raises(WorkerTimeoutError, match="5 ms"):
        adapter.modulate(np.array([1], np.uint8), 8.0)


def test_v1_request_roundtrip_and_iq_boundary_conversion():
    bits = np.array([0, 1, 1, 0], dtype=np.uint8)
    request = decode_request(encode_request("modulate", "bpsk", 12_000.0, bits))
    assert request.operation == "modulate"
    assert request.codec == "bpsk"
    np.testing.assert_array_equal(request.payload, bits)
    iq = np.array([1.0 + 0.25j, -0.5 - 0.75j], dtype=np.complex128)
    decoded = decode_request(encode_request("demodulate", "bpsk", 12_000.0, iq))
    np.testing.assert_allclose(decoded.payload, iq, atol=1e-7, rtol=0)
    assert decoded.payload.dtype == np.complex128


def test_v1_rejects_wrong_version_shape_length_and_operation():
    frames = encode_request("modulate", "bpsk", 1.0, np.array([0, 1], np.uint8))
    metadata = json.loads(frames[0].decode())
    metadata["version"] = 2
    with pytest.raises(FrameError, match="version"):
        decode_request((json.dumps(metadata).encode(), frames[1]))
    metadata = json.loads(frames[0].decode())
    metadata["shape"] = [3]
    with pytest.raises(FrameError, match="shape"):
        decode_request((json.dumps(metadata).encode(), frames[1]))
    metadata = json.loads(frames[0].decode())
    metadata["operation"] = "launch rockets"
    with pytest.raises(FrameError, match="operation"):
        decode_request((json.dumps(metadata).encode(), frames[1]))
    metadata = json.loads(frames[0].decode())
    metadata["version"] = True
    with pytest.raises(FrameError, match="integer"):
        decode_request((json.dumps(metadata).encode(), frames[1]))
    with pytest.raises(FrameError, match="exactly"):
        decode_request((frames[0], frames[1], b"extra"))
    with pytest.raises(FrameError, match="request_id"):
        encode_request("modulate", "bpsk", 1.0, [1], request_id="")


def test_v1_rejects_mismatched_response_id_and_structured_remote_error():
    request = decode_request(encode_request("modulate", "bpsk", 1.0, [1], request_id="id-1"))
    output = BPSKCodec().modulate(request.payload, request.sample_rate_hz)
    response = encode_response(request, output)
    with pytest.raises(FrameError, match="request_id"):
        decode_response(response, request_id="other-id", operation="modulate")
    remote = encode_response(request, error=RuntimeError("expected test failure"))
    with pytest.raises(RemoteWorkerError, match="expected test failure"):
        decode_response(remote, request_id="id-1", operation="modulate")


def test_worker_dispatches_to_plugin_and_returns_correlated_response():
    codec = BPSKCodec()
    request_frames = encode_request("modulate", codec.name, 1_000.0, [0, 1], request_id="fixed")
    request = decode_request(request_frames)
    response = process_request(codec, request)
    iq = decode_response(response, request_id="fixed", operation="modulate")
    np.testing.assert_array_equal(iq, codec.modulate(np.array([0, 1], np.uint8), 1_000.0))


def test_worker_returns_correlated_error_for_malformed_but_identifiable_request():
    request = encode_request("modulate", "bpsk", 1000.0, [0, 1], request_id="malformed-1")
    metadata = json.loads(request[0].decode())
    metadata["shape"] = [3]
    malformed = (json.dumps(metadata).encode(), request[1])
    with pytest.raises(FrameError, match="shape"):
        decode_request(malformed)
    response = _malformed_request_response(malformed, FrameError("bad test shape"))
    assert response is not None
    with pytest.raises(RemoteWorkerError, match="bad test shape"):
        decode_response(response, request_id="malformed-1", operation="modulate")


def test_optional_modules_are_not_required_to_import_adapter():
    # A fresh interpreter proves package import does not eagerly load runtimes.
    import subprocess
    import sys

    code = (
        "import sys; import integrations.gnu_radio.codec_adapter; "
        "assert 'gnuradio' not in sys.modules; assert 'zmq' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
