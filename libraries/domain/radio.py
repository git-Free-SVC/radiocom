"""Radio composition types. See architecture doc §9. Minimal shape needed
for plugin-sdk signatures in W0-5; full validation/mobility lands in W0-3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from libraries.domain.frequency import Frequency
from libraries.domain.position import ENUPosition, GeoPosition


@dataclass(frozen=True, slots=True)
class Antenna:
    antenna_type: str
    gain_dBi: float
    height_m: float
    # pattern(azimuth_deg, elevation_deg) -> relative gain in dB, default omni
    pattern: Callable[[float, float], float] = field(default=lambda az, el: 0.0)
    polarization: str = "vertical"


@dataclass(frozen=True, slots=True)
class Transmitter:
    power_watt: float
    cable_loss_db: float = 0.0


@dataclass(frozen=True, slots=True)
class Receiver:
    sensitivity_dBm: float
    noise_figure_dB: float


@dataclass(frozen=True, slots=True)
class Radio:
    id: str
    frequency: Frequency
    transmitter: Transmitter
    receiver: Receiver
    antenna: Antenna
    position: GeoPosition
    local_position: Optional[ENUPosition] = None  # resolved by World Engine at runtime
