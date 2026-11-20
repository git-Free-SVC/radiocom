# GNU Radio adapter

`GnuRadioCodecAdapter` preserves the Wave 0 `WaveformCodec` API at the package
boundary. Its injected `reference_codec` provides the analytical `ber` and
`occupied_bandwidth_hz` methods. Sample processing goes to an injected worker
transport; the NumPy package never imports GNU Radio, PyZMQ, or this adapter.

## Components and ownership

| Component          | Responsibility                                                  | Optional dependency            |
|--------------------|-----------------------------------------------------------------|--------------------------------|
| `services/dsp/`    | Deterministic reference codecs and scalar models                | NumPy only                     |
| `codec_adapter.py` | Implements the frozen API, routes IQ operations to worker       | None at import                 |
| `protocol.py`      | Validates v1 metadata, IDs, shapes, dtypes, and payload length  | NumPy                          |
| `zmq_transport.py` | Lazy REQ socket, timeout, and idempotent close                  | PyZMQ at `start()`             |
| `worker.py`        | REP host that dispatches to the selected GNU Radio codec plugin | GNU Radio + PyZMQ at `serve()` |

No socket is opened by importing or constructing an adapter. Start the worker
in the GNU Radio environment, for example:

```powershell
python -m integrations.gnu_radio.worker --endpoint tcp://127.0.0.1:5557 --codec-factory my_gnuradio_plugin:build_codec
```

The factory must return an object implementing `name`, `modulate`,
`demodulate`, `ber`, and `occupied_bandwidth_hz`. It should use the installed
GNU Radio version to process IQ and keep that version-specific implementation
inside its integration package. The host checks the GNU Radio runtime before
binding the endpoint and returns structured errors for plugin failures.

The v1 protocol is a ZeroMQ multipart pair: UTF-8 JSON metadata followed by a
binary payload. Metadata includes `version`, `request_id`, `operation`,
`codec`, `sample_rate_hz`, `payload_kind`, `dtype`, `shape`, `payload_len`, and
`status`. Bits use `uint8`; IQ uses interleaved little-endian `float32` real and
imaginary components (`complex64`). The public API receives `complex128` and
conversion happens only at the boundary. The worker rejects malformed shapes,
truncated/oversized payloads, non-finite values, unsupported versions, and
operation/payload mismatches before calling a codec.

## Add another open-source backend

1. Implement the frozen five-member `WaveformCodec` shape in a new integration
   package; do not edit `libraries/plugin_sdk/` or add members to its Protocol.
2. Keep plugin imports lazy and dependencies optional. Implement a transport
   with `start()`, `exchange(frames)`, and idempotent `close()`.
3. Reuse the versioned frame contract, or add a separately versioned adapter
   protocol if the transport cannot carry multipart messages.
4. Convert backend-specific units, sample types, and layouts only at the
   adapter edge; the service API remains `numpy.ndarray` with complex128 IQ and
   uint8 recovered bits.
5. Run the same unmodified Wave 0 contract test against the adapter and add
   fake-transport tests for success, malformed frames, timeouts, errors, and
   cleanup. Do not install dependencies dynamically or create a global plugin
   registry.
