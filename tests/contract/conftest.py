"""Shared fixtures + per-contract `--<contract>-impl module:Class` options.

    pytest tests/contract --propagation-impl=services.propagation.free_space:FreeSpaceModel
    pytest tests/contract/test_geodata_provider_contract.py --geodata-impl=pkg.mod:Cls

Defaults point at the in-repo fakes so the templates run out of the box.
"""

from __future__ import annotations

import importlib

import pytest

DEFAULTS = {
    "propagation": "tests.contract.fakes.free_space_reference:FreeSpaceReferenceModel",
    "geodata": "tests.contract.fakes.flat_geodata_provider:FlatGeodataProvider",
    "waveform": "tests.contract.fakes.bpsk_codec:BpskCodec",
    "eventbus": "tests.contract.fakes.in_process_event_bus:InProcessEventBus",
    "engine": "tests.contract.fakes.simple_engine:SimpleEngine",
    "scheduler": "tests.contract.fakes.simple_engine:HeapScheduler",
}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("radiocom contracts")
    for key, default in DEFAULTS.items():
        group.addoption(
            f"--{key}-impl",
            action="store",
            default=default,
            help=f"module:ClassName of the {key} implementation under test",
        )


def load_impl(config: pytest.Config, key: str):
    path = config.getoption(f"--{key}-impl")
    module_path, sep, cls_name = path.partition(":")
    if not sep:
        raise pytest.UsageError(f"--{key}-impl must look like 'module:ClassName', got {path!r}")
    return getattr(importlib.import_module(module_path), cls_name)


@pytest.fixture
def model(request):
    return load_impl(request.config, "propagation")()


@pytest.fixture
def provider(request):
    return load_impl(request.config, "geodata")()


@pytest.fixture
def codec(request):
    return load_impl(request.config, "waveform")()


@pytest.fixture
def bus(request):
    return load_impl(request.config, "eventbus")()


@pytest.fixture
def engine(request):
    return load_impl(request.config, "engine")()


@pytest.fixture
def scheduler(request):
    return load_impl(request.config, "scheduler")()
