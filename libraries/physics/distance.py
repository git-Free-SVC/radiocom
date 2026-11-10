"""Distances between two :class:`~libraries.domain.position.GeoPosition` points.

Two functions:

* :func:`haversine_distance_m` — great-circle **surface** distance on a sphere
  of radius ``EARTH_MEAN_RADIUS_M``. Altitude is ignored.
* :func:`slant_range_m` — straight-line distance including the altitude
  difference. This is the distance free-space path loss uses.

Precision: the spherical model is accurate to roughly 0.3 % against WGS84 — more
than enough for link-budget path loss. Precision geodesy (ECEF/ENU, ellipsoid)
is owned by the World Engine, not by this module. The slant range treats the
altitude difference as perpendicular to the surface (flat-vertical
approximation): adequate when ``|delta_alt| << EARTH_MEAN_RADIUS_M``, crude for
satellite-scale altitudes.

Source: haversine formula, R. W. Sinnott, "Virtues of the Haversine",
Sky & Telescope 68(2), 1984.
"""

from __future__ import annotations

import math
from typing import Protocol

from libraries.physics import _validate
from libraries.physics.constants import EARTH_MEAN_RADIUS_M


class _HasGeoPosition(Protocol):
    lat: float
    lon: float
    alt_m: float


def _lat_lon(name: str, p: _HasGeoPosition) -> tuple[float, float]:
    lat = _validate.in_range(f"{name}.lat", p.lat, -90.0, 90.0)
    lon = _validate.in_range(f"{name}.lon", p.lon, -180.0, 180.0)
    return lat, lon


def haversine_distance_m(a: _HasGeoPosition, b: _HasGeoPosition) -> float:
    """Great-circle surface distance between ``a`` and ``b``, in metres.

    Formula: ``d = 2R * atan2(sqrt(h), sqrt(1-h))`` with
    ``h = sin^2(dphi/2) + cos(phi1) cos(phi2) sin^2(dlambda/2)``.

    Valid input: ``lat`` in [-90, 90], ``lon`` in [-180, 180] (degrees), finite.
    Longitudes are *not* wrapped by the caller's convention but the formula is
    periodic, so the antimeridian (179.5 vs -179.5) is handled correctly.
    Altitude is ignored. Returns a value in ``[0, pi*R]``.

    Raises:
        PhysicsInputError: for NaN/inf, out-of-range or non-numeric coordinates.
    """
    lat1, lon1 = _lat_lon("a", a)
    lat2, lon2 = _lat_lon("b", b)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)

    h = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    h = min(1.0, max(0.0, h))  # guard tiny floating-point excursions
    return 2.0 * EARTH_MEAN_RADIUS_M * math.atan2(math.sqrt(h), math.sqrt(1.0 - h))


def slant_range_m(a: _HasGeoPosition, b: _HasGeoPosition) -> float:
    """Straight-line distance between ``a`` and ``b`` including altitude, metres.

    ``slant = sqrt(haversine(a, b)**2 + (a.alt_m - b.alt_m)**2)``. For two points
    at equal altitude this equals :func:`haversine_distance_m`.

    Two radios at identical latitude/longitude but different altitudes are *not*
    degenerate: the result is ``|delta_alt|``.

    Raises:
        PhysicsInputError: for invalid coordinates, non-finite ``alt_m``, or an
            altitude difference so large that the result overflows.
    """
    surface = haversine_distance_m(a, b)
    alt_a = _validate.finite("a.alt_m", a.alt_m)
    alt_b = _validate.finite("b.alt_m", b.alt_m)
    delta_alt = _validate.finite_result("altitude difference", alt_a - alt_b)
    return _validate.finite_result("slant range", math.hypot(surface, delta_alt))
