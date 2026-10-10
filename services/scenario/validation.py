"""Schema validation with precise, path-prefixed error messages."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

#: services/scenario/validation.py -> repo root is three levels up.
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "libraries" / "protocols" / "scenario.schema.json"
)


#: Scenario files are shallow (the schema is ~6 levels deep; a free-form radio
#: definition may nest a little more). Anything deeper is rejected up front,
#: because jsonschema / repr() can raise RecursionError on pathological depth
#: (observed on Python 3.13), which must never escape as a crash.
MAX_NESTING_DEPTH = 64


@lru_cache(maxsize=1)
def _validator() -> Draft7Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft7Validator(schema)


def format_path(parts: Iterable[Any]) -> str:
    """``['scenario', 'nodes', 1, 'position']`` -> ``scenario.nodes[1].position``."""
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "(root)"


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _quoted(values: Iterable[Any]) -> str:
    return ", ".join(repr(v) for v in values)


def _describe(error: ValidationError) -> str:
    kind = error.validator
    if kind == "required":
        instance = error.instance if isinstance(error.instance, dict) else {}
        missing = [k for k in error.validator_value if k not in instance]
        return f"missing required field{'s' if len(missing) != 1 else ''} {_quoted(missing)}"
    if kind == "enum":
        return (
            f"{error.instance!r} is not one of the allowed values: "
            f"{_quoted(error.validator_value)}"
        )
    if kind in ("minItems", "maxItems") and isinstance(error.instance, list):
        n = len(error.instance)
        bound = "minimum" if kind == "minItems" else "maximum"
        return f"array has {n} item{'s' if n != 1 else ''}, {bound} {error.validator_value}"
    if kind == "type":
        expected = error.validator_value
        expected_s = " or ".join(expected) if isinstance(expected, list) else str(expected)
        return f"expected {expected_s}, got {_json_type_name(error.instance)}"
    return error.message


def _sort_key(error: ValidationError) -> tuple[Any, ...]:
    return tuple((0, p, "") if isinstance(p, int) else (1, 0, str(p)) for p in error.absolute_path)


def _schema_errors(data: Any) -> list[str]:
    errors = sorted(_validator().iter_errors(data), key=_sort_key)
    messages: list[str] = []
    for err in errors:
        msg = f"{format_path(err.absolute_path)}: {_describe(err)}"
        if msg not in messages:  # 'required' yields one error per missing key
            messages.append(msg)
    return messages


def _depth_errors(data: Any) -> list[str]:
    """Return one error if ``data`` nests deeper than ``MAX_NESTING_DEPTH``.

    Iterative, so it is safe on arbitrarily deep input.
    """
    stack: list[tuple[tuple[Any, ...], Any]] = [((), data)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            children = [((*path, k), v) for k, v in value.items()]
        elif isinstance(value, list):
            children = [((*path, i), v) for i, v in enumerate(value)]
        else:
            continue
        if len(path) >= MAX_NESTING_DEPTH:
            shown = format_path(path[:8]) + ("…" if len(path) > 8 else "")
            return [f"{shown}: nesting deeper than {MAX_NESTING_DEPTH} levels"]
        stack.extend(children)
    return []


def _non_finite_errors(data: Any) -> list[str]:
    """Reject NaN/Infinity anywhere (JSON forbids them; YAML ``.nan``/``.inf``
    and out-of-range literals like ``1e999`` can produce them). Iterative, so
    deeply nested input cannot hit the recursion limit."""
    errors: list[str] = []
    stack: list[tuple[tuple[Any, ...], Any]] = [((), data)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{format_path(path)}: number must be finite, got {value!r}")
        elif isinstance(value, dict):
            stack.extend(((*path, k), v) for k, v in value.items())
        elif isinstance(value, list):
            stack.extend(((*path, i), v) for i, v in enumerate(value))
    return sorted(errors)


def _extension_errors(data: dict[str, Any]) -> list[str]:
    """Checks for the two non-schema conventions (scenario_version, radios).

    Only called when ``data["scenario"]`` is a dict. Defensive about the shape
    of anything the schema itself already reports on.
    """
    scenario = data["scenario"]
    errors: list[str] = []

    if "scenario_version" in scenario:
        v = scenario["scenario_version"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            errors.append(f"scenario.scenario_version: expected a positive integer, got {v!r}")

    if "radios" not in scenario:
        return errors  # no catalog: node.radio stays an opaque string

    radios = scenario["radios"]
    if not isinstance(radios, dict):
        errors.append(f"scenario.radios: expected object, got {_json_type_name(radios)}")
        return errors
    for name, definition in radios.items():
        if not isinstance(name, str):
            errors.append(f"scenario.radios: radio name {name!r} must be a string")
        elif not isinstance(definition, dict):
            errors.append(
                f"scenario.radios.{name}: expected object, " f"got {_json_type_name(definition)}"
            )

    nodes = scenario.get("nodes")
    if isinstance(nodes, list):
        known = sorted(str(k) for k in radios)
        for i, node in enumerate(nodes):
            if not isinstance(node, dict) or not isinstance(node.get("radio"), str):
                continue  # already reported by the schema pass
            if node["radio"] not in radios:
                node_id = node.get("id", f"#{i}")
                errors.append(
                    f"scenario.nodes[{i}].radio: node {node_id!r} references radio "
                    f"{node['radio']!r}, which is not defined in scenario.radios "
                    f"(defined: {_quoted(known) or 'none'})"
                )
    return errors


def validate_scenario_dict(data: Any) -> list[str]:
    """Validate a raw scenario dict. Returns all errors; an empty list = valid.

    Runs the frozen JSON Schema (draft-07) first, then the scenario-level
    conventions (``scenario_version``, ``radios`` resolution).
    """
    depth_errors = _depth_errors(data)
    if depth_errors:  # do not hand pathological input to jsonschema
        return depth_errors
    errors = _schema_errors(data)
    errors.extend(_non_finite_errors(data))
    if isinstance(data, dict) and isinstance(data.get("scenario"), dict):
        errors.extend(_extension_errors(data))
    return errors
