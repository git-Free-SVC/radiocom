"""REST behaviour of the §17 routes: one success test per YAML operation
(15), the full error matrix (404 / 409 / 413 / 422 / 500), and the engine
called-exactly-once assertions from the task prompt (§9).

Every error response is asserted through assert_error / assert_error_detail_list,
which enforce the single assumed envelope {"detail": ...} everywhere.
"""

from __future__ import annotations

import json as jsonlib
import math

import jsonschema
import pytest
from conftest import (  # type: ignore[import-not-found]
    VALID_RADIO_BODY,
    VALID_SCENARIO_BODY,
    assert_error,
    assert_error_detail_list,
    create_radio,
    create_scenario,
    create_simulation,
    get,
    patch,
    post,
    request,
)

from services.api import MAX_BODY_BYTES

RADIO_KEYS = {
    "id",
    "simulation_id",
    "frequency",
    "transmitter",
    "receiver",
    "antenna",
    "position",
}


# --------------------------------------------------------------------------------------
# GET /scenarios + POST /scenarios + GET /scenarios/{id}
# --------------------------------------------------------------------------------------


def test_get_scenarios_empty_store(app) -> None:
    response = get(app, "/scenarios")
    assert response.status == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"scenarios"}
    assert body["scenarios"] == []


def test_get_scenarios_lists_seeded_fixtures(seeded_app) -> None:
    response = get(seeded_app, "/scenarios")
    assert response.status == 200, response.text
    summaries = response.json()["scenarios"]
    assert [entry["name"] for entry in summaries] == ["city-centre", "harbour"]
    assert [entry["id"] for entry in summaries] == ["scn_0001", "scn_0002"]
    for entry in summaries:
        assert set(entry.keys()) == {"id", "name"}


def test_post_scenarios_creates_deterministic_record(app) -> None:
    response = post(app, "/scenarios", json=VALID_SCENARIO_BODY)
    assert response.status == 201, response.text
    record = response.json()
    assert set(record.keys()) == {"id", "scenario", "created_at"}
    assert record["id"] == "scn_0001"
    assert record["created_at"] == "2026-01-01T00:00:00Z"  # injected FakeClock origin
    assert record["scenario"] == VALID_SCENARIO_BODY["scenario"]


def test_post_scenarios_scenario_validates_against_frozen_schema(app) -> None:
    from services.api.schemas import SCENARIO_SCHEMA_PATH, load_frozen_schema

    frozen = load_frozen_schema(SCENARIO_SCHEMA_PATH)
    response = post(app, "/scenarios", json=VALID_SCENARIO_BODY)
    assert response.status == 201, response.text
    jsonschema.validate(response.json()["scenario"], frozen["properties"]["scenario"])


def test_get_scenarios_by_id_returns_created_record(app) -> None:
    created = create_scenario(app, "harbour-view")
    response = get(app, f"/scenarios/{created['id']}")
    assert response.status == 200, response.text
    assert response.json() == created
    assert response.json()["scenario"]["name"] == "harbour-view"


def test_get_scenarios_unknown_id_404(app) -> None:
    response = get(app, "/scenarios/scn_9999")
    assert_error(response, 404, "scn_9999", "not found")


def test_post_scenarios_missing_nodes_frozen_schema_rejects_422(app) -> None:
    response = post(app, "/scenarios", json={"scenario": {"name": "no-nodes"}})
    detail = assert_error_detail_list(response, 422)
    assert "nodes" in jsonlib.dumps(detail)


def test_post_scenarios_unknown_key_strict_declaration_rejects_422(app) -> None:
    body = {"scenario": {**VALID_SCENARIO_BODY["scenario"], "bogus": 1}}
    response = post(app, "/scenarios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "bogus" in jsonlib.dumps(detail)


def test_post_scenarios_nan_position_rejected_422(app) -> None:
    body = {
        "scenario": {
            "name": "nan-grid",
            "nodes": [
                {"id": "n1", "type": "fixed_radio", "position": [float("nan"), 2.0], "radio": "r1"}
            ],
        }
    }
    response = post(app, "/scenarios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "non-finite" in jsonlib.dumps(detail)


def test_post_scenarios_wrong_type_rejected_422(app) -> None:
    body = {"scenario": {**VALID_SCENARIO_BODY["scenario"], "name": 42}}
    response = post(app, "/scenarios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "string" in jsonlib.dumps(detail)


def test_post_scenarios_malformed_json_422(app) -> None:
    response = post(app, "/scenarios", raw_body=b'{"scenario": ')
    detail = assert_error_detail_list(response, 422)
    assert "json" in jsonlib.dumps(detail).lower()


def test_post_scenarios_empty_body_422(app) -> None:
    response = post(app, "/scenarios", raw_body=b"")
    detail = assert_error_detail_list(response, 422)
    assert jsonlib.dumps(detail)


def test_post_scenarios_non_object_body_422(app) -> None:
    response = post(app, "/scenarios", raw_body=b"[1, 2]")
    assert_error_detail_list(response, 422)


# --------------------------------------------------------------------------------------
# POST /simulations and the control routes
# --------------------------------------------------------------------------------------


def test_post_simulations_creates_loaded(app) -> None:
    scenario = create_scenario(app)
    response = post(app, "/simulations", json={"scenario_id": scenario["id"]})
    assert response.status == 201, response.text
    body = response.json()
    assert set(body.keys()) == {"id", "scenario_id", "status"}
    assert body == {"id": "sim_0001", "scenario_id": scenario["id"], "status": "LOADED"}
    assert app.state.registry.engine_calls == ["sim_0001:load"]


def test_post_simulations_unknown_scenario_404(app) -> None:
    response = post(app, "/simulations", json={"scenario_id": "scn_9999"})
    assert_error(response, 404, "scn_9999", "not found")


def test_post_simulations_missing_field_422(app) -> None:
    response = post(app, "/simulations", json={})
    detail = assert_error_detail_list(response, 422)
    assert "scenario_id" in jsonlib.dumps(detail)


def test_engine_called_exactly_once_on_create(app) -> None:
    scenario = create_scenario(app)
    post(app, "/simulations", json={"scenario_id": scenario["id"]})
    assert app.state.registry.engine_calls == ["sim_0001:load"]


def test_start_transitions_to_running_exactly_once(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    response = post(app, f"/simulations/{simulation['id']}/start")
    assert response.status == 200, response.text
    assert response.json()["status"] == "RUNNING"
    assert app.state.registry.engine_calls == ["sim_0001:load", "sim_0001:start"]


def test_pause_resume_reset_cycle_exactly_once_each(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    sim_id = simulation["id"]
    assert post(app, f"/simulations/{sim_id}/start").json()["status"] == "RUNNING"
    assert post(app, f"/simulations/{sim_id}/pause").json()["status"] == "PAUSED"
    assert post(app, f"/simulations/{sim_id}/resume").json()["status"] == "RUNNING"
    assert post(app, f"/simulations/{sim_id}/reset").json()["status"] == "LOADED"
    assert app.state.registry.engine_calls == [
        "sim_0001:load",
        "sim_0001:start",
        "sim_0001:pause",
        "sim_0001:resume",
        "sim_0001:reset",
    ]


def test_engine_called_exactly_once_on_pause(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    post(app, f"/simulations/{simulation['id']}/start")
    post(app, f"/simulations/{simulation['id']}/pause")
    calls = app.state.registry.engine_calls
    assert calls.count("sim_0001:pause") == 1
    assert len(calls) == 3  # load + start + pause, nothing double


def test_engine_called_exactly_once_on_resume(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    post(app, f"/simulations/{simulation['id']}/start")
    post(app, f"/simulations/{simulation['id']}/pause")
    post(app, f"/simulations/{simulation['id']}/resume")
    calls = app.state.registry.engine_calls
    assert calls.count("sim_0001:resume") == 1
    assert len(calls) == 4


def test_start_illegal_from_paused_409(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    sim_id = simulation["id"]
    post(app, f"/simulations/{sim_id}/start")
    post(app, f"/simulations/{sim_id}/pause")
    response = post(app, f"/simulations/{sim_id}/start")
    assert_error(response, 409, "start() illegal in state PAUSED")


def test_pause_illegal_from_loaded_409(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    response = post(app, f"/simulations/{simulation['id']}/pause")
    assert_error(response, 409, "pause() illegal in state LOADED")


def test_resume_illegal_from_loaded_409(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    response = post(app, f"/simulations/{simulation['id']}/resume")
    assert_error(response, 409, "resume() illegal in state LOADED")


def test_start_twice_illegal_409(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    sim_id = simulation["id"]
    assert post(app, f"/simulations/{sim_id}/start").status == 200
    response = post(app, f"/simulations/{sim_id}/start")  # second start from RUNNING
    assert_error(response, 409, "start() illegal in state RUNNING")
    # both attempts are in the call log; neither was executed twice
    assert app.state.registry.engine_calls.count("sim_0001:start") == 2


def test_reset_from_running_is_legal_and_returns_loaded(app) -> None:
    # reset() is legal from RUNNING (any state except new) — this asserts the
    # positive side; the illegal "new" side is engine-level (port contract).
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    post(app, f"/simulations/{simulation['id']}/start")
    response = post(app, f"/simulations/{simulation['id']}/reset")
    assert response.status == 200, response.text
    assert response.json()["status"] == "LOADED"


def test_control_unknown_simulation_404(app) -> None:
    response = post(app, "/simulations/sim_9999/start")
    assert_error(response, 404, "sim_9999", "not found")


def test_step_has_no_route_intentional_gap(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    for method in ("POST", "GET"):
        response = request(app, method, f"/simulations/{simulation['id']}/step")
        assert response.status == 404, response.text


# --------------------------------------------------------------------------------------
# POST /radios + PATCH /radios/{id} + GET /links/{a}/{b}
# --------------------------------------------------------------------------------------


def test_post_radios_creates_deterministic_radio(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {**VALID_RADIO_BODY, "simulation_id": simulation["id"]}
    response = post(app, "/radios", json=body)
    assert response.status == 201, response.text
    radio = response.json()
    assert set(radio.keys()) == RADIO_KEYS
    assert radio["id"] == "rdr_0001"
    assert radio["simulation_id"] == simulation["id"]
    assert "pattern" not in radio["antenna"]  # callable, never on the wire
    assert "local_position" not in radio  # runtime-resolved, not in Wave-1 shape
    assert radio["position"] == {"lat": 48.85, "lon": 2.35, "alt_m": 30.0}


def test_post_radios_unknown_simulation_404(app) -> None:
    body = {**VALID_RADIO_BODY, "simulation_id": "sim_9999"}
    response = post(app, "/radios", json=body)
    assert_error(response, 404, "sim_9999", "not found")


def test_post_radios_domain_valueerror_frequency_zero_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {
        **VALID_RADIO_BODY,
        "simulation_id": simulation["id"],
        "frequency": {"center_hz": 0.0, "bandwidth_hz": 12_500.0},
    }
    response = post(app, "/radios", json=body)
    assert_error(response, 422, "center_hz must be positive")  # domain message, not 500


def test_post_radios_domain_valueerror_latitude_out_of_range_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {
        **VALID_RADIO_BODY,
        "simulation_id": simulation["id"],
        "position": {"lat": 91.0, "lon": 2.35},
    }
    response = post(app, "/radios", json=body)
    assert_error(response, 422, "lat out of range")


def test_post_radios_unknown_field_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {**VALID_RADIO_BODY, "simulation_id": simulation["id"], "bogus": 1}
    response = post(app, "/radios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "bogus" in jsonlib.dumps(detail)


def test_post_radios_missing_subfield_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {key: value for key, value in VALID_RADIO_BODY.items() if key != "receiver"}
    body["simulation_id"] = simulation["id"]
    response = post(app, "/radios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "receiver" in jsonlib.dumps(detail)


def test_post_radios_nan_frequency_rejected_before_domain(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {
        **VALID_RADIO_BODY,
        "simulation_id": simulation["id"],
        "frequency": {"center_hz": float("nan"), "bandwidth_hz": 12_500.0},
    }
    response = post(app, "/radios", json=body)
    detail = assert_error_detail_list(response, 422)
    assert "non-finite" in jsonlib.dumps(detail)


def test_patch_radio_updates_position_and_publishes_map_delta(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(
        app,
        f"/radios/{radio['id']}",
        json={"position": {"lat": 48.9, "lon": 2.4, "alt_m": 10.0}},
    )
    assert response.status == 200, response.text
    updated = response.json()
    assert set(updated.keys()) == RADIO_KEYS
    assert updated["position"] == {"lat": 48.9, "lon": 2.4, "alt_m": 10.0}
    assert updated["frequency"] == radio["frequency"]  # untouched subfield preserved
    # The mock published the delta on simulation:{id}:telemetry.
    from services.api.ws_contract import CHANNEL_MAP, CHANNEL_RADIO, telemetry_topic

    last = app.state.bus.last_payload(telemetry_topic(simulation["id"]))
    assert last is not None
    assert last["channel"] in {CHANNEL_RADIO, CHANNEL_MAP}


def test_patch_radio_merges_whole_values_only(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(
        app,
        f"/radios/{radio['id']}",
        json={"frequency": {"center_hz": 915_000_000.0, "bandwidth_hz": 2_000_000.0}},
    )
    assert response.status == 200, response.text
    assert response.json()["frequency"] == {
        "center_hz": 915_000_000.0,
        "bandwidth_hz": 2_000_000.0,
    }
    assert response.json()["receiver"] == radio["receiver"]


def test_patch_radio_unknown_field_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(app, f"/radios/{radio['id']}", json={"bogus": 1})
    detail = assert_error_detail_list(response, 422)
    assert "bogus" in jsonlib.dumps(detail)


def test_patch_radio_immutable_id_field_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(app, f"/radios/{radio['id']}", json={"id": "rdr_hacked"})
    detail = assert_error_detail_list(response, 422)
    assert "id" in jsonlib.dumps(detail)
    # unchanged in the store
    assert get(app, "/scenarios/" + scenario["id"]).status == 200
    listing = app.state.registry.radios(simulation["id"])
    assert [entry["id"] for entry in listing] == [radio["id"]]


def test_patch_radio_immutable_simulation_id_field_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(app, f"/radios/{radio['id']}", json={"simulation_id": "sim_other"})
    assert_error_detail_list(response, 422)


def test_patch_radio_empty_patch_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(app, f"/radios/{radio['id']}", json={})
    assert_error_detail_list(response, 422)


def test_patch_radio_unknown_radio_404(app) -> None:
    response = patch(app, "/radios/rdr_9999", json={"position": {"lat": 1.0, "lon": 1.0}})
    assert_error(response, 404, "rdr_9999", "not found")


def test_patch_radio_domain_valueerror_422(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    radio = create_radio(app, simulation["id"])
    response = patch(
        app,
        f"/radios/{radio['id']}",
        json={"frequency": {"center_hz": -1.0, "bandwidth_hz": 12_500.0}},
    )
    assert_error(response, 422, "center_hz must be positive")


def test_get_link_known_pair_known_values(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    first = create_radio(app, simulation["id"])
    second = create_radio(app, simulation["id"])
    response = get(app, f"/links/{first['id']}/{second['id']}")
    assert response.status == 200, response.text
    assert response.json() == {
        "tx_id": first["id"],
        "rx_id": second["id"],
        "snr_db": 12.5,
        "margin_db": 6.0,
        "quality": "up",
        "time_s": 0.0,
    }


def test_get_link_reversed_direction_matches(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    first = create_radio(app, simulation["id"])
    second = create_radio(app, simulation["id"])
    forward = get(app, f"/links/{first['id']}/{second['id']}")
    reversed_response = get(app, f"/links/{second['id']}/{first['id']}")
    assert reversed_response.status == 200, reversed_response.text
    assert reversed_response.json() == forward.json()  # tx/rx kept as stored


def test_get_link_unknown_pair_404(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    only = create_radio(app, simulation["id"])
    response = get(app, f"/links/{only['id']}/rdr_9999")
    assert_error(response, 404, "not found")


# --------------------------------------------------------------------------------------
# Geodata routes (all four YAML paths, provider mocked — no GeoServer)
# --------------------------------------------------------------------------------------


def test_get_geodata_layers_lists_defaults(app) -> None:
    response = get(app, "/geodata/layers")
    assert response.status == 200, response.text
    layers = response.json()["layers"]
    assert layers == [
        {"name": "base_terrain", "kind": "raster"},
        {"name": "admin_boundaries", "kind": "vector"},
    ]


def test_post_geodata_layers_publishes_vector(app) -> None:
    response = post(
        app,
        "/geodata/layers",
        json={"name": "roads", "kind": "vector", "path_or_uri": "data/roads.geojson"},
    )
    assert response.status == 201, response.text
    assert response.json() == {"name": "roads", "kind": "vector"}
    names = [layer["name"] for layer in get(app, "/geodata/layers").json()["layers"]]
    assert "roads" in names


def test_post_geodata_layers_publishes_raster(app) -> None:
    response = post(
        app,
        "/geodata/layers",
        json={
            "name": "dem",
            "kind": "raster",
            "path_or_uri": "s3://bucket/dem.tif",
            "srs": "EPSG:3857",
        },
    )
    assert response.status == 201, response.text
    assert response.json() == {"name": "dem", "kind": "raster"}


def test_post_geodata_layers_invalid_kind_422(app) -> None:
    response = post(
        app,
        "/geodata/layers",
        json={"name": "nope", "kind": "rasterx", "path_or_uri": "x"},
    )
    assert_error_detail_list(response, 422)


def test_post_geodata_layers_missing_field_422(app) -> None:
    response = post(app, "/geodata/layers", json={"name": "x", "kind": "vector"})
    detail = assert_error_detail_list(response, 422)
    assert "path_or_uri" in jsonlib.dumps(detail)


def test_get_elevation_is_deterministic_and_schema_valid(app) -> None:
    path = "/geodata/elevation?lat=48.85&lon=2.35"
    first = get(app, path)
    second = get(app, path)
    assert first.status == 200, first.text
    body = first.json()
    assert set(body.keys()) == {"lat", "lon", "elevation_m"}
    assert body["lat"] == 48.85 and body["lon"] == 2.35
    assert isinstance(body["elevation_m"], float) and math.isfinite(body["elevation_m"])
    assert second.json() == body  # same query -> identical value (pure function)


def test_get_elevation_lat_out_of_range_422(app) -> None:
    response = get(app, "/geodata/elevation?lat=91.0&lon=2.35")
    assert_error(response, 422, "lat out of range")


def test_get_elevation_nan_query_422(app) -> None:
    response = get(app, "/geodata/elevation?lat=nan&lon=2.35")
    assert_error(response, 422, "lat out of range")


def test_get_elevation_missing_query_parameter_422(app) -> None:
    response = get(app, "/geodata/elevation?lat=48.85")
    assert_error_detail_list(response, 422)


def test_get_elevation_profile_exact_sample_count(app) -> None:
    path = "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.90&lon2=2.40&samples=7"
    response = get(app, path)
    assert response.status == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"profile_m"}
    assert len(body["profile_m"]) == 7
    assert all(isinstance(value, float) and math.isfinite(value) for value in body["profile_m"])


def test_get_elevation_profile_samples_one_422(app) -> None:
    path = "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.90&lon2=2.40&samples=1"
    response = get(app, path)
    assert_error(response, 422, "samples must be >= 2")


def test_get_elevation_profile_samples_not_integer_422(app) -> None:
    path = "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.90&lon2=2.40&samples=abc"
    response = get(app, path)
    assert_error_detail_list(response, 422)


def test_get_elevation_profile_missing_query_parameter_422(app) -> None:
    path = "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.90&lon2=2.40"
    response = get(app, path)
    assert_error_detail_list(response, 422)


# --------------------------------------------------------------------------------------
# 413 body limit + 500 catch-all + uniform envelope
# --------------------------------------------------------------------------------------


def test_oversized_body_rejected_413(app) -> None:
    assert MAX_BODY_BYTES == 1024 * 1024
    response = post(
        app,
        "/scenarios",
        raw_body=b'{"scenario": {"name": "x", "nodes": []}}',
        content_length_override=2 * 1024 * 1024,
    )
    assert_error(response, 413, "too large")


def test_body_with_accurate_length_under_limit_accepted(app) -> None:
    body_bytes = jsonlib.dumps(VALID_SCENARIO_BODY).encode("utf-8")
    response = post(
        app,
        "/scenarios",
        raw_body=body_bytes,
        content_length_override=len(body_bytes),
    )
    assert response.status == 201, response.text
    assert response.json()["id"] == "scn_0001"


def test_unexpected_exception_returns_500_envelope_without_traceback(app) -> None:
    @app.get("/__boom")
    def boom() -> None:  # pragma: no cover - registration only
        raise RuntimeError("kaboom")

    response = get(app, "/__boom")
    body = assert_error(response, 500, "internal error")
    assert body["detail"] == "internal error"
    assert "kaboom" not in response.text
    assert "Traceback" not in response.text


def test_openapi_document_served(app) -> None:
    response = get(app, "/openapi.json")
    assert response.status == 200, response.text
    paths = set(response.json()["paths"].keys())
    assert "/scenarios" in paths
    assert len(paths) == 13  # the frozen YAML's path count (15 operations)


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/scenarios", "GET"),
        ("/scenarios", "POST"),
        ("/scenarios/{id}", "GET"),
        ("/simulations", "POST"),
        ("/simulations/{id}/start", "POST"),
        ("/simulations/{id}/pause", "POST"),
        ("/simulations/{id}/resume", "POST"),
        ("/simulations/{id}/reset", "POST"),
        ("/radios", "POST"),
        ("/radios/{id}", "PATCH"),
        ("/links/{a}/{b}", "GET"),
        ("/geodata/layers", "GET"),
        ("/geodata/layers", "POST"),
        ("/geodata/elevation", "GET"),
        ("/geodata/elevation/profile", "GET"),
    ],
)
def test_every_yaml_operation_is_routed(app, path: str, method: str) -> None:
    from fastapi.routing import APIRoute

    app_ops = {
        (candidate_method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for candidate_method in route.methods
        if candidate_method not in {"HEAD", "OPTIONS"}
    }
    assert (method, path) in app_ops


# --------------------------------------------------------------------------------------
# Adversarial: domain boundaries, odd path ids, non-finite JSON numbers
# --------------------------------------------------------------------------------------


def test_latitude_longitude_boundaries_accepted_and_just_past_rejected(app) -> None:
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {
        **VALID_RADIO_BODY,
        "simulation_id": simulation["id"],
        "position": {"lat": 90.0, "lon": 180.0, "alt_m": 12.5},
    }
    accepted = post(app, "/radios", json=body)
    assert accepted.status == 201, accepted.text
    assert accepted.json()["position"] == {"lat": 90.0, "lon": 180.0, "alt_m": 12.5}

    just_past = post(app, "/radios", json={**body, "position": {"lat": 90.1, "lon": 180.0}})
    assert_error(just_past, 422, "lat out of range")  # frozen domain message, never 500


def test_infinity_request_rejected_422_never_500(app) -> None:
    # json.dumps emits the Python-specific token "Infinity"; json.loads accepts
    # it, so it must be stopped by the finite-number check with a 422.
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    body = {
        **VALID_RADIO_BODY,
        "simulation_id": simulation["id"],
        "frequency": {"center_hz": float("inf"), "bandwidth_hz": 12_500.0},
    }
    response = post(app, "/radios", json=body)
    assert_error(response, 422)


@pytest.mark.parametrize(
    "odd_id",
    ["../secrets", "%00", "radio-\U0001f3a9", "x" * 10_000],
    ids=["dot-dot-segment", "percent-null", "emoji", "ten-thousand-chars"],
)
def test_odd_path_ids_answer_404_without_crashing(app, odd_id: str) -> None:
    # GET routes that exist for GET, plus the PATCH-only radio route with a
    # valid body (GET /radios/{id} has no operation at all - 405, not 404).
    for template in ("/scenarios/{value}", "/links/{value}/rdr_0001"):
        assert_error(get(app, template.format(value=odd_id)), 404)
    assert_error(
        patch(app, f"/radios/{odd_id}", json={"position": {"lat": 1.0, "lon": 2.0}}),
        404,
    )


def test_success_response_bodies_contain_only_finite_floats(app) -> None:
    # Starlette's JSONResponse uses allow_nan=False: a non-finite float in any
    # payload would become a 500. Every fixture float must survive strict dumps.
    scenario = create_scenario(app)
    simulation = create_simulation(app, scenario["id"])
    control = post(app, f"/simulations/{simulation['id']}/start")
    radio_a = create_radio(app, simulation["id"])
    radio_b = create_radio(app, simulation["id"])
    bodies = [
        control.json(),
        get(app, "/scenarios").json(),
        get(app, f"/scenarios/{scenario['id']}").json(),
        post(app, "/simulations", json={"scenario_id": scenario["id"]}).json(),
        patch(
            app,
            f"/radios/{radio_a['id']}",
            json={"position": {"lat": 48.9, "lon": 2.4, "alt_m": 5.0}},
        ).json(),
        get(app, f"/links/{radio_a['id']}/{radio_b['id']}").json(),
        get(app, "/geodata/layers").json(),
        get(app, "/geodata/elevation?lat=48.85&lon=2.35").json(),
        get(
            app,
            "/geodata/elevation/profile?lat1=48.85&lon1=2.35&lat2=48.86&lon2=2.36&samples=5",
        ).json(),
    ]
    for body in bodies:
        jsonlib.dumps(body, allow_nan=False)  # must not raise ValueError
