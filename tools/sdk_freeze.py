"""SDK freeze tooling: versioned snapshots + semver rule + ADR rule.

    python -m tools.sdk_freeze diff      # what changed vs the latest snapshot, and what bump it needs
    python -m tools.sdk_freeze write     # record a NEW snapshot for SDK_VERSION (enforces both rules)

Rules enforced by `write` (and re-checked in tests / CI):
  VERSION  Snapshots are one file per version in sdk_snapshots/ and are never overwritten.
           Surface change vs the previous snapshot needs a big-enough SDK_VERSION bump:
             removed/changed anything, or added a member to a Protocol/ABC  -> MAJOR
             purely additive (new class/function/constant/method)           -> MINOR at least
  ADR      docs/adr/*.md must contain an accepted ADR for that version:
             Status: Accepted
             SDK-Version: X.Y.Z
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "sdk_snapshots"
ADR_DIR = ROOT / "docs" / "adr"

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


class FreezeError(Exception):
    """A freeze rule is violated (message is meant to be shown to the developer)."""


# --------------------------------------------------------------------------- versions
def parse_version(v: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        raise FreezeError(f"SDK version {v!r} is not MAJOR.MINOR.PATCH")
    return int(m[1]), int(m[2]), int(m[3])


def snapshot_path(version: str, snap_dir: Path = SNAP_DIR) -> Path:
    return snap_dir / f"plugin_sdk_{version}.json"


def current_version() -> str:
    from libraries.plugin_sdk import SDK_VERSION

    return SDK_VERSION


# --------------------------------------------------------------------------- surface
def _callable_name(obj: Any) -> str | None:
    if callable(obj) and hasattr(obj, "__qualname__"):
        return "callable:" + obj.__qualname__  # avoids memory addresses in repr()
    return None


def _field_default(f: dataclasses.Field) -> str:
    if f.default is not dataclasses.MISSING:
        return _callable_name(f.default) or repr(f.default)
    if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        return "factory:" + (_callable_name(f.default_factory) or repr(f.default_factory))
    return "<required>"


def _describe_class(cls: type) -> dict:
    entry: dict = {"bases": [b.__name__ for b in cls.__bases__]}
    if issubclass(cls, enum.Enum):
        entry["members"] = {m.name: repr(m.value) for m in cls}
        return entry
    if dataclasses.is_dataclass(cls):
        p = cls.__dataclass_params__
        entry["dataclass"] = {"frozen": p.frozen, "order": p.order, "eq": p.eq}
        entry["fields"] = [
            [f.name, str(f.type), _field_default(f)] for f in dataclasses.fields(cls)
        ]
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


def _module_constants(mod) -> dict[str, str]:
    """Public top-level assignments (type aliases, constants), as source text.
    Source text (not repr) keeps the snapshot stable across Python versions."""
    tree = ast.parse(inspect.getsource(mod))
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names, value = [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            names, value = [node.target.id], node.value
        else:
            continue
        for n in names:
            if not n.startswith("_"):
                out[n] = ast.unparse(value)
    return dict(sorted(out.items()))


def build_surface(modules: list[str] = MODULES) -> dict:
    """The frozen surface: classes, module-level functions and constants of each module."""
    out: dict = {}
    for modname in modules:
        mod = importlib.import_module(modname)
        classes, functions = {}, {}
        for n, o in sorted(vars(mod).items()):
            if n.startswith("_") or getattr(o, "__module__", None) != modname:
                continue
            if inspect.isclass(o):
                classes[n] = _describe_class(o)
            elif inspect.isfunction(o):
                functions[n] = str(inspect.signature(o))
        out[modname] = {
            "classes": classes,
            "functions": functions,
            "constants": _module_constants(mod),
        }
    return out


def build_snapshot(version: str | None = None) -> dict:
    return {"sdk_version": version or current_version(), "modules": build_surface()}


# --------------------------------------------------------------------------- snapshots on disk
def load_snapshots(snap_dir: Path = SNAP_DIR) -> dict[str, dict]:
    """{version: snapshot}, ordered oldest -> newest. Validates file name == content."""
    found: dict[str, dict] = {}
    for p in snap_dir.glob("plugin_sdk_*.json"):
        version = p.stem.removeprefix("plugin_sdk_")
        parse_version(version)
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("sdk_version") != version:
            raise FreezeError(
                f"{p.name}: file says version {version} but content says {data.get('sdk_version')}"
            )
        found[version] = data
    return dict(sorted(found.items(), key=lambda kv: parse_version(kv[0])))


# --------------------------------------------------------------------------- diff + semver rule
def _flatten(obj: Any, path: tuple = ()) -> Iterator[tuple[tuple, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, path + (k,))
    else:
        yield path, json.dumps(obj, sort_keys=True)


def _extends_contract(modules: dict, p: tuple) -> bool:
    """True if `p` is a new member of a Protocol/ABC that already existed:
    every existing implementation would suddenly be incomplete."""
    if len(p) < 5 or p[1] != "classes" or p[3] not in ("methods", "annotations"):
        return False
    entry = modules[p[0]]["classes"][p[2]]
    return "Protocol" in entry["bases"] or "abstract" in entry


def classify(old: dict, new: dict) -> tuple[str, list[str]]:
    """-> ("none" | "minor" | "major", human-readable reasons)."""
    o, n = dict(_flatten(old["modules"])), dict(_flatten(new["modules"]))
    major: list[str] = []
    minor: list[str] = []
    for p, v in o.items():
        if p not in n:
            major.append(f"removed: {'.'.join(p)}")
        elif n[p] != v:
            major.append(f"changed: {'.'.join(p)}\n      was {v}\n      now {n[p]}")
    for p in n:
        if p in o:
            continue
        if _extends_contract(new["modules"], p):
            major.append(f"added to Protocol/ABC (breaks implementers): {'.'.join(p)}")
        else:
            minor.append(f"added: {'.'.join(p)}")
    if major:
        return "major", major + minor
    return ("minor", minor) if minor else ("none", [])


def bump_ok(old_v: str, new_v: str, level: str) -> bool:
    o, n = parse_version(old_v), parse_version(new_v)
    if n <= o:
        return False
    if level == "major":
        return n[0] > o[0]
    if level == "minor":
        return n[0] > o[0] or (n[0] == o[0] and n[1] > o[1])
    return True


def required_bump(level: str) -> str:
    return {"major": "MAJOR (X.0.0)", "minor": "MINOR (x.Y.0) or higher", "none": "any"}[level]


def check_history(snaps: dict[str, dict]) -> list[str]:
    """Every consecutive pair of recorded snapshots must respect the semver rule."""
    errors = []
    versions = list(snaps)
    for a, b in zip(versions, versions[1:]):
        level, _ = classify(snaps[a], snaps[b])
        if not bump_ok(a, b, level):
            errors.append(
                f"{a} -> {b}: surface change is '{level}' but version bump is too small "
                f"(needs {required_bump(level)})"
            )
    return errors


# --------------------------------------------------------------------------- ADR rule
def find_accepted_adr(version: str, adr_dir: Path = ADR_DIR) -> Path | None:
    status = re.compile(r"^\s*status\s*:\s*accepted\b", re.I | re.M)
    ver = re.compile(rf"^\s*sdk[-_ ]version\s*:\s*{re.escape(version)}\s*$", re.I | re.M)
    for p in sorted(adr_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        if status.search(text) and ver.search(text):
            return p
    return None


# --------------------------------------------------------------------------- write
def write_snapshot(
    version: str | None = None,
    *,
    snap_dir: Path = SNAP_DIR,
    adr_dir: Path = ADR_DIR,
    surface: dict | None = None,
    require_adr: bool = True,
) -> Path:
    """Record a new snapshot. Refuses unless VERSION and ADR rules hold."""
    version = version or current_version()
    parse_version(version)
    snap_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_path(version, snap_dir)
    if target.exists():
        raise FreezeError(
            f"{target.name} already exists. Released snapshots are immutable: "
            f"bump SDK_VERSION instead of rewriting it."
        )
    if require_adr and not find_accepted_adr(version, adr_dir):
        raise FreezeError(
            f"No accepted ADR for SDK {version}. Add a file in {adr_dir} containing the lines\n"
            f"    Status: Accepted\n    SDK-Version: {version}"
        )
    new = {"sdk_version": version, "modules": surface if surface is not None else build_surface()}
    snaps = load_snapshots(snap_dir)
    if snaps:
        prev_v = list(snaps)[-1]
        level, reasons = classify(snaps[prev_v], new)
        if not bump_ok(prev_v, version, level):
            raise FreezeError(
                f"Surface change vs {prev_v} is '{level}': version must go to "
                f"{required_bump(level)}, got {version}.\n  " + "\n  ".join(reasons[:15])
            )
    target.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "diff"
    try:
        if cmd == "write":
            print(f"wrote {write_snapshot()}")
            return 0
        if cmd == "diff":
            snaps = load_snapshots()
            if not snaps:
                print("no snapshots yet")
                return 1
            prev_v = list(snaps)[-1]
            level, reasons = classify(snaps[prev_v], build_snapshot())
            print(f"latest snapshot: {prev_v}   SDK_VERSION: {current_version()}   change: {level}")
            for r in reasons:
                print("  -", r)
            if level != "none":
                print(f"needs version bump: {required_bump(level)}")
            return 0
        print(__doc__)
        return 2
    except FreezeError as e:
        print(f"FREEZE RULE VIOLATION: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
