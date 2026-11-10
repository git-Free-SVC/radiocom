"""The single payload conversion layer: frozen domain types -> JSON-safe data.

Rules (task prompt §7): dataclass -> dict, Enum -> ``.value`` (str), tuple ->
list, datetime -> ISO-8601 UTC with a ``Z`` suffix, every float finite-checked.
Response payloads are built through this module and nowhere else.

Antenna.pattern (a Callable) and Radio.local_position (runtime-resolved, not
part of the Wave-1 wire shape) are deliberately excluded from the wire.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from libraries.domain.radio import Radio
from libraries.domain.rf_results import LinkState
from services.api.errors import ResponseContractError


def datetime_to_iso(value: datetime) -> str:
    """ISO-8601 UTC; naive datetimes are assumed UTC and end with a Z suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    text = value.isoformat()
    if text.endswith("+00:00"):
        text = text[: -len("+00:00")] + "Z"
    return text


def iter_non_finite(value: Any, path: str = "$") -> list[str]:
    """Return the dotted paths of every NaN/inf float inside a JSON-like value.

    Python's json.loads accepts NaN/Infinity by default, so a non-finite float
    can reach the API; jsonschema would happily call it a "number". This is
    the guard that keeps them off the wire in both directions.
    """
    found: list[str] = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(iter_non_finite(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(iter_non_finite(item, f"{path}[{index}]"))
    return found


def to_payload(value: Any) -> Any:
    """Recursively convert a domain object / JSON-like value to JSON-safe data.

    Non-finite floats raise ResponseContractError: a non-finite value here is
    a server-side data bug (mock fixtures must stay finite), never a client
    input error — client input is rejected long before serialization.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ResponseContractError(f"non-finite float in response payload: {value!r}")
        return value
    if isinstance(value, Enum):
        return to_payload(value.value)
    if isinstance(value, datetime):
        return datetime_to_iso(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        result: dict[str, Any] = {}
        for field in dataclasses.fields(value):
            item = getattr(value, field.name)
            if callable(item):  # Antenna.pattern: not representable, not on the wire
                continue
            result[field.name] = to_payload(item)
        return result
    if isinstance(value, (list, tuple)):
        return [to_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_payload(item) for key, item in value.items()}
    raise ResponseContractError(f"cannot serialise {type(value).__name__} onto the wire")


def radio_to_payload(radio: Radio, simulation_id: str) -> dict[str, Any]:
    """Wire shape for a radio (API-declared: openapi.yaml has no schemas).

    Key order is fixed here so identical states produce byte-identical
    responses across fresh app instances.
    """
    data = to_payload(radio)
    return {
        "id": data["id"],
        "simulation_id": simulation_id,
        "frequency": data["frequency"],
        "transmitter": data["transmitter"],
        "receiver": data["receiver"],
        "antenna": data["antenna"],
        "position": data["position"],
    }


def position_payload(radio: Radio) -> dict[str, Any]:
    """Map-channel event: {id, lat, lon, alt_m} derived from a radio's position."""
    return {"id": radio.id, **to_payload(radio.position)}


def link_to_payload(tx_id: str, rx_id: str, state: LinkState, time_s: float) -> dict[str, Any]:
    """Mirror of libraries/protocols/events/link_state_changed.schema.json keys."""
    return {"tx_id": tx_id, "rx_id": rx_id, **to_payload(state), "time_s": time_s}
