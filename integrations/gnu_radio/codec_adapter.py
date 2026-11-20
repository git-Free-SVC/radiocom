"""WaveformCodec-facing proxy to an optional GNU Radio worker process."""

from __future__ import annotations

from threading import RLock
from typing import Any, Protocol

import numpy as np

from .errors import WorkerExecutionError, WorkerProtocolError
from .protocol import FrameError, RemoteWorkerError, decode_response, encode_request


class WorkerTransport(Protocol):
    """Minimal request/reply port. Implementations own their socket lifecycle."""

    def start(self) -> None:
        """Bring the transport up (idempotent)."""
        ...

    def exchange(self, frames: tuple[bytes, bytes]) -> tuple[bytes, bytes]:
        """Send one multipart request and return the multipart response."""
        ...

    def close(self) -> None:
        """Tear the transport down; subsequent calls are no-ops."""
        ...


class GnuRadioCodecAdapter:
    """Implements the frozen codec API while delegating IQ work to a worker.

    ``reference_codec`` provides analytical BER/bandwidth and a stable codec
    name. The injected transport forwards only modulation/demodulation calls.
    No optional package is imported and no connection is opened by construction.
    """

    def __init__(self, reference_codec: Any, transport: WorkerTransport) -> None:
        for member in ("name", "ber", "occupied_bandwidth_hz"):
            if not hasattr(reference_codec, member):
                raise TypeError(f"reference_codec is missing {member!r}")
        for member in ("start", "exchange", "close"):
            if not callable(getattr(transport, member, None)):
                raise TypeError(f"transport is missing callable {member!r}")
        self._reference_codec = reference_codec
        self._transport = transport
        self._lock = RLock()
        self._closed = False
        self.name = str(reference_codec.name)

    def _call_worker(
        self, operation: str, payload: np.ndarray, sample_rate_hz: float
    ) -> np.ndarray:
        with self._lock:
            if self._closed:
                raise WorkerExecutionError("GNU Radio adapter is closed")
            try:
                frames = encode_request(operation, self.name, sample_rate_hz, payload)
                self._transport.start()
                response = self._transport.exchange(frames)
                return decode_response(
                    response,
                    request_id=_request_id(frames),
                    operation=operation,
                    codec=self.name,
                )
            except RemoteWorkerError as exc:
                raise WorkerExecutionError(str(exc)) from exc
            except FrameError as exc:
                raise WorkerProtocolError(str(exc)) from exc

    def modulate(self, bits: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        result = self._call_worker("modulate", bits, sample_rate_hz)
        return np.ascontiguousarray(result, dtype=np.complex128)

    def demodulate(self, iq: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        result = self._call_worker("demodulate", iq, sample_rate_hz)
        return np.ascontiguousarray(result, dtype=np.uint8)

    def ber(self, ebn0_db: float) -> float:
        return self._reference_codec.ber(ebn0_db)

    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float:
        return self._reference_codec.occupied_bandwidth_hz(symbol_rate_hz)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._transport.close()

    def __enter__(self) -> "GnuRadioCodecAdapter":
        if self._closed:
            raise WorkerExecutionError("GNU Radio adapter is closed")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def _request_id(frames: tuple[bytes, bytes]) -> str:
    import json

    try:
        return str(json.loads(frames[0].decode("utf-8"))["request_id"])
    except Exception as exc:
        raise WorkerProtocolError("locally generated request metadata is invalid") from exc
