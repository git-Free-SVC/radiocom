"""Private argument validators shared by the physics modules."""

from __future__ import annotations

import math

from libraries.physics.errors import PhysicsInputError


def finite(name: str, value: float) -> float:
    """Return ``value`` as a float if it is a finite real number, else raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsInputError(f"{name} must be a real number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise PhysicsInputError(f"{name} must be finite, got {value!r}")
    return result


def positive(name: str, value: float) -> float:
    """Return ``value`` if it is finite and strictly positive, else raise."""
    result = finite(name, value)
    if result <= 0.0:
        raise PhysicsInputError(f"{name} must be > 0, got {value!r}")
    return result


def in_range(name: str, value: float, low: float, high: float) -> float:
    """Return ``value`` if finite and within ``[low, high]``, else raise."""
    result = finite(name, value)
    if not low <= result <= high:
        raise PhysicsInputError(f"{name} must be within [{low}, {high}], got {value!r}")
    return result


def finite_result(name: str, value: float) -> float:
    """Guard an *output*: raise instead of returning NaN/inf."""
    if not math.isfinite(value):
        raise PhysicsInputError(f"{name} is not finite ({value!r}); inputs out of numeric range")
    return value
