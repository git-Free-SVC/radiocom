"""Typed, immutable models mirroring the frozen scenario schema.

These models are deliberately independent of ``libraries.domain``: they
describe *scenario file data*, not simulation-runtime objects. Mapping them
onto domain types is a later integration concern.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Version assumed when a scenario omits ``scenario_version`` (the schema's
#: current implicit shape). NOT part of the frozen schema -- see README/PR.
DEFAULT_SCENARIO_VERSION = 1

NodeType = Literal["fixed_radio", "mobile_radio"]


class _ScenarioModel(BaseModel):
    # The frozen schema never sets additionalProperties=false, so unknown
    # keys are legal; we ignore (drop) them rather than reject them.
    model_config = ConfigDict(frozen=True, extra="ignore")


class TerrainConfig(_ScenarioModel):
    """``environment.terrain`` -- validated as data only, never resolved."""

    layer_name: str
    source: str
    srs: str = "EPSG:4326"
    style: str | None = None


class VectorLayerConfig(_ScenarioModel):
    """One entry of ``environment.vector_layers``."""

    layer_name: str
    source: str
    style: str | None = None


class Environment(_ScenarioModel):
    terrain: TerrainConfig | None = None
    vector_layers: tuple[VectorLayerConfig, ...] = ()


class Node(_ScenarioModel):
    """A radio node in the scenario.

    ``position`` is ``(lat, lon)`` or ``(lat, lon, alt_m)``: latitude first,
    then longitude (both degrees), then optional altitude in metres. This
    follows the ``GeoPosition`` convention; the schema itself only constrains
    the array length (2 or 3 numbers).

    ``position`` is required for *every* node. For a ``mobile_radio`` it means
    the initial/starting position; this model attaches no further semantics
    (e.g. it does not assume ``route`` overrides it).

    ``route`` and ``radio`` are opaque string references; resolving them is
    out of scope (see ``Scenario.radios`` for the optional radio catalog).
    """

    id: str
    type: NodeType
    position: tuple[float, ...]
    radio: str
    route: str | None = None

    @field_validator("position")
    @classmethod
    def _check_position_length(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if not 2 <= len(v) <= 3:
            raise ValueError("position must have 2 or 3 elements")
        return v

    @property
    def lat(self) -> float:
        return self.position[0]

    @property
    def lon(self) -> float:
        return self.position[1]

    @property
    def alt_m(self) -> float | None:
        """Altitude in metres, or ``None`` if the position has no 3rd element."""
        return self.position[2] if len(self.position) == 3 else None


class InterferenceSource(_ScenarioModel):
    """An interference entry. The schema does not state units; the example
    scenario suggests frequency/bandwidth in Hz. ``power`` units are
    unspecified and are carried through untouched."""

    id: str
    frequency: float
    bandwidth: float
    power: float


class RadioDefinition(_ScenarioModel):
    """An entry of the optional ``scenario.radios`` catalog.

    The catalog is NOT in the frozen schema, so its parameter names are not
    defined; all keys are carried through untouched via ``params``.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class Scenario(_ScenarioModel):
    """A validated scenario (the contents of the top-level ``scenario`` key)."""

    name: str
    seed: int = 0
    #: Optional, non-schema key. Absent -> ``DEFAULT_SCENARIO_VERSION``.
    scenario_version: int = DEFAULT_SCENARIO_VERSION
    environment: Environment = Field(default_factory=Environment)
    nodes: tuple[Node, ...]
    interference: tuple[InterferenceSource, ...] = ()
    #: Optional, non-schema radio catalog (name -> definition). ``None`` means
    #: no catalog was supplied, so ``Node.radio`` strings are opaque.
    radios: dict[str, RadioDefinition] | None = None

    def radio_for(self, node: Node) -> RadioDefinition | None:
        """Return the catalog entry for ``node.radio``, or ``None`` if the
        scenario has no catalog."""
        if self.radios is None:
            return None
        return self.radios[node.radio]
