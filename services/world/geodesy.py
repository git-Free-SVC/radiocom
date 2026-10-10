"""WGS84 geodetic <-> ECEF conversions (pure math, standard library only).

Two layers:

* ``geo_to_ecef`` / ``ecef_to_geo`` -- the public API, on the frozen
  ``GeoPosition`` domain type (degrees, validated).
* ``geodetic_rad_to_ecef`` / ``ecef_to_geodetic_rad`` -- the same maths on bare
  floats in radians, with no object construction or validation. The ENU module
  builds on these so hot loops pay for the maths only.
"""

from __future__ import annotations

import math

from libraries.domain.position import GeoPosition

# --- WGS84 ellipsoid -------------------------------------------------------
WGS84_A = 6378137.0  # semi-major axis, metres
WGS84_F = 1.0 / 298.257223563  # flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F)  # semi-minor axis, metres (~6356752.314245)
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)  # first eccentricity squared
WGS84_EP2 = WGS84_E2 / (1.0 - WGS84_E2)  # second eccentricity squared

# --- ECEF -> geodetic solver settings --------------------------------------
# Bowring's closed-form start is accurate to ~1e-9 rad, so a single fixed-point
# refinement already lands at machine precision for realistic altitudes. We stop
# as soon as a refinement moves the latitude by less than this; measured over
# 550k points (-10 km..1000 km altitude, down to 1e-9 deg from the poles) the
# result is identical to iterating all the way down to 1e-15.
_REFINE_TOL_RAD = 1e-12
_MAX_REFINEMENTS = 5

_sin, _cos, _sqrt = math.sin, math.cos, math.sqrt
_atan2, _hypot = math.atan2, math.hypot


def geodetic_rad_to_ecef(lat: float, lon: float, alt_m: float) -> tuple[float, float, float]:
    """Geodetic (radians, radians, metres) -> ECEF ``(X, Y, Z)`` metres.

    ``N`` is the prime-vertical radius of curvature::

        N = a / sqrt(1 - e2 sin^2(lat))
        X = (N + h) cos(lat) cos(lon)
        Y = (N + h) cos(lat) sin(lon)
        Z = (N (1 - e2) + h) sin(lat)

    Non-finite inputs propagate as non-finite outputs (IEEE semantics).
    """
    sin_lat = _sin(lat)
    n = WGS84_A / _sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    ring = (n + alt_m) * _cos(lat)  # distance from the polar axis
    return ring * _cos(lon), ring * _sin(lon), (n * (1.0 - WGS84_E2) + alt_m) * sin_lat


def ecef_to_geodetic_rad(x: float, y: float, z: float) -> tuple[float, float, float]:
    """ECEF metres -> geodetic ``(lat_rad, lon_rad, alt_m)``.

    Algorithm: Bowring's closed-form latitude estimate, then fixed-point
    refinement of ``lat`` against the height. Altitude uses
    ``h = p cos(lat) + z sin(lat) - a sqrt(1 - e2 sin^2(lat))``, which (unlike
    ``p / cos(lat) - N``) stays accurate at the poles.

    Longitude is mathematically undefined on the polar axis (``p == 0``); it is
    returned as 0.0 there.

    Raises:
        ValueError: if any coordinate is NaN/inf, or the point is the Earth's
            centre (latitude undefined). Without this, NaN input would be
            silently turned into a plausible-looking latitude by range clamping.
    """
    p = _hypot(x, y)
    if not math.isfinite(p + z):
        raise ValueError(f"ECEF coordinates must be finite, got ({x}, {y}, {z})")
    if p == 0.0 and z == 0.0:
        raise ValueError("ECEF point at the Earth's centre has no geodetic latitude")

    # Bowring's closed-form start (s^3 / c^3 spelled as products: faster than **).
    theta = _atan2(z * WGS84_A, p * WGS84_B)
    sin_t, cos_t = _sin(theta), _cos(theta)
    lat = _atan2(
        z + WGS84_EP2 * WGS84_B * sin_t * sin_t * sin_t,
        p - WGS84_E2 * WGS84_A * cos_t * cos_t * cos_t,
    )
    alt = 0.0
    for _ in range(_MAX_REFINEMENTS):
        sin_lat = _sin(lat)
        w = _sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        n = WGS84_A / w
        # Altitude from the *current* latitude. d(alt)/d(lat) is exactly zero at
        # the solution, so once a step is < 1e-12 rad this value is already
        # correct to ~1e-17 m and no final recompute is needed.
        alt = p * _cos(lat) + z * sin_lat - WGS84_A * w
        refined = _atan2(z, p * (1.0 - WGS84_E2 * n / (n + alt)))
        done = abs(refined - lat) < _REFINE_TOL_RAD
        lat = refined
        if done:
            break
    return lat, _atan2(y, x), alt


def geo_to_ecef(pos: GeoPosition) -> tuple[float, float, float]:
    """Convert a WGS84 :class:`GeoPosition` to ECEF ``(X, Y, Z)`` in metres."""
    return geodetic_rad_to_ecef(math.radians(pos.lat), math.radians(pos.lon), pos.alt_m)


def ecef_to_geo(x: float, y: float, z: float) -> GeoPosition:
    """Convert ECEF metres to a WGS84 :class:`GeoPosition`.

    See :func:`ecef_to_geodetic_rad` for the algorithm and the ``ValueError``
    cases.
    """
    lat, lon, alt = ecef_to_geodetic_rad(x, y, z)
    return _to_geo_position(lat, lon, alt)


def _to_geo_position(lat_rad: float, lon_rad: float, alt_m: float) -> GeoPosition:
    """Build a :class:`GeoPosition`, clamping the last-ulp overshoot of
    ``degrees(pi/2)`` so the domain type's range check can never trip."""
    return GeoPosition(
        lat=max(-90.0, min(90.0, math.degrees(lat_rad))),
        lon=max(-180.0, min(180.0, math.degrees(lon_rad))),
        alt_m=alt_m,
    )
