"""Stress / fuzz harness for services/scenario.

Run from anywhere (paths are resolved from this file's location):

    python services/scenario/stress_scenario.py

Not collected by pytest (name does not match ``test_*.py``).
"""

from __future__ import annotations

import copy
import importlib
import json
import random
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import yaml

# services/scenario/stress_scenario.py -> repo root is two levels above this folder.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_api = importlib.import_module("services.scenario")
ScenarioError = _api.ScenarioError
ScenarioValidationError = _api.ScenarioValidationError
load_scenario = _api.load_scenario
parse_scenario_dict = _api.parse_scenario_dict
validate_scenario_dict = _api.validate_scenario_dict

#: Exception types that would indicate a bug (as opposed to a clean rejection).
UNEXPECTED = (
    ArithmeticError,
    AssertionError,
    LookupError,
    OSError,
    RecursionError,
    RuntimeError,
    TypeError,
    ValueError,
)

FIXTURES = REPO_ROOT / "tests" / "unit" / "scenario" / "fixtures"
BASE: dict[str, Any] = json.loads(
    (FIXTURES / "mountain_communication_test.json").read_text(encoding="utf-8")
)


def timed(label: str, fn: Callable[[], Any]) -> None:
    start = time.perf_counter()
    try:
        result = fn()
    except ScenarioError as exc:  # clean, expected rejection
        first_line = str(exc).splitlines()[0][:110]
        result = f"REJECTED ({type(exc).__name__}): {first_line}"
    except UNEXPECTED as exc:  # a bug: report it, never abort the harness
        result = f"UNEXPECTED {type(exc).__name__}: {str(exc)[:110]}"
    elapsed = time.perf_counter() - start
    print(f"{label:55s} {elapsed:7.3f}s  {result if isinstance(result, str) else ''}")


def big_scenario(n: int) -> dict[str, Any]:
    data = copy.deepcopy(BASE)
    sc = data["scenario"]
    sc["nodes"] = [
        {
            "id": f"N{i}",
            "type": "fixed_radio" if i % 2 else "mobile_radio",
            "position": [45 + i * 1e-6, 6.0, 100.0],
            "radio": "r",
        }
        for i in range(n)
    ]
    sc["interference"] = [
        {"id": f"J{i}", "frequency": 1e8, "bandwidth": 1e3, "power": 1} for i in range(n // 10)
    ]
    sc["radios"] = {"r": {}}
    return data


def scale_tests() -> None:
    for n in (1_000, 20_000, 100_000):
        d = big_scenario(n)
        timed(
            f"validate {n} nodes",
            lambda d=d: f"errors={len(validate_scenario_dict(d))}",
        )
        timed(f"parse {n} nodes", lambda d=d: f"nodes={len(parse_scenario_dict(d).nodes)}")

    d = big_scenario(20_000)
    for node in d["scenario"]["nodes"]:
        node["position"] = [1, 2, 3, 4]
        del node["radio"]
    timed("20k nodes x2 errors each", lambda: f"errors={len(validate_scenario_dict(d))}")

    d = big_scenario(20_000)
    with tempfile.TemporaryDirectory() as td:
        pj, py = Path(td) / "b.json", Path(td) / "b.yaml"
        pj.write_text(json.dumps(d), encoding="utf-8")
        py.write_text(yaml.safe_dump(d), encoding="utf-8")
        timed("load 20k json", lambda: f"{len(load_scenario(pj).nodes)}")
        timed("load 20k yaml", lambda: f"{len(load_scenario(py).nodes)}")
        timed("yaml == json (20k)", lambda: str(load_scenario(pj) == load_scenario(py)))


def hostile_inputs() -> None:
    deep: Any = []
    for _ in range(5000):
        deep = [deep]
    dd = copy.deepcopy(BASE)
    dd["scenario"]["nodes"][0]["position"] = deep
    timed(
        "deep nested position (5000)",
        lambda: f"errors={len(validate_scenario_dict(dd))}",
    )

    for name in ("NaN", "Infinity"):
        text = json.dumps(BASE).replace('"power": 50', f'"power": {name}')
        timed(
            f"JSON {name} power",
            lambda t=text: str(validate_scenario_dict(json.loads(t))),
        )

    seed_data = {"scenario": {**BASE["scenario"], "seed": 10**40}}
    timed(
        "huge int seed 10**40",
        lambda: f"errors={validate_scenario_dict(seed_data)} "
        f"parsed={parse_scenario_dict(seed_data).seed == 10**40}",
    )
    timed(
        "float 1e999 position",
        lambda: str(validate_scenario_dict(json.loads(json.dumps(BASE).replace("45.0", "1e999")))),
    )

    node = {"id": "节点", "type": "fixed_radio", "position": [0, 0], "radio": "r"}
    timed(
        "unicode / emoji ids",
        lambda: parse_scenario_dict({"scenario": {"name": "é😀", "nodes": [node]}}).nodes[0].id,
    )
    timed(
        "non-dict roots",
        lambda: str([validate_scenario_dict(x)[:1] for x in (None, 1, "s", [], [1])]),
    )
    timed(
        "scenario = null / list / int",
        lambda: str([validate_scenario_dict({"scenario": x}) for x in (None, [], 5)]),
    )
    timed(
        "radios with int key",
        lambda: str(
            validate_scenario_dict({"scenario": {"name": "n", "nodes": [], "radios": {1: {}}}})
        ),
    )
    bad_ref = {"id": "a", "type": "fixed_radio", "position": [0, 0], "radio": ["x"]}
    timed(
        "unhashable radio reference",
        lambda: str(
            validate_scenario_dict(
                {"scenario": {"name": "n", "nodes": [bad_ref], "radios": {"x": {}}}}
            )
        ),
    )


def yaml_and_file_edge_cases() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def write(name: str, text: str) -> Path:
            p = root / name
            p.write_text(text, encoding="utf-8")
            return p

        anchor = write("anchor.yaml", "scenario: &s\n  name: n\n  nodes: []\n  self: *s\n")
        pytag = write("tag.yaml", "scenario: !!python/object/apply:os.system ['echo pwned']\n")
        dup = write("dup.yaml", "scenario:\n  name: a\n  name: b\n  nodes: []\n")
        empty = write("empty.yaml", "")
        badutf = root / "u.json"
        badutf.write_bytes(b'{"scenario":\xff}')
        folder = root / "dir.yaml"
        folder.mkdir()

        timed("YAML recursive anchor", lambda: str(load_scenario(anchor).name))
        timed("YAML python tag (must be refused)", lambda: str(load_scenario(pytag)))
        timed("YAML duplicate key (must be refused)", lambda: str(load_scenario(dup)))
        timed("empty yaml", lambda: str(load_scenario(empty)))
        timed("invalid utf-8", lambda: str(load_scenario(badutf)))
        timed("path is a directory", lambda: str(load_scenario(folder)))


def _paths(obj: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    yield prefix
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _paths(v, (*prefix, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _paths(v, (*prefix, i))


def _walk(obj: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        obj = obj[key]
    return obj


def fuzz(iterations: int = 30_000, seed: int = 1234) -> None:
    rng = random.Random(seed)
    junk: list[Any] = [None, True, False, 0, -1, 1.5, "", "x", [], {}, [1], [1, 2, 3, 4],
                       {"a": 1}, 10**30, float("inf")]  # fmt: skip
    crashes = inconsistent = valid = 0
    for _ in range(iterations):
        d = copy.deepcopy(BASE)
        d["scenario"]["radios"] = {"radio_vhf_01": {}, "radio_vhf_02": {}}
        for _ in range(rng.randint(1, 4)):
            targets = [p for p in _paths(d) if p]
            if not targets:  # earlier mutations deleted everything
                break
            path = rng.choice(targets)
            try:
                parent = _walk(d, path[:-1])
                if rng.random() < 0.4:
                    del parent[path[-1]]
                else:
                    parent[path[-1]] = copy.deepcopy(rng.choice(junk))
            except (KeyError, IndexError):
                pass  # an earlier mutation already removed this path
        try:
            errors = validate_scenario_dict(d)
            try:
                parse_scenario_dict(d)
                ok = True
            except ScenarioValidationError as exc:
                ok = False
                if exc.errors != errors:
                    raise AssertionError(
                        "exception errors differ from validate_scenario_dict"
                    ) from exc
            if bool(errors) == ok:
                inconsistent += 1
            valid += ok
            if not all(isinstance(e, str) and e for e in errors):
                raise AssertionError("empty or non-string error message")
        except UNEXPECTED:
            crashes += 1
            if crashes < 4:
                traceback.print_exc(limit=3)
    print(
        f"fuzz: {iterations} mutations, valid={valid}, rejected={iterations - valid}, "
        f"crashes={crashes}, inconsistencies={inconsistent}"
    )

    d = big_scenario(2000)
    for node in d["scenario"]["nodes"]:
        node["position"] = [1]
    same = validate_scenario_dict(d) == validate_scenario_dict(copy.deepcopy(d))
    print(f"deterministic errors: {same}")


def main() -> None:
    scale_tests()
    hostile_inputs()
    yaml_and_file_edge_cases()
    fuzz()


if __name__ == "__main__":
    main()
