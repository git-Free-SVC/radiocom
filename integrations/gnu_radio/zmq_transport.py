"""Lazy PyZMQ REQ transport for a separately started GNU Radio worker."""

from __future__ import annotations

from typing import Any

from .errors import WorkerProtocolError, WorkerTimeoutError, WorkerUnavailableError


class ZeroMQTransport:
    """Synchronous REQ transport; importing or constructing it opens no socket."""

    def __init__(self, endpoint: str, *, timeout_ms: int = 3000) -> None:
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("endpoint must be a non-empty ZeroMQ endpoint")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ValueError("timeout_ms must be a positive integer")
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self._context: Any = None
        self._socket: Any = None

    def start(self) -> None:
        if self._socket is not None:
            return
        try:
            import zmq
        except ImportError as exc:
            raise WorkerUnavailableError(
                "PyZMQ is optional; install pyzmq in the GNU Radio worker environment"
            ) from exc
        try:
            self._context = zmq.Context.instance()
            self._socket = self._context.socket(zmq.REQ)
            self._socket.setsockopt(zmq.LINGER, 0)
            self._socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
            self._socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            self._socket.connect(self.endpoint)
        except Exception as exc:
            self.close()
            raise WorkerUnavailableError(f"could not connect to worker at {self.endpoint}") from exc

    def exchange(self, frames: tuple[bytes, bytes]) -> tuple[bytes, bytes]:
        if self._socket is None:
            self.start()
        try:
            self._socket.send_multipart(list(frames))
            response = self._socket.recv_multipart()
        except Exception as exc:
            # A timed-out REQ socket cannot safely continue its send/receive cycle.
            self.close()
            try:
                import zmq
            except ImportError:
                raise WorkerUnavailableError("PyZMQ became unavailable during exchange") from exc
            if isinstance(exc, zmq.Again):
                raise WorkerTimeoutError(f"worker timed out after {self.timeout_ms} ms") from exc
            raise WorkerUnavailableError("ZeroMQ worker exchange failed") from exc
        if len(response) != 2:
            raise WorkerProtocolError("worker returned an invalid multipart response")
        return bytes(response[0]), bytes(response[1])

    def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            try:
                socket.close(linger=0)
            except Exception:
                pass
        self._context = None
