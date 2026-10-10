"""Deliberately simple terrain line-of-sight stub.

Straight line between two points vs. terrain from ``GeodataProvider``. Ignores
Earth curvature and refraction (later propagation models' job) and ignores
vector features such as buildings (out of scope for this ticket). ``alt_m`` is
taken as given: whatever the caller wants checked (ground, antenna height,
height above the ellipsoid) -- this module attaches no meaning to it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing only: keeps this module free of a runtime SDK import
    from libraries.domain.position import GeoPosition
    from libraries.plugin_sdk.geodata import GeodataProvider

#: 32 samples: ~3% of path length per step -- enough to catch a ridge on a
#: typical tens-of-km link without making the provider (a WCS query in
#: production) expensive. Callers with long paths should raise it.
DEFAULT_SAMPLES = 32


@dataclass(frozen=True, slots=True)
class LOSResult:
    """Outcome of a line-of-sight check.

    ``clear`` is True when no terrain sample rises above the line (touching
    counts as clear). ``min_clearance_m`` is the smallest ``line - terrain``
    over all samples: negative means obstructed by that many metres.
    ``worst_fraction`` is the path fraction (0 at ``a``, 1 at ``b``) where it
    occurs (the first such sample on ties); ``samples`` is how many points were
    evaluated.
    """

    clear: bool
    min_clearance_m: float
    worst_fraction: float
    samples: int


def line_of_sight(
    a: GeoPosition,
    b: GeoPosition,
    provider: GeodataProvider,
    samples: int = DEFAULT_SAMPLES,
) -> LOSResult:
    """Check whether the straight line a->b clears the terrain between them.

    Raises:
        TypeError: ``samples`` is not an ``int``.
        ValueError: ``samples < 2``; an endpoint altitude is not finite; the
            provider returns the wrong number of samples; or any elevation is
            NaN/inf. The last one matters: raster *nodata* typically arrives as
            NaN, and ``nan < x`` is always False, so a naive min-search would
            skip it and report an unknown path as clear.
    """
    if isinstance(samples, bool) or not isinstance(samples, int):
        raise TypeError(f"samples must be an int, got {type(samples).__name__}")
    if samples < 2:
        raise ValueError(f"samples must be >= 2, got {samples}")
    if not (math.isfinite(a.alt_m) and math.isfinite(b.alt_m)):
        raise ValueError(f"endpoint altitudes must be finite, got {a.alt_m} and {b.alt_m}")

    profile = provider.elevation_profile(a, b, samples)
    if len(profile) != samples:
        raise ValueError(f"provider returned {len(profile)} elevation samples, expected {samples}")

    _require_finite(profile)

    last = samples - 1
    start, rise = a.alt_m, b.alt_m - a.alt_m
    worst_index, min_clearance = 0, math.inf
    for i, terrain in enumerate(profile):
        clearance = start + (i / last) * rise - terrain  # line height - terrain
        if clearance < min_clearance:  # strict: first sample wins ties
            worst_index, min_clearance = i, clearance

    return LOSResult(
        clear=min_clearance >= 0.0,
        min_clearance_m=min_clearance,
        worst_fraction=worst_index / last,
        samples=samples,
    )


def _require_finite(profile: list[float]) -> None:
    """Raise ``ValueError`` unless every elevation is finite.

    ``sum()`` is one C-level pass and is non-finite if any element is NaN/inf,
    so the per-sample scan only runs on the (rare) failure path, to name the
    offending sample.
    """
    if math.isfinite(sum(profile)):
        return
    bad = next((i for i, t in enumerate(profile) if not math.isfinite(t)), None)
    if bad is None:  # finite samples whose sum overflows -- not real elevations
        raise ValueError("elevation samples are too large to be valid terrain heights")
    raise ValueError(
        f"elevation sample {bad} of {len(profile)} is {profile[bad]} (missing data?); "
        "refusing to report line of sight over unknown terrain"
    )
