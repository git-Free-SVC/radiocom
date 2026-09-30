"""Flat-earth fake GeodataProvider: zero elevation everywhere, no real
GeoServer needed. Used by Wave-1 World Engine agent until Wave-2's real
geodata-api (K) is wired in by the Integration Agent."""

from __future__ import annotations

from libraries.domain.position import GeoPosition
from libraries.plugin_sdk.geodata import BBox, Feature, LayerRef


class FlatGeodataProvider:
    def __init__(self) -> None:
        self._layers: dict[str, LayerRef] = {}

    def publish_raster(self, name: str, path_or_uri: str, srs: str = "EPSG:4326") -> LayerRef:
        ref = LayerRef(name=name, kind="raster")
        self._layers[name] = ref
        return ref

    def publish_vector(self, name: str, source) -> LayerRef:
        ref = LayerRef(name=name, kind="vector")
        self._layers[name] = ref
        return ref

    def set_style(self, layer: LayerRef, sld: str) -> None:
        pass  # no-op

    def elevation_at(self, pos: GeoPosition) -> float:
        return 0.0

    def elevation_profile(self, a: GeoPosition, b: GeoPosition, samples: int) -> list[float]:
        if samples < 2:
            raise ValueError("samples must be >= 2")
        return [0.0] * samples

    def features_in(self, layer: LayerRef, bbox: BBox) -> list[Feature]:
        return []

    def tile_url(self, layer: LayerRef, style: str | None = None) -> str:
        return f"about:blank#{layer.name}"
