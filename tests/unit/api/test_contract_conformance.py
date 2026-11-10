"""Contract conformance (task prompt §6): two independent, machine-verified checks
plus drift-proofing negatives.

Check 1 — route parity, BOTH directions: the frozen openapi.yaml operation set
versus the FastAPI app's registered routes (and the §17 WebSocket paths).
Check 2 — status parity: YAML success codes versus the handlers' declared
status codes AND versus the runtime responses of a full happy chain.
Check 3 — body validation: exact key-set equality for every response
(additionalProperties: false + complete required), scenario requests against
the frozen scenario.schema.json, and the spec-silent premise canary.
Negative tests feed deliberately doctored inputs to the same helpers to prove
the checks can actually fail (never mutating real contract files).
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
import yaml
from conftest import (  # type: ignore[import-not-found]
    REPOSITORY_ROOT,
    VALID_RADIO_BODY,
    VALID_SCENARIO_BODY,
    get,
    patch,
    post,
)
from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute

from services.api.schemas import (
    LINK_EVENT_SCHEMA_PATH,
    RESPONSE_SCHEMAS,
    SCENARIO_SCHEMA_PATH,
    load_frozen_schema,
)

YAML_PATH = REPOSITORY_ROOT / "libraries" / "protocols" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

# Architecture doc §17 lists exactly these two WebSocket paths (parameter
# spelled {id}); OpenAPI 3.0.3 cannot represent them at all.
SECTION_17_WS_PATHS = {"/ws/simulations/{id}/telemetry", "/spectrum"}

EXPECTED_RESPONSE_KEYS: dict[str, set[str]] = {
    "GET /scenarios": {"scenarios"},
    "POST /scenarios": {"id", "scenario", "created_at"},
    "GET /scenarios/{id}": {"id", "scenario", "created_at"},
    "POST /simulations": {"id", "scenario_id", "status"},
    "POST /simulations/{id}/start": {"id", "scenario_id", "status"},
    "POST /simulations/{id}/pause": {"id", "scenario_id", "status"},
    "POST /simulations/{id}/resume": {"id", "scenario_id", "status"},
    "POST /simulations/{id}/reset": {"id", "scenario_id", "status"},
    "POST /radios": {
        "id",
        "simulation_id",
        "frequency",
        "transmitter",
        "receiver",
        "antenna",
        "position",
    },
    "PATCH /radios/{id}": {
        "id",
        "simulation_id",
        "frequency",
        "transmitter",
        "receiver",
        "antenna",
        "position",
    },
    "GET /links/{a}/{b}": {"tx_id", "rx_id", "snr_db", "margin_db", "quality", "time_s"},
    "GET /geodata/layers": {"layers"},
    "POST /geodata/layers": {"name", "kind"},
    "GET /geodata/elevation": {"lat", "lon", "elevation_m"},
    "GET /geodata/elevation/profile": {"profile_m"},
}


# --------------------------------------------------------------------------------------
# Contract parsers (reusable by the Integration Agent)
# --------------------------------------------------------------------------------------


def load_yaml_contract() -> dict[str, Any]:
    with YAML_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def yaml_operations(spec: dict[str, Any]) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                operations.add((method.upper(), path))
    return operations


def yaml_success_statuses(spec: dict[str, Any]) -> dict[tuple[str, str], int]:
    statuses: dict[tuple[str, str], int] = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            codes = [int(code) for code in operation.get("responses", {})]
            success = [code for code in codes if 200 <= code < 300]
            assert success, f"{method.upper()} {path} declares no 2xx response"
            statuses[(method.upper(), path)] = success[0]
    return statuses


def app_operations(app: Any) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }


def app_declared_statuses(app: Any) -> dict[tuple[str, str], int]:
    statuses: dict[tuple[str, str], int] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            statuses[(method, route.path)] = int(route.status_code or 200)
    return statuses


def app_ws_paths(app: Any) -> set[str]:
    return {route.path for route in app.routes if isinstance(route, WebSocketRoute)}


def compare_routes(
    expected: set[tuple[str, str]], actual: set[tuple[str, str]]
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(missing_from_actual, extra_in_actual) — used in both directions."""
    return expected - actual, actual - expected


def compare_statuses(
    expected: dict[tuple[str, str], int], actual: dict[tuple[str, str], int]
) -> list[tuple[str, int, int]]:
    """[(route_key, expected_code, actual_code), ...] for shared routes that differ."""
    mismatches: list[tuple[str, int, int]] = []
    for route in sorted(expected):
        if route in actual and expected[route] != actual[route]:
            mismatches.append((f"{route[0]} {route[1]}", expected[route], actual[route]))
    return mismatches


# --------------------------------------------------------------------------------------
# Check 1: route parity (both directions)
# --------------------------------------------------------------------------------------


def test_route_parity_yaml_to_app(app) -> None:
    spec = load_yaml_contract()
    missing, _extra = compare_routes(yaml_operations(spec), app_operations(app))
    assert missing == set(), f"YAML operations missing from the app: {sorted(missing)}"


def test_route_parity_app_to_yaml(app) -> None:
    spec = load_yaml_contract()
    _missing, extra = compare_routes(yaml_operations(spec), app_operations(app))
    assert extra == set(), f"App routes absent from the frozen YAML: {sorted(extra)}"


def test_ws_paths_match_architecture_section_17(app) -> None:
    assert app_ws_paths(app) == SECTION_17_WS_PATHS


def test_every_yaml_operation_has_a_declared_response_schema() -> None:
    spec = load_yaml_contract()
    yaml_keys = {f"{method} {path}" for method, path in yaml_operations(spec)}
    assert set(RESPONSE_SCHEMAS) == yaml_keys
    assert set(RESPONSE_SCHEMAS) == set(EXPECTED_RESPONSE_KEYS)


# --------------------------------------------------------------------------------------
# Check 2: status parity (declared handler codes and runtime responses)
# --------------------------------------------------------------------------------------


def test_status_parity_declared_handlers_vs_yaml(app) -> None:
    spec = load_yaml_contract()
    mismatches = compare_statuses(yaml_success_statuses(spec), app_declared_statuses(app))
    assert mismatches == [], mismatches


def _run_happy_chain(app: Any) -> dict[str, Any]:
    """Execute every YAML operation once; returns route_key -> HttpResponse."""
    responses: dict[str, Any] = {}
    responses["GET /scenarios"] = get(app, "/scenarios")

    responses["POST /scenarios"] = post(app, "/scenarios", json=VALID_SCENARIO_BODY)
    scenario_id = responses["POST /scenarios"].json()["id"]
    responses["GET /scenarios/{id}"] = get(app, f"/scenarios/{scenario_id}")

    responses["POST /simulations"] = post(app, "/simulations", json={"scenario_id": scenario_id})
    simulation_id = responses["POST /simulations"].json()["id"]
    responses["POST /simulations/{id}/start"] = post(app, f"/simulations/{simulation_id}/start")
    responses["POST /simulations/{id}/pause"] = post(app, f"/simulations/{simulation_id}/pause")
    responses["POST /simulations/{id}/resume"] = post(app, f"/simulations/{simulation_id}/resume")
    responses["POST /simulations/{id}/reset"] = post(app, f"/simulations/{simulation_id}/reset")

    responses["POST /radios"] = post(
        app, "/radios", json={**VALID_RADIO_BODY, "simulation_id": simulation_id}
    )
    first_radio = responses["POST /radios"].json()["id"]
    second = post(app, "/radios", json={**VALID_RADIO_BODY, "simulation_id": simulation_id})
    assert second.status == 201, second.text
    second_radio = second.json()["id"]

    responses["PATCH /radios/{id}"] = patch(
        app,
        f"/radios/{first_radio}",
        json={"position": {"lat": 48.86, "lon": 2.36, "alt_m": 20.0}},
    )
    responses["GET /links/{a}/{b}"] = get(app, f"/links/{first_radio}/{second_radio}")

    responses["GET /geodata/layers"] = get(app, "/geodata/layers")
    responses["POST /geodata/layers"] = post(
        app,
        "/geodata/layers",
        json={"name": "conformance", "kind": "vector", "path_or_uri": "data/x.geojson"},
    )
    responses["GET /geodata/elevation"] = get(app, "/geodata/elevation?lat=48.85&lon=2.35")
    responses["GET /geodata/elevation/profile"] = get(
        app,
        "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.86&lon2=2.36&samples=5",
    )
    return responses


def test_runtime_success_statuses_match_yaml(app) -> None:
    responses = _run_happy_chain(app)
    expected = yaml_success_statuses(load_yaml_contract())
    assert set(responses) == {f"{method} {path}" for method, path in expected}
    for route_key, response in responses.items():
        assert response.status == expected[_split_route(route_key)], (
            route_key,
            response.status,
            response.text,
        )


def _split_route(route_key: str) -> tuple[str, str]:
    method, _, path = route_key.partition(" ")
    return method, path


# --------------------------------------------------------------------------------------
# Check 3: response body key sets + value schemas
# --------------------------------------------------------------------------------------


def test_response_key_sets_exact_and_schema_valid(app) -> None:
    responses = _run_happy_chain(app)
    for route_key, response in responses.items():
        assert response.status < 300, (route_key, response.text)
        body = response.json()
        expected_keys = EXPECTED_RESPONSE_KEYS[route_key]
        assert set(body.keys()) == expected_keys, (route_key, sorted(body))
        jsonschema.validate(body, RESPONSE_SCHEMAS[route_key])


def test_scenario_record_inner_keys_are_the_frozen_property_set(app) -> None:
    response = post(app, "/scenarios", json=VALID_SCENARIO_BODY)
    scenario = response.json()["scenario"]
    assert set(scenario.keys()) <= {"name", "seed", "environment", "interference", "nodes"}


def test_request_bodies_validated_against_declared_schemas(app) -> None:
    """Extra key on a no-spec request body -> 422 with the offending key named."""
    response = post(app, "/simulations", json={"scenario_id": "scn_0001", "bogus": 1})
    assert response.status == 422, response.text
    assert "bogus" in response.text


# --------------------------------------------------------------------------------------
# Spec-silent premise canary (why schemas.py exists at all)
# --------------------------------------------------------------------------------------


def test_frozen_yaml_declares_no_bodies_no_schemas_no_errors() -> None:
    """If the frozen contract ever grows request/response schemas, this canary
    fails and schemas.py must be re-pointed at the contract (§6)."""
    spec = load_yaml_contract()
    assert "components" not in spec
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            assert "requestBody" not in operation, (method, path)
            responses = operation["responses"]
            assert set(responses) <= {"200", "201"}, (method, path, set(responses))
            for response in responses.values():
                assert set(response.keys()) == {"description"}, (method, path, response)


def test_frozen_yaml_is_valid_openapi() -> None:
    openapi_spec_validator = pytest.importorskip("openapi_spec_validator")
    spec = load_yaml_contract()
    openapi_spec_validator.validate(spec)


# --------------------------------------------------------------------------------------
# Drift-proofing negatives (doctored inputs, real files untouched)
# --------------------------------------------------------------------------------------


def test_negative_parity_detects_renamed_path() -> None:
    yaml_ops = {("GET", "/scenarios"), ("POST", "/scenarios")}
    doctored_yaml = {("GET", "/scenariosRenamed"), ("POST", "/scenarios")}
    # doctored contract vs the (here: real) served set:
    missing, extra = compare_routes(doctored_yaml, yaml_ops)
    assert missing == {("GET", "/scenariosRenamed")}  # contract op not served
    assert extra == {("GET", "/scenarios")}  # served op not in contract


def test_negative_parity_detects_dropped_operation() -> None:
    yaml_ops = {("POST", "/radios"), ("GET", "/scenarios")}
    doctored_yaml = {("GET", "/scenarios")}  # someone dropped POST /radios
    missing, extra = compare_routes(doctored_yaml, yaml_ops)
    assert missing == set()
    assert extra == {("POST", "/radios")}


def test_negative_parity_detects_wrong_method() -> None:
    yaml_ops = {("PUT", "/scenarios")}  # POST -> PUT typo
    app_ops = {("POST", "/scenarios")}
    missing, extra = compare_routes(yaml_ops, app_ops)
    assert missing == {("PUT", "/scenarios")}
    assert extra == {("POST", "/scenarios")}


def test_negative_status_parity_detects_doctored_status(app) -> None:
    """A doctored expected status (200 instead of the contract's 201) must be
    reported against the app's declared status — same helper as the positive
    check, fed deliberately wrong input."""
    spec = load_yaml_contract()
    doctored = yaml_success_statuses(spec)
    doctored[("POST", "/scenarios")] = 200  # contract actually says 201
    mismatches = compare_statuses(doctored, app_declared_statuses(app))
    assert len(mismatches) == 1, mismatches
    route, expected_code, actual_code = mismatches[0]
    assert (route, expected_code, actual_code) == ("POST /scenarios", 200, 201)


def test_negative_response_schema_detects_renamed_field(app) -> None:
    responses = _run_happy_chain(app)
    body = responses["POST /scenarios"].json()
    doctored = dict(body)
    doctored["identifier"] = doctored.pop("id")  # renamed field
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doctored, RESPONSE_SCHEMAS["POST /scenarios"])


def test_negative_response_schema_detects_missing_field(app) -> None:
    responses = _run_happy_chain(app)
    body = dict(responses["POST /radios"].json())
    body.pop("position")  # missing field
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(body, RESPONSE_SCHEMAS["POST /radios"])


def test_negative_response_schema_detects_extra_field(app) -> None:
    responses = _run_happy_chain(app)
    body = dict(responses["GET /links/{a}/{b}"].json())
    body["extra_metric"] = 1.0  # extra field
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(body, RESPONSE_SCHEMAS["GET /links/{a}/{b}"])


def test_negative_frozen_scenario_schema_rejects_doctored_instance() -> None:
    frozen = load_frozen_schema(SCENARIO_SCHEMA_PATH)
    doctored = {"scenario": {"name": "x"}}  # nodes removed
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doctored, frozen)


def test_link_event_schema_is_frozen_and_six_keys() -> None:
    link_schema = load_frozen_schema(LINK_EVENT_SCHEMA_PATH)
    assert set(link_schema["required"]) == {
        "tx_id",
        "rx_id",
        "snr_db",
        "margin_db",
        "quality",
        "time_s",
    }


def test_helpers_are_reusable_without_app() -> None:
    """Pure functions usable by the Integration Agent in CI, no app needed."""
    spec = load_yaml_contract()
    operations = yaml_operations(spec)
    statuses = yaml_success_statuses(spec)
    assert len(operations) == 15
    assert set(statuses) == operations
    assert statuses[("POST", "/scenarios")] == 201
    assert statuses[("GET", "/scenarios")] == 200
