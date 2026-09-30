"""Contract for any GeodataProvider (fake or GeoServer-backed geodata-api).

    pytest tests/contract/test_geodata_provider_contract.py --geodata-impl=pkg.mod:Class
"""

from __future__ import annotations

import pytest

from libraries.domain.position import GeoPosition
from libraries.plugin_sdk.geodata import BBox, GeodataProvider, GeoJSONFile, LayerRef

A = GeoPosition(lat=45.0, lon=6.0)
B = GeoPosition(lat=45.1, lon=6.1)


def test_conforms_to_protocol(provider):
    assert isinstance(provider, GeodataProvider)


def test_elevation_at_returns_float(provider):
    assert isinstance(provider.elevation_at(A), float)


def test_elevation_profile_length_and_type(provider):
    p = provider.elevation_profile(A, B, samples=10)
    assert len(p) == 10 and all(isinstance(v, float) for v in p)


def test_elevation_profile_endpoints_match_point_queries(provider):
    p = provider.elevation_profile(A, B, samples=5)
    assert p[0] == pytest.approx(provider.elevation_at(A), abs=1.0)
    assert p[-1] == pytest.approx(provider.elevation_at(B), abs=1.0)


@pytest.mark.parametrize("n", [0, 1, -3])
def test_elevation_profile_rejects_too_few_samples(provider, n):
    with pytest.raises(ValueError):
        provider.elevation_profile(A, B, samples=n)


def test_publish_raster_returns_layer_ref(provider):
    ref = provider.publish_raster("dem", "file:///tmp/dem.tif")
    assert isinstance(ref, LayerRef) and ref.name == "dem" and ref.kind == "raster"


def test_publish_vector_returns_layer_ref(provider):
    ref = provider.publish_vector("roads", GeoJSONFile(path="roads.geojson"))
    assert isinstance(ref, LayerRef) and ref.name == "roads" and ref.kind == "vector"


def test_features_in_returns_list(provider):
    ref = provider.publish_vector("roads", GeoJSONFile(path="roads.geojson"))
    assert isinstance(provider.features_in(ref, BBox(44.9, 5.9, 45.2, 6.2)), list)


def test_tile_url_is_nonempty_string(provider):
    ref = provider.publish_raster("dem", "file:///tmp/dem.tif")
    url = provider.tile_url(ref)
    assert isinstance(url, str) and url


def test_set_style_returns_none(provider):
    ref = provider.publish_raster("dem", "file:///tmp/dem.tif")
    assert provider.set_style(ref, "<StyledLayerDescriptor/>") is None
