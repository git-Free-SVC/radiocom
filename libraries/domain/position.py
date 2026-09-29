"""Position types. Pure data, zero I/O. See architecture doc §13."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeoPosition:
    """WGS84 geographic position."""

    lat: float  # degrees, -90..90
    lon: float  # degrees, -180..180
    alt_m: float = 0.0  # meters above ellipsoid

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0):
            raise ValueError(f"lat out of range: {self.lat}")
        if not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"lon out of range: {self.lon}")


@dataclass(frozen=True, slots=True)
class ENUPosition:
    """Local East-North-Up position, meters, relative to a scenario origin.
    This is what the simulation hot loop actually computes with (§13)."""

    east_m: float
    north_m: float
    up_m: float = 0.0
