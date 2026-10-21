"""Internal input-validation helpers shared by the physics modules.

Every public physics function validates its own arguments (task brief §5.12):
values must be finite, positive where the physics demands it, and the raised
:class:`~libraries.physics.errors.PhysicsInputError` message always names the
offending argument and value.
"""

from __future__ import annotations

import math

from .errors import PhysicsInputError


def finite_float(name: str, value: object) -> float:
    """Return ``value`` as a finite float, or raise :class:`PhysicsInputError`."""
    if type(value) is float:
        # Fast path: plain floats are what the simulation passes in, and this
        # function is called ~20 times per propagation evaluation.
        if math.isfinite(value):
            return value
        raise PhysicsInputError(f"{name} must be finite; got {value!r}")
    if isinstance(value, bool):
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}") from exc
    if not math.isfinite(number):
        raise PhysicsInputError(f"{name} must be finite; got {value!r}")
    return number


def positive_float(name: str, value: object) -> float:
    """Return ``value`` as a finite float strictly greater than zero."""
    number = finite_float(name, value)
    if number <= 0.0:
        raise PhysicsInputError(f"{name} must be > 0; got {number!r}")
    return number


def non_negative_float(name: str, value: object) -> float:
    """Return ``value`` as a finite float greater than or equal to zero."""
    number = finite_float(name, value)
    if number < 0.0:
        raise PhysicsInputError(f"{name} must be >= 0; got {number!r}")
    return number


def finite_result(name: str, value: float) -> float:
    """Return ``value`` if it is finite, otherwise raise :class:`PhysicsInputError`."""
    if not math.isfinite(value):
        raise PhysicsInputError(f"{name} result must be finite; got {value!r}")
    return value
