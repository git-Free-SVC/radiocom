"""Reusable, validated RF math for propagation and link budgets."""

from .distance import (
    EARTH_MEAN_RADIUS_M,
    MIN_DISTANCE_M,
    haversine_distance_m,
    slant_range_m,
)
from .errors import PhysicsInputError
from .link_budget import (
    MARGINAL_MARGIN_DB,
    NOISE_DENSITY_DBM_HZ,
    UP_MARGIN_DB,
    LinkBudgetResult,
    calculate_link_budget,
    dbm_from_watts,
    eb_n0_db,
    link_margin_db,
    link_quality,
    noise_floor_dbm,
    received_power_dbm,
    snr_db,
    watts_from_dbm,
)
from .propagation import FSPL_CONSTANT_DB, free_space_path_loss_db

SPEED_OF_LIGHT_M_S = 299_792_458.0

__all__ = [
    "EARTH_MEAN_RADIUS_M",
    "FSPL_CONSTANT_DB",
    "LinkBudgetResult",
    "MARGINAL_MARGIN_DB",
    "MIN_DISTANCE_M",
    "NOISE_DENSITY_DBM_HZ",
    "PhysicsInputError",
    "SPEED_OF_LIGHT_M_S",
    "UP_MARGIN_DB",
    "calculate_link_budget",
    "dbm_from_watts",
    "eb_n0_db",
    "free_space_path_loss_db",
    "haversine_distance_m",
    "link_margin_db",
    "link_quality",
    "noise_floor_dbm",
    "received_power_dbm",
    "slant_range_m",
    "snr_db",
    "watts_from_dbm",
]
