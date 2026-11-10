"""Exceptions raised by ``libraries.physics``."""

from __future__ import annotations


class PhysicsInputError(ValueError):
    """An input to a physics function is invalid (NaN, inf, out of range, wrong type).

    Subclasses :class:`ValueError` so generic callers keep working, but every
    invalid input is reported with this named type and a message that names the
    offending argument and value — never a raw ``math domain error`` or
    ``OverflowError``.
    """
