"""The API-local WebSocket contract — single source of envelope, topics,
channels and close codes (task prompt §5).

Why this file exists: openapi.yaml is OpenAPI 3.0.3, which cannot describe
WebSockets at all, and the only frozen event schema in libraries/protocols
is link_state_changed.schema.json. Nothing in the repository fixes a WS
envelope or topic name, so these decisions are API-local and marked
``assumed-spec-silent`` in README.txt — but they are fixed HERE so that the
implementation, the tests and the future Integration Agent all agree.

Envelope (both endpoints):
    {"kind": "snapshot" | "delta", "channel": <str>, "seq": <int>, "data": {...}}

  * seq starts at 0 per connection and increments for every message sent, so
    a client can detect dropped frames (drops happen under backpressure).
  * On connect the server sends ONE snapshot message per channel (initial
    state) and only then delta messages — snapshot-before-delta is mandatory
    and tested; deltas published during snapshot construction are buffered on
    the connection and flushed after the snapshots, so nothing is lost.
  * Link payloads (snapshot elements and deltas) validate against the frozen
    link_state_changed.schema.json; radio/map/spectrum payloads have no
    frozen schema and validate against the API-declared schemas in
    services.api.schemas / WS_DATA_SCHEMAS below.

Topic -> endpoint mapping (topic names appear in no frozen file):
    simulation:{id}:telemetry -> /ws/simulations/{id}/telemetry
    spectrum                   -> /spectrum
"""

from __future__ import annotations

from typing import Any

from services.api.schemas import LINK_SCHEMA, RADIO_SCHEMA

KIND_SNAPSHOT = "snapshot"
KIND_DELTA = "delta"

CHANNEL_RADIO = "radio"
CHANNEL_LINK = "link"
CHANNEL_MAP = "map"
CHANNEL_SPECTRUM = "spectrum"
TELEMETRY_CHANNELS = (CHANNEL_RADIO, CHANNEL_LINK, CHANNEL_MAP)

TELEMETRY_TOPIC_TEMPLATE = "simulation:{simulation_id}:telemetry"
SPECTRUM_TOPIC = "spectrum"

WS_PATH_TELEMETRY = "/ws/simulations/{id}/telemetry"
WS_PATH_SPECTRUM = "/spectrum"
WS_PATHS = (WS_PATH_TELEMETRY, WS_PATH_SPECTRUM)

# No frozen close-code registry exists -> API-local, assumed. Close happens
# after accept and BEFORE any subscription is created.
CLOSE_UNKNOWN_SIMULATION = 4404

# Queue bound per connection (§5): full queue -> drop oldest, count it,
# never block the publisher, never disconnect the slow client.
QUEUE_MAXSIZE = 256
# Deltas published before the snapshots are flushed are buffered up to this
# many messages, then the oldest pre-snapshot delta is dropped (counted).
PREBUFFER_LIMIT = 512

# Map-channel event key set (API-declared).
MAP_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "lat", "lon", "alt_m"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "lat": {"type": "number"},
        "lon": {"type": "number"},
        "alt_m": {"type": "number"},
    },
}
SPECTRUM_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["occupancy"],
    "additionalProperties": False,
    "properties": {"occupancy": {"type": "array", "items": {"type": "number"}}},
}
SPECTRUM_DELTA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["t_s", "occupancy"],
    "additionalProperties": False,
    "properties": {
        "t_s": {"type": "number"},
        "occupancy": {"type": "array", "items": {"type": "number"}},
    },
}
SPECTRUM_EMPTY_SNAPSHOT: dict[str, Any] = {"occupancy": []}

# API-local (assumed) data schemas keyed by (kind, channel). The link channel
# is validated against the FROZEN file instead (no extra keys allowed there
# either — the frozen schema simply leaves additionalProperties unset); see
# WS_DATA_SCHEMAS_FOR_TEST in tests/unit/api/conftest.py which loads it.
WS_DATA_SCHEMAS: dict[tuple[str, str], dict[str, Any]] = {
    (KIND_DELTA, CHANNEL_RADIO): RADIO_SCHEMA,
    (KIND_DELTA, CHANNEL_MAP): MAP_EVENT_SCHEMA,
    (KIND_DELTA, CHANNEL_SPECTRUM): SPECTRUM_DELTA_SCHEMA,
    (KIND_SNAPSHOT, CHANNEL_RADIO): {
        "type": "object",
        "required": ["radios"],
        "additionalProperties": False,
        "properties": {"radios": {"type": "array", "items": RADIO_SCHEMA}},
    },
    (KIND_SNAPSHOT, CHANNEL_MAP): {
        "type": "object",
        "required": ["positions"],
        "additionalProperties": False,
        "properties": {"positions": {"type": "array", "items": MAP_EVENT_SCHEMA}},
    },
    (KIND_SNAPSHOT, CHANNEL_SPECTRUM): SPECTRUM_SNAPSHOT_SCHEMA,
}
# The link snapshot wraps events in a list; each element is a frozen event.
LINK_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["links"],
    "additionalProperties": False,
    "properties": {"links": {"type": "array", "items": LINK_SCHEMA}},
}


def telemetry_topic(simulation_id: str) -> str:
    return TELEMETRY_TOPIC_TEMPLATE.format(simulation_id=simulation_id)


def make_message(kind: str, channel: str, seq: int, data: Any) -> dict[str, Any]:
    """The one envelope constructor — every outbound WS message goes through it."""
    return {"kind": kind, "channel": channel, "seq": seq, "data": data}


def build_telemetry_snapshot(
    radios: list[dict[str, Any]], links: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Initial state: exactly one snapshot payload per telemetry channel.
    Each link element validates against the frozen link_state_changed schema."""
    return {
        CHANNEL_RADIO: {"radios": radios},
        CHANNEL_LINK: {"links": links},
        CHANNEL_MAP: {"positions": [{"id": radio["id"], **radio["position"]} for radio in radios]},
    }


def spectrum_snapshot(last_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Current occupancy frame: the last spectrum event published on the bus,
    or the empty frame when no frame has ever been published."""
    if isinstance(last_payload, dict) and isinstance(last_payload.get("data"), dict):
        return last_payload["data"]
    return dict(SPECTRUM_EMPTY_SNAPSHOT)
