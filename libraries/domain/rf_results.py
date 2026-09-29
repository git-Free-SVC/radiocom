"""RF result types returned by plugin-sdk implementations. Field names here
are frozen and match §9/§11 of the architecture doc verbatim — later agents
must not rename them."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True, slots=True)
class PropagationResult:
    path_loss_db: float
    rx_power_dbm: float
    delay_s: float = 0.0
    doppler_hz: float = 0.0
    los: bool = True
    multipath: tuple[float, ...] = field(default_factory=tuple)  # extra path delays, s
    fading_db: float = 0.0


class LinkQuality(str, Enum):
    UP = "up"
    MARGINAL = "marginal"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class LinkState:
    snr_db: float
    margin_db: float
    quality: LinkQuality


@dataclass(frozen=True, slots=True)
class LinkBudgetInput:
    tx_power_dbm: float
    tx_gain_dbi: float
    rx_gain_dbi: float
    path_loss_db: float
    cable_loss_db: float = 0.0
    polarization_loss_db: float = 0.0
    atmospheric_loss_db: float = 0.0
    shadowing_db: float = 0.0
    bandwidth_hz: float = 1.0
    noise_figure_db: float = 0.0
    sensitivity_dbm: float = -120.0
