"""Cross-platform Agent F acceptance runner; performs no Git operations."""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "tests/contract/test_waveform_codec_contract.py"
CONTRACT_TARGETS = (
    "services.dsp.bpsk:BPSKCodec",
    "services.dsp.qpsk:QPSKCodec",
    "services.dsp.am:AMCodec",
    "services.dsp.fm:FMCodec",
    "services.dsp.ofdm:OFDMCodec",
)
SOURCE_METHODS = {
    "services/dsp/bpsk.py": {
        "BPSKCodec": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz"}
    },
    "services/dsp/qpsk.py": {
        "QPSKCodec": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz"}
    },
    "services/dsp/am.py": {"AMCodec": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz"}},
    "services/dsp/fm.py": {"FMCodec": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz"}},
    "services/dsp/ofdm.py": {
        "OFDMCodec": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz"}
    },
    "integrations/gnu_radio/codec_adapter.py": {
        "GnuRadioCodecAdapter": {"modulate", "demodulate", "ber", "occupied_bandwidth_hz", "close"}
    },
}


def run(label: str, argv: list[str]) -> None:
    print(f"[{label}] {' '.join(argv)}", flush=True)
    completed = subprocess.run(argv, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def content_audit() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    required = [
        *SOURCE_METHODS,
        "services/dsp/__init__.py",
        "services/dsp/_validation.py",
        "services/dsp/_analytic.py",
        "services/dsp/README.md",
        "services/dsp/STRESS_REPORT.md",
        "integrations/gnu_radio/protocol.py",
        "integrations/gnu_radio/worker.py",
        "integrations/gnu_radio/zmq_transport.py",
        "tests/unit/dsp/test_waveforms.py",
        "tests/unit/dsp/test_gnuradio_adapter.py",
        CONTRACT,
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit("required Agent F/master contract files missing: " + ", ".join(missing))
    report = (ROOT / "services/dsp/STRESS_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "**A —",
        "**B —",
        "**C —",
        "**D —",
        "**E —",
        "**F —",
        "test_regression_ofdm_qpsk_bits_preserve_frame_axis",
    ):
        if marker not in report:
            raise SystemExit(f"stress report is missing required evidence marker {marker!r}")
    for relative in SOURCE_METHODS:
        source = ROOT / relative
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError) as exc:
            raise SystemExit(f"source audit failed for {relative}: {exc}") from exc
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        for class_name, methods in SOURCE_METHODS[relative].items():
            node = classes.get(class_name)
            actual = (
                {
                    child.name
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if node
                else set()
            )
            absent = sorted(methods - actual)
            if absent:
                raise SystemExit(f"{relative}:{class_name} is missing methods: {', '.join(absent)}")
    for module_name in (
        "services.dsp",
        "services.dsp.bpsk",
        "services.dsp.qpsk",
        "services.dsp.am",
        "services.dsp.fm",
        "services.dsp.ofdm",
        "integrations.gnu_radio.codec_adapter",
        "integrations.gnu_radio.protocol",
    ):
        importlib.import_module(module_name)
    print("[W2-10] required files, AST method manifest, and public imports passed")


def main() -> None:
    if not (ROOT / CONTRACT).is_file():
        raise SystemExit(
            "Run this script from a RADIOCOM master checkout containing the frozen Wave 0 contract; no files were installed."
        )
    # Each named gate has a focused check; W2-9 then reruns the complete suite.
    gates = [
        ("W2-1 decision record/content", None),
        (
            "W2-2 validation and boundary cases",
            ["tests/unit/dsp/test_waveforms.py", "-k", "hostile or extreme_positive"],
        ),
        (
            "W2-3 BER, bandwidth, sweep, AWGN, benchmark",
            [
                "tests/unit/dsp/test_waveforms.py",
                "-k",
                "ber_golden or bandwidth or monotonicity or numeric_sweep or awgn or performance",
            ],
        ),
        (
            "W2-4 BPSK/QPSK codecs",
            ["tests/unit/dsp/test_waveforms.py", "-k", "fixed_constellation or public_codec_shape"],
        ),
        ("W2-5 OOK/FSK codecs", ["tests/unit/dsp/test_waveforms.py", "-k", "ook or fsk"]),
        ("W2-6 OFDM codec", ["tests/unit/dsp/test_waveforms.py", "-k", "ofdm"]),
        (
            "W2-7 fake adapter/error lifecycle",
            ["tests/unit/dsp/test_gnuradio_adapter.py", "-k", "adapter or v1"],
        ),
        (
            "W2-8 worker/frame dispatch",
            ["tests/unit/dsp/test_gnuradio_adapter.py", "-k", "worker or v1"],
        ),
        ("W2-9 full unit and stress suite", ["tests/unit/dsp"]),
    ]
    print("[W2-1] architecture decisions and frozen API are summarized in services/dsp/README.md")
    for label, selection in gates[1:]:
        assert selection is not None
        run(label, [sys.executable, "-m", "pytest", "-q", *selection])
    for index, target in enumerate(CONTRACT_TARGETS, start=1):
        run(
            f"W2-10 frozen Wave 0 contract {index}/5",
            [sys.executable, "-m", "pytest", "-q", CONTRACT, f"--waveform-impl={target}"],
        )
    content_audit()
    print("All Agent F acceptance checks passed. No Git command was run.")


if __name__ == "__main__":
    main()
