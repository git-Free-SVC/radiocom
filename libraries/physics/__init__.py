"""Reusable, validated RF math for propagation models and link budgets.

This package holds the physics that any propagation model needs: distances
between radios, free-space path loss, received power, noise floor, SNR, link
margin, Eb/N0 and a link-quality classifier. It contains no scenario state,
no I/O and no global mutable state, so every function is a pure function of
its arguments (architecture doc §14 determinism).

Typical use::

    from libraries.physics import free_space_path_loss_db, slant_range_m

    distance = slant_range_m(tx.position, rx.position)
    path_loss = free_space_path_loss_db(distance, tx.frequency.center_hz)

Invalid input raises :class:`PhysicsInputError` (a :class:`ValueError`
subclass) whose message names the offending argument and value; no raw
``ValueError: math domain error`` or ``OverflowError`` ever escapes.
"""

from __future__ import annotations

from .constants import (
    EARTH_MEAN_RADIUS_M,
    FSPL_CONSTANT_DB,
    MARGINAL_MARGIN_DB,
    MIN_DISTANCE_M,
    NOISE_DENSITY_DBM_HZ,
    SPEED_OF_LIGHT_M_S,
    UP_MARGIN_DB,
)
from .distance import haversine_distance_m, slant_range_m
from .errors import PhysicsInputError
from .link_budget import (
    LinkBudgetResult,
    calculate_link_budget,
    dbm_from_watts,
    eb_n0_db,
    link_margin_db,
    link_quality,
    link_state,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
    watts_from_dbm,
)
from .propagation import free_space_path_loss_db

__all__ = [
    "EARTH_MEAN_RADIUS_M",
    "FSPL_CONSTANT_DB",
    "MARGINAL_MARGIN_DB",
    "MIN_DISTANCE_M",
    "NOISE_DENSITY_DBM_HZ",
    "SPEED_OF_LIGHT_M_S",
    "UP_MARGIN_DB",
    "LinkBudgetResult",
    "PhysicsInputError",
    "calculate_link_budget",
    "dbm_from_watts",
    "eb_n0_db",
    "free_space_path_loss_db",
    "haversine_distance_m",
    "link_margin_db",
    "link_quality",
    "link_state",
    "noise_floor_dbm",
    "received_power_dbm",
    "slant_range_m",
    "snr_db",
    "watts_from_dbm",
]
