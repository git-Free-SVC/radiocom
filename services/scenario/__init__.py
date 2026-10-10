"""Scenario Engine: parse, validate and version RADIOCOM scenario files.

Pure data package -- no I/O beyond reading the scenario file, no dependency on
the Simulation Core or on ``libraries.domain``.

Public API:

* :func:`load_scenario` -- file path -> :class:`Scenario`
* :func:`parse_scenario_dict` -- raw dict -> :class:`Scenario`
* :func:`validate_scenario_dict` -- raw dict -> ``list[str]`` of errors (empty = valid)
"""

from .errors import ScenarioError, ScenarioFileError, ScenarioValidationError
from .loader import load_scenario, parse_scenario_dict
from .models import (
    DEFAULT_SCENARIO_VERSION,
    Environment,
    InterferenceSource,
    Node,
    RadioDefinition,
    Scenario,
    TerrainConfig,
    VectorLayerConfig,
)
from .validation import validate_scenario_dict

__all__ = [
    "DEFAULT_SCENARIO_VERSION",
    "Environment",
    "InterferenceSource",
    "Node",
    "RadioDefinition",
    "Scenario",
    "ScenarioError",
    "ScenarioFileError",
    "ScenarioValidationError",
    "TerrainConfig",
    "VectorLayerConfig",
    "load_scenario",
    "parse_scenario_dict",
    "validate_scenario_dict",
]
