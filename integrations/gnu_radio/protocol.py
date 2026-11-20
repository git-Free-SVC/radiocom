"""Versioned ZeroMQ multipart protocol for DSP worker requests and responses.

Each message has a UTF-8 JSON metadata frame followed by one binary payload
frame. IQ is interleaved little-endian float32 (real, imag); the public API
converts it to/from complex128 at this boundary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from services.dsp._validation import DSPInputError, finite_real, validate_bits, validate_iq

PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
_COMMON_FIELDS = {
    "version",
    "request_id",
    "operation",
    "codec",
    "sample_rate_hz",
    "payload_kind",
    "dtype",
    "shape",
    "payload_len",
    "status",
}


class FrameError(ValueError):
    """A local frame failed schema or payload validation."""


class RemoteWorkerError(RuntimeError):
    """A well-formed worker response reported a processing error."""


@dataclass(frozen=True)
class WorkerRequest:
    request_id: str
    operation: str
    codec: str
    sample_rate_hz: float
    payload: np.ndarray


def _positive_rate(value: Any) -> float:
    try:
        return finite_real(value, "sample_rate_hz", positive=True)
    except DSPInputError as exc:
        raise FrameError(str(exc)) from exc


def _encode_payload(kind: str, payload: Any) -> tuple[str, list[int], bytes]:
    if kind == "bits":
        try:
            values = validate_bits(payload)
        except DSPInputError as exc:
            raise FrameError(str(exc)) from exc
        return "uint8", [int(values.size)], values.tobytes(order="C")
    if kind == "iq":
        try:
            values = validate_iq(payload)
        except DSPInputError as exc:
            raise FrameError(str(exc)) from exc
        with np.errstate(over="ignore", invalid="ignore"):
            wire_complex = np.asarray(values, dtype="<c8")
        if not bool(np.all(np.isfinite(wire_complex))):
            raise FrameError("iq cannot be represented as finite complex64 wire samples")
        interleaved = wire_complex.view("<f4")
        raw = np.ascontiguousarray(interleaved).tobytes(order="C")
        return "complex64", [int(values.size)], raw
    raise FrameError(f"unsupported payload_kind {kind!r}")


def _metadata_bytes(metadata: dict[str, Any]) -> bytes:
    try:
        return json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FrameError("metadata is not valid finite JSON") from exc


def _make_message(
    *,
    request_id: str,
    operation: str,
    codec: str,
    sample_rate_hz: float,
    payload_kind: str,
    payload: Any,
    status: str,
    error: dict[str, str] | None = None,
) -> tuple[bytes, bytes]:
    if operation not in {"modulate", "demodulate"}:
        raise FrameError(f"unsupported operation {operation!r}")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise FrameError("request_id must be a non-empty string of at most 128 characters")
    if not isinstance(codec, str) or not codec or len(codec) > 128:
        raise FrameError("codec must be a non-empty string of at most 128 characters")
    rate = _positive_rate(sample_rate_hz)
    if status == "error":
        if error is None or not isinstance(error.get("message"), str):
            raise FrameError("error response requires a structured error message")
        if payload_kind == "iq":
            dtype = "complex64"
        elif payload_kind == "bits":
            dtype = "uint8"
        else:
            raise FrameError("error response payload kind is unsupported")
        shape, raw = [0], b""
    else:
        dtype, shape, raw = _encode_payload(payload_kind, payload)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise FrameError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    metadata: dict[str, Any] = {
        "version": PROTOCOL_VERSION,
        "request_id": request_id,
        "operation": operation,
        "codec": codec,
        "sample_rate_hz": rate,
        "payload_kind": payload_kind,
        "dtype": dtype,
        "shape": shape,
        "payload_len": len(raw),
        "status": status,
    }
    if error is not None:
        metadata["error"] = error
    return _metadata_bytes(metadata), raw


def encode_request(
    operation: str,
    codec: str,
    sample_rate_hz: float,
    payload: Any,
    *,
    request_id: str | None = None,
) -> tuple[bytes, bytes]:
    """Create a validated v1 request; metadata and payload are separate frames."""
    if operation == "modulate":
        kind = "bits"
    elif operation == "demodulate":
        kind = "iq"
    else:
        raise FrameError(f"unsupported operation {operation!r}")
    return _make_message(
        request_id=request_id if request_id is not None else uuid.uuid4().hex,
        operation=operation,
        codec=codec,
        sample_rate_hz=sample_rate_hz,
        payload_kind=kind,
        payload=payload,
        status="request",
    )


def _decode_parts(
    parts: Sequence[bytes], *, expected_status: str
) -> tuple[dict[str, Any], np.ndarray]:
    if len(parts) != 2:
        raise FrameError("message must contain exactly metadata and payload frames")
    metadata_frame, raw = parts
    if not isinstance(metadata_frame, (bytes, bytearray, memoryview)):
        raise FrameError("metadata frame must be bytes")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise FrameError("payload frame must be bytes")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise FrameError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    try:
        metadata = json.loads(bytes(metadata_frame).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FrameError("metadata frame is not valid UTF-8 JSON") from exc
    if not isinstance(metadata, dict) or not _COMMON_FIELDS.issubset(metadata):
        raise FrameError("metadata is missing required fields")
    if isinstance(metadata["version"], bool) or not isinstance(metadata["version"], int):
        raise FrameError("protocol version must be an integer")
    if metadata["version"] != PROTOCOL_VERSION:
        raise FrameError(f"unsupported protocol version {metadata['version']!r}")
    if metadata["status"] != expected_status:
        raise FrameError(f"expected status {expected_status!r}")
    if not isinstance(metadata["operation"], str) or metadata["operation"] not in {
        "modulate",
        "demodulate",
    }:
        raise FrameError("metadata operation is unsupported")
    if not isinstance(metadata["request_id"], str) or not metadata["request_id"]:
        raise FrameError("metadata request_id must be a non-empty string")
    if not isinstance(metadata["codec"], str) or not metadata["codec"]:
        raise FrameError("metadata codec must be a non-empty string")
    _positive_rate(metadata["sample_rate_hz"])
    shape = metadata["shape"]
    if not isinstance(shape, list) or len(shape) != 1:
        raise FrameError("shape must declare one array dimension")
    length = shape[0]
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise FrameError("shape length must be a non-negative integer")
    payload_len = metadata["payload_len"]
    if isinstance(payload_len, bool) or not isinstance(payload_len, int) or payload_len < 0:
        raise FrameError("payload_len must be a non-negative integer")
    if payload_len != len(raw):
        raise FrameError("payload_len does not match binary payload size")
    kind, dtype = metadata["payload_kind"], metadata["dtype"]
    if kind == "bits" and dtype == "uint8":
        expected_bytes = length
        if expected_bytes != len(raw):
            raise FrameError("bits shape does not match payload byte count")
        values = np.frombuffer(raw, dtype=np.uint8).copy()
        if values.size and bool(np.any(values > 1)):
            raise FrameError("bit payload may contain only 0 or 1")
    elif kind == "iq" and dtype == "complex64":
        expected_bytes = length * 2 * np.dtype("<f4").itemsize
        if expected_bytes != len(raw):
            raise FrameError("IQ shape does not match payload byte count")
        scalars = np.frombuffer(raw, dtype="<f4")
        if scalars.size and not bool(np.all(np.isfinite(scalars))):
            raise FrameError("IQ payload contains non-finite values")
        pairs = scalars.reshape(-1, 2)
        values = pairs[:, 0].astype(np.float64) + 1j * pairs[:, 1].astype(np.float64)
        values = np.ascontiguousarray(values, dtype=np.complex128)
    else:
        raise FrameError("payload_kind and dtype are unsupported or mismatched")
    return metadata, values


def decode_request(parts: Sequence[bytes]) -> WorkerRequest:
    metadata, payload = _decode_parts(parts, expected_status="request")
    expected_kind = "bits" if metadata["operation"] == "modulate" else "iq"
    if metadata["payload_kind"] != expected_kind:
        raise FrameError("request payload kind does not match operation")
    return WorkerRequest(
        request_id=metadata["request_id"],
        operation=metadata["operation"],
        codec=metadata["codec"],
        sample_rate_hz=float(metadata["sample_rate_hz"]),
        payload=payload,
    )


def encode_response(
    request: WorkerRequest,
    output: Any = None,
    *,
    error: Exception | None = None,
) -> tuple[bytes, bytes]:
    if error is not None:
        return _make_message(
            request_id=request.request_id,
            operation=request.operation,
            codec=request.codec,
            sample_rate_hz=request.sample_rate_hz,
            payload_kind="iq" if request.operation == "modulate" else "bits",
            payload=None,
            status="error",
            error={"type": type(error).__name__, "message": str(error)},
        )
    output_kind = "iq" if request.operation == "modulate" else "bits"
    return _make_message(
        request_id=request.request_id,
        operation=request.operation,
        codec=request.codec,
        sample_rate_hz=request.sample_rate_hz,
        payload_kind=output_kind,
        payload=output,
        status="ok",
    )


def decode_response(
    parts: Sequence[bytes], *, request_id: str, operation: str, codec: str | None = None
) -> np.ndarray:
    if operation not in {"modulate", "demodulate"}:
        raise FrameError(f"unsupported operation {operation!r}")
    if len(parts) == 2:
        try:
            preview = json.loads(bytes(parts[0]).decode("utf-8"))
        except Exception:
            preview = None
        if isinstance(preview, dict) and preview.get("status") == "error":
            metadata, _ = _decode_parts(parts, expected_status="error")
            if metadata["request_id"] != request_id or metadata["operation"] != operation:
                raise FrameError("worker error response does not match request")
            if codec is not None and metadata["codec"] != codec:
                raise FrameError("worker error response codec does not match request")
            error_data = metadata.get("error")
            if not isinstance(error_data, dict) or not isinstance(error_data.get("message"), str):
                raise FrameError("worker error response has no structured message")
            raise RemoteWorkerError(
                f"{error_data.get('type', 'WorkerError')}: {error_data['message']}"
            )
    metadata, payload = _decode_parts(parts, expected_status="ok")
    if metadata["request_id"] != request_id:
        raise FrameError("response request_id does not match request")
    if metadata["operation"] != operation:
        raise FrameError("response operation does not match request")
    if codec is not None and metadata["codec"] != codec:
        raise FrameError("response codec does not match request")
    expected_kind = "iq" if operation == "modulate" else "bits"
    if metadata["payload_kind"] != expected_kind:
        raise FrameError("response payload kind does not match operation")
    return payload
