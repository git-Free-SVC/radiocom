"""PropagationModel interface. Frozen after Wave 0 — see docs/adr/ADR-000.
Implementations: services/propagation/{free_space,two_ray,hata,...}.py"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from libraries.domain.radio import Radio
from libraries.domain.rf_results import PropagationResult


@runtime_checkable
class PropagationModel(Protocol):
    """One propagation model (FreeSpace, TwoRay, Hata, ITM, RayTracing...).

    Implementations must be pure functions of (tx, rx, environment) plus an
    optional seeded RNG for fading — no hidden global state, so results are
    reproducible under the determinism requirement (§14/§24).
    """

    name: str  # e.g. "free_space" — used in scenario config to select the model

    def validity_domain(self) -> "ValidityDomain":
        """Frequency/distance/terrain ranges this model is valid for. The RF
        Core uses this to warn or refuse selection outside range (§11)."""
        ...

    def evaluate(
        self,
        tx: Radio,
        rx: Radio,
        *,
        seed: int | None = None,
    ) -> PropagationResult:
        """Compute path loss and channel effects between tx and rx.

        seed: if provided, any stochastic component (fading, multipath) MUST
        be deterministic for this seed (same seed -> identical result).
        """
        ...


class ValidityDomain(Protocol):
    min_freq_hz: float
    max_freq_hz: float
    min_distance_m: float
    max_distance_m: float
    requires_terrain: bool
