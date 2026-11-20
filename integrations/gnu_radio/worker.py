"""Optional ZeroMQ worker host for an installed GNU Radio codec plugin.

The host imports GNU Radio and PyZMQ only inside ``serve``. A plugin factory
named on the command line must return a WaveformCodec-compatible object backed
by the selected GNU Radio module. This keeps open-source plugins replaceable
without coupling the NumPy codecs to a particular GNU Radio release.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import threading
from typing import Any

import numpy as np

from .errors import WorkerUnavailableError
from .protocol import FrameError, WorkerRequest, decode_request, encode_response


def _load_factory(spec: str) -> Any:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("--codec-factory must use module.path:factory_name")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute)
    return factory() if callable(factory) else factory


def _check_codec(codec: Any) -> None:
    required = ("name", "modulate", "demodulate", "ber", "occupied_bandwidth_hz")
    missing = [name for name in required if not hasattr(codec, name)]
    if missing:
        raise TypeError(f"codec plugin is missing WaveformCodec members: {', '.join(missing)}")


def process_request(codec: Any, request: WorkerRequest) -> tuple[bytes, bytes]:
    """Dispatch a decoded request and turn plugin failures into wire errors."""
    try:
        _check_codec(codec)
        if request.codec != codec.name:
            raise ValueError(
                f"worker codec {codec.name!r} does not match request {request.codec!r}"
            )
        if request.operation == "modulate":
            result = codec.modulate(request.payload, request.sample_rate_hz)
        elif request.operation == "demodulate":
            result = codec.demodulate(request.payload, request.sample_rate_hz)
        else:
            raise ValueError(f"unsupported operation {request.operation!r}")
        return encode_response(request, result)
    except Exception as exc:
        return encode_response(request, error=exc)


def _malformed_request_response(parts: list[bytes], error: Exception) -> tuple[bytes, bytes] | None:
    """Reply when malformed payloads still carry safe correlation metadata."""
    if len(parts) != 2:
        return None
    try:
        metadata = json.loads(parts[0].decode("utf-8"))
        request_id = metadata["request_id"]
        operation = metadata["operation"]
        codec = metadata["codec"]
        rate = float(metadata["sample_rate_hz"])
        if (
            not isinstance(request_id, str)
            or not request_id
            or operation not in {"modulate", "demodulate"}
            or not isinstance(codec, str)
            or not codec
            or not math.isfinite(rate)
            or rate <= 0.0
        ):
            return None
        request = WorkerRequest(
            request_id=request_id,
            operation=operation,
            codec=codec,
            sample_rate_hz=rate,
            payload=np.empty(0, dtype=np.uint8),
        )
        return encode_response(request, error=error)
    except Exception:
        return None


def serve(
    codec: Any,
    endpoint: str = "tcp://127.0.0.1:5557",
    *,
    stop_event: threading.Event | None = None,
    require_gnuradio: bool = True,
) -> None:
    """Run a sequential ZeroMQ REP worker until ``stop_event`` is set.

    ``require_gnuradio`` is exposed for isolated protocol tests only. Production
    startup always checks the actual GNU Radio Python runtime before binding.
    """
    _check_codec(codec)
    try:
        import zmq
    except ImportError as exc:
        raise WorkerUnavailableError(
            "PyZMQ is required only in the worker process; install pyzmq there"
        ) from exc
    if require_gnuradio:
        try:
            importlib.import_module("gnuradio.gr")
        except ImportError as exc:
            raise WorkerUnavailableError(
                "GNU Radio Python runtime is unavailable; install GNU Radio in the worker environment"
            ) from exc
    stop = stop_event or threading.Event()
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.setsockopt(zmq.LINGER, 0)
    socket.bind(endpoint)
    try:
        while not stop.is_set():
            if not socket.poll(100, zmq.POLLIN):
                continue
            parts = socket.recv_multipart()
            try:
                request = decode_request(parts)
            except FrameError as exc:
                response = _malformed_request_response(parts, exc)
                if response is not None:
                    socket.send_multipart(list(response))
                # Without safe correlation metadata, there is no valid reply.
                continue
            socket.send_multipart(list(process_request(codec, request)))
    finally:
        socket.close(linger=0)
        context.term()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5557")
    parser.add_argument("--codec-factory", required=True)
    args = parser.parse_args()
    try:
        importlib.import_module("gnuradio.gr")
    except ImportError as exc:
        raise WorkerUnavailableError(
            "GNU Radio Python runtime is unavailable; install GNU Radio in the worker environment"
        ) from exc
    codec = _load_factory(args.codec_factory)
    serve(codec, args.endpoint)


if __name__ == "__main__":
    main()
