"""Link-quality classifier from link margin.

CONVENTION (not specified by the frozen interfaces; should become an ADR):

* ``margin_db >= 10``      -> ``LinkQuality.UP``
* ``0 <= margin_db < 10``  -> ``LinkQuality.MARGINAL``
* ``margin_db < 0``        -> ``LinkQuality.DOWN``

Positive margin is required to close the link at all; 10 dB is the customary
buffer before calling it solidly reliable. Both boundaries belong to the
*better* class (10.0 -> UP, 0.0 -> MARGINAL; -0.0 -> MARGINAL).
"""

from __future__ import annotations

import math

from libraries.domain.rf_results import LinkQuality
from libraries.physics.constants import LINK_MARGINAL_MARGIN_DB, LINK_UP_MARGIN_DB
from libraries.physics.errors import PhysicsInputError


def link_quality(margin_db: float) -> LinkQuality:
    """Classify ``margin_db`` into UP / MARGINAL / DOWN.

    ``+inf`` maps to UP and ``-inf`` to DOWN (monotone, exhaustive).

    Raises:
        PhysicsInputError: for NaN or a non-numeric argument.
    """
    if isinstance(margin_db, bool) or not isinstance(margin_db, (int, float)):
        raise PhysicsInputError(f"margin_db must be a real number, got {margin_db!r}")
    if math.isnan(margin_db):
        raise PhysicsInputError("margin_db must not be NaN")
    if margin_db >= LINK_UP_MARGIN_DB:
        return LinkQuality.UP
    if margin_db >= LINK_MARGINAL_MARGIN_DB:
        return LinkQuality.MARGINAL
    return LinkQuality.DOWN
