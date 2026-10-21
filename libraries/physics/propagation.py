"""Free-space path-loss calculation."""

from __future__ import annotations

import math

from .distance import MIN_DISTANCE_M
from .errors import PhysicsInputError

FSPL_CONSTANT_DB = 32.44


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}") from exc
    if not math.isfinite(number):
        raise PhysicsInputError(f"{name} must be finite; got {value!r}")
    return number


def free_space_path_loss_db(distance_m: float, frequency_hz: float) -> float:
    """Return raw free-space path loss in dB using the engineering 32.44 form.

    Distances below ``MIN_DISTANCE_M`` are clamped to that value, including a
    zero range, to define co-located radio behavior and avoid log10(0). The
    raw result can be negative in the near field; propagation models should
    apply the passive-medium 0 dB floor where appropriate.
    """
    distance = _finite("distance_m", distance_m)
    frequency = _finite("frequency_hz", frequency_hz)
    if distance < 0.0:
        raise PhysicsInputError(f"distance_m must be >= 0; got {distance!r}")
    if frequency <= 0.0:
        raise PhysicsInputError(f"frequency_hz must be > 0; got {frequency!r}")

    effective_distance = max(distance, MIN_DISTANCE_M)
    # Log in the input's original units to avoid underflow from converting
    # subnormal meters to kilometers or hertz to megahertz.
    result = (
        20.0 * (math.log10(effective_distance) - 3.0)
        + 20.0 * (math.log10(frequency) - 6.0)
        + FSPL_CONSTANT_DB
    )
    if not math.isfinite(result):
        raise PhysicsInputError("free-space path loss result must be finite")
    return result
