"""Frequency domain type. See architecture doc §9."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Frequency:
    center_hz: float
    bandwidth_hz: float

    def __post_init__(self) -> None:
        if self.center_hz <= 0:
            raise ValueError(f"center_hz must be positive, got {self.center_hz}")
        if self.bandwidth_hz <= 0:
            raise ValueError(f"bandwidth_hz must be positive, got {self.bandwidth_hz}")

    @property
    def lower_hz(self) -> float:
        return self.center_hz - self.bandwidth_hz / 2

    @property
    def upper_hz(self) -> float:
        return self.center_hz + self.bandwidth_hz / 2

    def overlaps(self, other: "Frequency") -> bool:
        return self.lower_hz < other.upper_hz and other.lower_hz < self.upper_hz
