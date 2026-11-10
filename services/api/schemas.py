"""API-declared request/response JSON Schemas + the validation helpers.

Verified premise (foundation-v0): libraries/protocols/openapi.yaml declares
NO requestBody, NO components, NO response schemas and NO 4xx/5xx responses.
Every schema below is therefore an API-local decision marked
``assumed-spec-silent`` in README.txt (task prompt §6).

Two deliberate properties give exact key-set equality:
  * ``additionalProperties: false`` on every object, and
  * ``required`` listing every key of the wire shape.
A renamed, extra or missing field fails validation. Tests additionally
assert literal expected key sets so schema and handler cannot drift together
unnoticed.

POST /scenarios is the one route validated against a real frozen contract:
libraries/protocols/scenario.schema.json (draft-07). Because that schema
leaves additionalProperties unset, the API validates against it first
(frozen, authoritative) and then against the strict declaration below — a key
outside the frozen property set is rejected with 422 rather than echoed back.

NaN/inf: jsonschema calls NaN a "number", and Python's json.loads accepts
NaN/Infinity, so both validators run after ``assert_finite_request`` (input)
and are paired with ``iter_non_finite`` on output (validate_response). This
replaces pydantic's ``allow_inf_nan=False`` — no pydantic request/response
models exist in this package by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from services.api.errors import ApiError, ResponseContractError
from services.api.serialization import iter_non_finite

# services/api/schemas.py -> parents[2] == repository root
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_SCHEMA_PATH = REPOSITORY_ROOT / "libraries" / "protocols" / "scenario.schema.json"
LINK_EVENT_SCHEMA_PATH = (
    REPOSITORY_ROOT / "libraries" / "protocols" / "events" / "link_state_changed.schema.json"
)

# --------------------------------------------------------------------------------------
# Object fragments (shared by requests and responses)
# --------------------------------------------------------------------------------------

FREQUENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["center_hz", "bandwidth_hz"],
    "additionalProperties": False,
    "properties": {"center_hz": {"type": "number"}, "bandwidth_hz": {"type": "number"}},
}
TRANSMITTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["power_watt"],
    "additionalProperties": False,
    "properties": {"power_watt": {"type": "number"}, "cable_loss_db": {"type": "number"}},
}
RECEIVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["sensitivity_dBm", "noise_figure_dB"],
    "additionalProperties": False,
    "properties": {
        "sensitivity_dBm": {"type": "number"},
        "noise_figure_dB": {"type": "number"},
    },
}
ANTENNA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["antenna_type", "gain_dBi", "height_m"],
    "additionalProperties": False,
    "properties": {
        "antenna_type": {"type": "string"},
        "gain_dBi": {"type": "number"},
        "height_m": {"type": "number"},
        "polarization": {"type": "string"},
    },
}
POSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["lat", "lon"],
    "additionalProperties": False,
    "properties": {
        "lat": {"type": "number"},
        "lon": {"type": "number"},
        "alt_m": {"type": "number"},
    },
}

# Strict mirror of the frozen scenario.schema.json property set (same required
# lists, same types, plus additionalProperties: false at every object level).
SCENARIO_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "nodes"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "seed": {"type": "integer"},
        "environment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "terrain": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["layer_name", "source"],
                    "properties": {
                        "layer_name": {"type": "string"},
                        "source": {"type": "string"},
                        "srs": {"type": "string"},
                        "style": {"type": ["string", "null"]},
                    },
                },
                "vector_layers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["layer_name", "source"],
                        "properties": {
                            "layer_name": {"type": "string"},
                            "source": {"type": "string"},
                            "style": {"type": "string"},
                        },
                    },
                },
            },
        },
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "position", "radio"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"enum": ["fixed_radio", "mobile_radio"]},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 3,
                    },
                    "route": {"type": "string"},
                    "radio": {"type": "string"},
                },
            },
        },
        "interference": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "frequency", "bandwidth", "power"],
                "properties": {
                    "id": {"type": "string"},
                    "frequency": {"type": "number"},
                    "bandwidth": {"type": "number"},
                    "power": {"type": "number"},
                },
            },
        },
    },
}

# --------------------------------------------------------------------------------------
# Request schemas (API-declared, except CREATE_SCENARIO which is checked against the
# frozen scenario.schema.json first)
# --------------------------------------------------------------------------------------

CREATE_SCENARIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scenario"],
    "additionalProperties": False,
    "properties": {"scenario": SCENARIO_OBJECT_SCHEMA},
}
CREATE_SIMULATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scenario_id"],
    "additionalProperties": False,
    "properties": {"scenario_id": {"type": "string", "minLength": 1}},
}
CREATE_RADIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["simulation_id", "frequency", "transmitter", "receiver", "antenna", "position"],
    "additionalProperties": False,
    "properties": {
        "simulation_id": {"type": "string", "minLength": 1},
        "frequency": FREQUENCY_SCHEMA,
        "transmitter": TRANSMITTER_SCHEMA,
        "receiver": RECEIVER_SCHEMA,
        "antenna": ANTENNA_SCHEMA,
        "position": POSITION_SCHEMA,
    },
}
PATCH_RADIO_SCHEMA: dict[str, Any] = {
    # Empty patch rejected (minProperties); id/simulation_id are not listed and
    # additionalProperties: false rejects them -> 422 (immutable == unknown here,
    # both forbidden, both 422 — the spec defines no PATCH semantics at all).
    "type": "object",
    "minProperties": 1,
    "additionalProperties": False,
    "properties": {
        "frequency": FREQUENCY_SCHEMA,
        "transmitter": TRANSMITTER_SCHEMA,
        "receiver": RECEIVER_SCHEMA,
        "antenna": ANTENNA_SCHEMA,
        "position": POSITION_SCHEMA,
    },
}
CREATE_LAYER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "kind", "path_or_uri"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "kind": {"enum": ["raster", "vector"]},
        "path_or_uri": {"type": "string", "minLength": 1},
        "srs": {"type": "string"},
    },
}

REQUEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "POST /scenarios": CREATE_SCENARIO_SCHEMA,
    "POST /simulations": CREATE_SIMULATION_SCHEMA,
    "POST /radios": CREATE_RADIO_SCHEMA,
    "PATCH /radios/{id}": PATCH_RADIO_SCHEMA,
    "POST /geodata/layers": CREATE_LAYER_SCHEMA,
}

# --------------------------------------------------------------------------------------
# Response schemas
# --------------------------------------------------------------------------------------

SCENARIO_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name"],
    "additionalProperties": False,
    "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
}
SCENARIO_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "scenario", "created_at"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "scenario": SCENARIO_OBJECT_SCHEMA,
        "created_at": {"type": "string"},
    },
}
SIMULATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "scenario_id", "status"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "scenario_id": {"type": "string"},
        "status": {"type": "string"},
    },
}
RADIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "simulation_id",
        "frequency",
        "transmitter",
        "receiver",
        "antenna",
        "position",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "simulation_id": {"type": "string"},
        "frequency": FREQUENCY_SCHEMA,
        "transmitter": TRANSMITTER_SCHEMA,
        "receiver": RECEIVER_SCHEMA,
        "antenna": ANTENNA_SCHEMA,
        "position": POSITION_SCHEMA,
    },
}
LINK_SCHEMA: dict[str, Any] = {
    # Key set mirrors the frozen link_state_changed.schema.json event.
    "type": "object",
    "required": ["tx_id", "rx_id", "snr_db", "margin_db", "quality", "time_s"],
    "additionalProperties": False,
    "properties": {
        "tx_id": {"type": "string"},
        "rx_id": {"type": "string"},
        "snr_db": {"type": "number"},
        "margin_db": {"type": "number"},
        "quality": {"enum": ["up", "marginal", "down"]},
        "time_s": {"type": "number"},
    },
}
LAYER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "kind"],
    "additionalProperties": False,
    "properties": {"name": {"type": "string"}, "kind": {"type": "string"}},
}
ELEVATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["lat", "lon", "elevation_m"],
    "additionalProperties": False,
    "properties": {
        "lat": {"type": "number"},
        "lon": {"type": "number"},
        "elevation_m": {"type": "number"},
    },
}
PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["profile_m"],
    "additionalProperties": False,
    "properties": {"profile_m": {"type": "array", "items": {"type": "number"}}},
}

RESPONSE_SCHEMAS: dict[str, dict[str, Any]] = {
    "GET /scenarios": {
        "type": "object",
        "required": ["scenarios"],
        "additionalProperties": False,
        "properties": {"scenarios": {"type": "array", "items": SCENARIO_SUMMARY_SCHEMA}},
    },
    "POST /scenarios": SCENARIO_RECORD_SCHEMA,
    "GET /scenarios/{id}": SCENARIO_RECORD_SCHEMA,
    "POST /simulations": SIMULATION_SCHEMA,
    "POST /simulations/{id}/start": SIMULATION_SCHEMA,
    "POST /simulations/{id}/pause": SIMULATION_SCHEMA,
    "POST /simulations/{id}/resume": SIMULATION_SCHEMA,
    "POST /simulations/{id}/reset": SIMULATION_SCHEMA,
    "POST /radios": RADIO_SCHEMA,
    "PATCH /radios/{id}": RADIO_SCHEMA,
    "GET /links/{a}/{b}": LINK_SCHEMA,
    "GET /geodata/layers": {
        "type": "object",
        "required": ["layers"],
        "additionalProperties": False,
        "properties": {"layers": {"type": "array", "items": LAYER_SCHEMA}},
    },
    "POST /geodata/layers": LAYER_SCHEMA,
    "GET /geodata/elevation": ELEVATION_SCHEMA,
    "GET /geodata/elevation/profile": PROFILE_SCHEMA,
}

# --------------------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------------------

_REQUEST_VALIDATORS: dict[str, jsonschema.Draft7Validator] = {}
_RESPONSE_VALIDATORS: dict[str, jsonschema.Draft7Validator] = {}
_FROZEN_SCENARIO_SCHEMA: dict[str, Any] | None = None


def load_frozen_schema(path: Path) -> dict[str, Any]:
    """Read a frozen contract file with an explicit encoding (Windows/PowerShell)."""
    return json.loads(path.read_text(encoding="utf-8"))


def _frozen_scenario_schema() -> dict[str, Any]:
    """Lazily loaded so `import services.api` performs no file IO at all."""
    global _FROZEN_SCENARIO_SCHEMA
    if _FROZEN_SCENARIO_SCHEMA is None:
        _FROZEN_SCENARIO_SCHEMA = load_frozen_schema(SCENARIO_SCHEMA_PATH)
    return _FROZEN_SCENARIO_SCHEMA


def _schema_error(error: jsonschema.ValidationError) -> dict[str, Any]:
    return {
        "loc": [str(part) for part in error.absolute_path],
        "msg": error.message,
        "type": error.validator,
    }


def _errors_to_detail(errors: list[jsonschema.ValidationError]) -> list[dict[str, Any]]:
    return [_schema_error(error) for error in errors]


def assert_finite_request(value: Any) -> None:
    """Reject NaN/inf anywhere in a request body before schema validation."""
    bad = iter_non_finite(value)
    if bad:
        raise ApiError(
            422,
            [
                {
                    "loc": path.replace("$", "body").replace("[", ".").replace("]", "").split("."),
                    "msg": "non-finite number (NaN/Infinity) is not allowed",
                    "type": "value_error.non_finite",
                }
                for path in bad
            ],
        )


def validate_request(route_key: str, body: Any) -> None:
    """API-declared request schema -> ApiError(422), FastAPI-shaped detail list."""
    assert_finite_request(body)
    validator = _REQUEST_VALIDATORS.get(route_key)
    if validator is None:
        validator = jsonschema.Draft7Validator(REQUEST_SCHEMAS[route_key])
        _REQUEST_VALIDATORS[route_key] = validator
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        raise ApiError(422, _errors_to_detail(errors))


def validate_frozen_scenario(body: Any) -> None:
    """The one real frozen request contract: scenario.schema.json (§6 of the
    task prompt). Failure -> ApiError(422) with the same detail shape."""
    validator = jsonschema.Draft7Validator(_frozen_scenario_schema())
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        raise ApiError(422, _errors_to_detail(errors))


def validate_create_scenario(body: Any) -> None:
    """Frozen contract first (authoritative), then the API-strict declaration."""
    assert_finite_request(body)
    validate_frozen_scenario(body)
    validate_request("POST /scenarios", body)


def validate_response(route_key: str, payload: Any) -> None:
    """Declare-and-enforce: a body violating the API-declared response schema
    (or containing a non-finite float) is a SERVER bug -> 500, never a lie
    sent to the client."""
    bad = iter_non_finite(payload)
    if bad:
        raise ResponseContractError(
            f"response for {route_key} contains non-finite numbers at {', '.join(bad)}"
        )
    validator = _RESPONSE_VALIDATORS.get(route_key)
    if validator is None:
        validator = jsonschema.Draft7Validator(RESPONSE_SCHEMAS[route_key])
        _RESPONSE_VALIDATORS[route_key] = validator
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        first = _schema_error(errors[0])
        raise ResponseContractError(
            f"response for {route_key} violates the declared schema at "
            f"{'/'.join(first['loc']) or '<root>'}: {first['msg']}"
        )
