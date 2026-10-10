"""Exceptions raised by the scenario engine."""

from __future__ import annotations


class ScenarioError(Exception):
    """Base class for all scenario-engine errors."""


class ScenarioFileError(ScenarioError):
    """The scenario file could not be read or is not well-formed YAML/JSON."""


class ScenarioValidationError(ScenarioError):
    """The scenario content violates the schema or a scenario-level rule.

    ``errors`` holds one human-readable string per violation, each prefixed
    with the path of the offending field (e.g.
    ``scenario.nodes[1].position: array has 4 items, maximum 3``).
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors: list[str] = list(errors)
        count = len(self.errors)
        header = f"Scenario is invalid ({count} error{'s' if count != 1 else ''}):"
        super().__init__("\n".join([header, *(f"  - {e}" for e in self.errors)]))
