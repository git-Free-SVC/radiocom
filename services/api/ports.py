"""API-local ports (typing.Protocol). The API package depends only on these.

The frozen interfaces from libraries.plugin_sdk (EventBus, GeodataProvider,
SimulationEngine) are referenced but never modified. SimulationRegistryPort
extends CorePort because radios and links belong to a simulation and
create_app takes the five ports named in the task prompt (§7): scenario,
registry, bus, clock, geodata — the registry doubles as the radio/link store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from libraries.plugin_sdk.geodata import GeodataProvider, LayerRef
from libraries.plugin_sdk.simulation import SimulationEngine


@runtime_checkable
class ScenarioPort(Protocol):
    """Read/write access to stored scenarios."""

    def list_scenarios(self) -> list[dict[str, Any]]:
        """Summaries [{id, name}, ...] in creation order."""
        ...

    def create_scenario(self, body: dict[str, Any]) -> dict[str, Any]:
        """Validate-free storage: schema validation happens in the route.
        Returns {id, scenario, created_at}."""
        ...

    def get_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        """The stored record, or None for an unknown id."""
        ...


@runtime_checkable
class ClockPort(Protocol):
    """Injected deterministic clock — no wall time anywhere in services/api."""

    def now(self) -> datetime: ...


@runtime_checkable
class CorePort(Protocol):
    """Radio/link operations needed by POST|PATCH /radios, GET /links/{a}/{b}
    and the telemetry WebSocket snapshots."""

    def add_radio(self, simulation_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Build frozen domain types from a validated body (ValueError from a
        domain constructor is the API's 422 input path) and store the radio."""
        ...

    def update_radio(self, radio_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a whole-value replacement patch; None for an unknown radio."""
        ...

    def get_link(self, a: str, b: str) -> dict[str, Any] | None:
        """Link payload (link_state_changed keys); direction-insensitive;
        None when no link exists between the two radios."""
        ...

    def radios(self, simulation_id: str) -> list[dict[str, Any]]:
        """Radio payloads of one simulation (WS snapshot source)."""
        ...

    def links(self, simulation_id: str) -> list[dict[str, Any]]:
        """Link payloads of one simulation (WS snapshot source)."""
        ...


@runtime_checkable
class SimulationRegistryPort(CorePort, Protocol):
    """One SimulationEngine per /simulations/{id} (SimulationEngine itself has
    no id field) plus the radio/link store of §4 of the task prompt."""

    def create(self, scenario_id: str) -> str:
        """Register a fresh engine (state "new"); returns sim_000N."""
        ...

    def get(self, simulation_id: str) -> SimulationEngine | None: ...

    def exists(self, simulation_id: str) -> bool: ...

    def status(self, simulation_id: str) -> str:
        """LOADED | RUNNING | PAUSED | new; ApiError(404) when unknown."""
        ...

    def scenario_id(self, simulation_id: str) -> str:
        """The scenario a simulation was created from; ApiError(404) unknown."""
        ...


@runtime_checkable
class GeodataPort(GeodataProvider, Protocol):
    """Frozen GeodataProvider plus list_layers for GET /geodata/layers (the
    frozen Protocol has no listing method; the mock and the future GeoServer
    adapter both expose one)."""

    def list_layers(self) -> list[LayerRef]: ...
