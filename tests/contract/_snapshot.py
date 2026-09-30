"""Builds a signature snapshot of the frozen SDK surface.

    python -m tests.contract._snapshot --write     # ONLY with an ADR + SDK_VERSION bump
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import inspect
import json
import sys
from pathlib import Path

from libraries.plugin_sdk import SDK_VERSION

MODULES = [
    "libraries.plugin_sdk.propagation",
    "libraries.plugin_sdk.waveform",
    "libraries.plugin_sdk.geodata",
    "libraries.plugin_sdk.event_bus",
    "libraries.plugin_sdk.simulation",
    "libraries.domain.frequency",
    "libraries.domain.position",
    "libraries.domain.radio",
    "libraries.domain.rf_results",
]
SNAPSHOT = Path(__file__).with_name("plugin_sdk_v1.snapshot.json")


def _describe_class(cls: type) -> dict:
    entry: dict = {"bases": [b.__name__ for b in cls.__bases__]}
    if issubclass(cls, enum.Enum):
        entry["members"] = {m.name: repr(m.value) for m in cls}
        return entry
    if dataclasses.is_dataclass(cls):
        entry["fields"] = [[f.name, str(f.type)] for f in dataclasses.fields(cls)]
    ann = cls.__dict__.get("__annotations__", {})
    entry["annotations"] = {k: str(v) for k, v in sorted(ann.items()) if not k.startswith("_")}
    abstract = getattr(cls, "__abstractmethods__", None)
    if abstract:
        entry["abstract"] = sorted(abstract)
    methods = {}
    for name, raw in vars(cls).items():
        if name.startswith("_"):
            continue
        kind, fn = "method", raw
        if isinstance(raw, property):
            kind, fn = "property", raw.fget
        elif isinstance(raw, classmethod):
            kind, fn = "classmethod", raw.__func__
        elif isinstance(raw, staticmethod):
            kind, fn = "staticmethod", raw.__func__
        if inspect.isfunction(fn):
            methods[name] = f"{kind} {inspect.signature(fn)}"
    entry["methods"] = dict(sorted(methods.items()))
    return entry


def build() -> dict:
    out: dict = {"sdk_version": SDK_VERSION, "modules": {}}
    for modname in MODULES:
        mod = importlib.import_module(modname)
        out["modules"][modname] = {
            n: _describe_class(o)
            for n, o in sorted(vars(mod).items())
            if inspect.isclass(o) and not n.startswith("_") and o.__module__ == modname
        }
    return out


if __name__ == "__main__":
    if "--write" in sys.argv:
        SNAPSHOT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
        print(f"wrote {SNAPSHOT}")
    else:
        print(json.dumps(build(), indent=2, sort_keys=True))
