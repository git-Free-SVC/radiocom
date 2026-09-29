"""GeodataProvider interface. Frozen after Wave 0 — see docs/adr/ADR-000.
Real implementation: services/geodata-api (backed by GeoServer, §13a).
In-memory fake: tests/contract/fakes/flat_geodata_provider.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union, runtime_checkable

from libraries.domain.position import GeoPosition


@dataclass(frozen=True, slots=True)
class LayerRef:
    name: str
    kind: str  # "raster" | "vector"


@dataclass(frozen=True, slots=True)
class PostGISTable:
    table: str
    schema: str = "public"


@dataclass(frozen=True, slots=True)
class GeoJSONFile:
    path: str


@dataclass(frozen=True, slots=True)
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


@dataclass(frozen=True, slots=True)
class Feature:
    geometry: dict  # GeoJSON geometry
    properties: dict


@runtime_checkable
class GeodataProvider(Protocol):
    def publish_raster(self, name: str, path_or_uri: str, srs: str = "EPSG:4326") -> LayerRef: ...

    def publish_vector(self, name: str, source: Union[PostGISTable, GeoJSONFile]) -> LayerRef: ...

    def set_style(self, layer: LayerRef, sld: str) -> None: ...

    def elevation_at(self, pos: GeoPosition) -> float:
        """Single WCS elevation query, meters."""
        ...

    def elevation_profile(self, a: GeoPosition, b: GeoPosition, samples: int) -> list[float]:
        """LOS elevation profile between two points, meters, `samples` points."""
        ...

    def features_in(self, layer: LayerRef, bbox: BBox) -> list[Feature]: ...

    def tile_url(self, layer: LayerRef, style: str | None = None) -> str:
        """WMS/WMTS tile URL template for the UI basemap."""
        ...
