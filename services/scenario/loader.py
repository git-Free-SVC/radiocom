"""Load scenario files (YAML or JSON) into validated :class:`Scenario` objects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from .errors import ScenarioFileError, ScenarioValidationError
from .models import Scenario
from .validation import format_path, validate_scenario_dict

YAML_SUFFIXES = frozenset({".yaml", ".yml"})
JSON_SUFFIXES = frozenset({".json"})


# libYAML-backed loader when available (~10x faster on large scenarios); the
# resolver/constructor customisations below work identically on either base.
# _BaseLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Use the pure-Python loader for scenario YAML. The C-backed CSafeLoader can
# overflow the native stack on deeply nested input on Windows, terminating the
# process before _read_data can translate RecursionError into ScenarioFileError.
_BaseLoader = yaml.SafeLoader


class _DuplicateKeyError(ValueError):
    """A mapping contains the same key twice (silently last-wins otherwise)."""


class _ScenarioYamlLoader(_BaseLoader):  # type: ignore[misc, valid-type]
    """SafeLoader that also reads ``145.5e6`` / ``25e3`` as floats.

    PyYAML implements YAML 1.1, whose float rule demands a dot *and* a signed
    exponent, so these common spellings would load as *strings* and then fail
    schema validation (or worse, differ from the same JSON file).
    """


def _construct_unique_mapping(loader: Any, node: yaml.MappingNode) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in result:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_ScenarioYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)

_EXTRA_FLOAT = re.compile(
    r"""^(?:[-+]?(?:[0-9][0-9_]*)[eE][-+]?[0-9]+
        |[-+]?(?:[0-9][0-9_]*)\.[0-9_]*[eE][-+]?[0-9]+)$""",
    re.VERBOSE,
)
_ScenarioYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float", _EXTRA_FLOAT, list("-+0123456789")
)


def _json_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _read_data(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix not in YAML_SUFFIXES | JSON_SUFFIXES:
        raise ScenarioFileError(
            f"{path}: unsupported file extension {path.suffix!r} " "(expected .yaml, .yml or .json)"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")  # tolerate Windows BOM
    except UnicodeDecodeError as exc:
        raise ScenarioFileError(f"{path}: file is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise ScenarioFileError(f"{path}: cannot read file: {exc}") from exc
    try:
        if suffix in JSON_SUFFIXES:
            return json.loads(text, object_pairs_hook=_json_unique_object)
        return yaml.load(text, Loader=_ScenarioYamlLoader)
    except (json.JSONDecodeError, yaml.YAMLError, _DuplicateKeyError) as exc:
        raise ScenarioFileError(f"{path}: malformed {suffix[1:].upper()}: {exc}") from exc
    except RecursionError as exc:  # parser limit hit on pathological nesting
        raise ScenarioFileError(
            f"{path}: {suffix[1:].upper()} nesting is too deep to parse"
        ) from exc


def parse_scenario_dict(data: Any) -> Scenario:
    """Validate ``data`` and build a :class:`Scenario`.

    Raises :class:`ScenarioValidationError` listing every violation.
    """
    errors = validate_scenario_dict(data)
    if errors:
        raise ScenarioValidationError(errors)
    try:
        return Scenario.model_validate(data["scenario"])
    except PydanticValidationError as exc:  # pragma: no cover - schema should prevent this
        raise ScenarioValidationError(
            [f"{format_path(('scenario', *e['loc']))}: {e['msg']}" for e in exc.errors()]
        ) from exc


def load_scenario(path: str | Path) -> Scenario:
    """Read a ``.yaml``/``.yml``/``.json`` scenario file and return a :class:`Scenario`.

    Raises :class:`ScenarioFileError` (unreadable / malformed) or
    :class:`ScenarioValidationError` (schema or scenario-level violations).
    """
    return parse_scenario_dict(_read_data(Path(path)))
