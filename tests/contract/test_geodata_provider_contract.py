"""Contract test for any GeodataProvider implementation (fake or real
GeoServer-backed geodata-api). Run with:
    pytest tests/contract/test_geodata_provider_contract.py --impl=tests.contract.fakes.flat_geodata_provider:FlatGeodataProvider
"""

from __future__ import annotations

import importlib

import pytest

from libraries.domain.position import GeoPosition
from libraries.plugin_sdk.geodata import GeodataProvider


def _load_impl(impl_path: str) -> GeodataProvider:
    module_path, _, cls_name = impl_path.partition(":")
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)()


@pytest.fixture
def provider(request) -> GeodataProvider:
    impl_path = request.config.getoption("--impl")
    return _load_impl(impl_path)


def test_conforms_to_protocol(provider: GeodataProvider) -> None:
    assert isinstance(provider, GeodataProvider)


def test_elevation_at_returns_float(provider: GeodataProvider) -> None:
    pos = GeoPosition(lat=45.0, lon=6.0)
    elevation = provider.elevation_at(pos)
    assert isinstance(elevation, float)


def test_elevation_profile_length_matches_samples(provider: GeodataProvider) -> None:
    a = GeoPosition(lat=45.0, lon=6.0)
    b = GeoPosition(lat=45.1, lon=6.1)
    profile = provider.elevation_profile(a, b, samples=10)
    assert len(profile) == 10


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--impl",
        action="store",
        default="tests.contract.fakes.flat_geodata_provider:FlatGeodataProvider",
        help="module:ClassName of the GeodataProvider implementation under test",
    )
