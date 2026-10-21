"""Exceptions raised by the reusable RF physics helpers.

The physics package never lets a raw ``ValueError: math domain error`` or an
``OverflowError`` escape to its callers: every invalid input is reported as a
:class:`PhysicsInputError` whose message names the offending argument and
value (architecture doc §9 / §11, task brief §5.12).
"""

from __future__ import annotations


class PhysicsInputError(ValueError):
    """An RF-physics input is invalid or cannot produce a finite result.

    It subclasses :class:`ValueError` so that callers which already guard
    against bad numbers keep working, while the physics package itself can
    raise a single, catchable, self-describing error type.
    """
