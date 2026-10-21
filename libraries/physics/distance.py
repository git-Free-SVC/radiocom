"""Geographic distance helpers for radio link budgets.

Two distances are provided, and they answer different questions:

``haversine_distance_m``
    The *surface* (great-circle) distance between two :class:`GeoPosition`
    values on a sphere of mean Earth radius. Altitude is ignored.

``slant_range_m``
    The 3D *slant range* between the same two points: the surface distance
    combined with the altitude difference. This is the distance a
    free-space path-loss computation uses, because a link between two radios
    at different heights is not a link along the surface.

Both are deliberately spherical. Precise geodesy (WGS84 ellipsoid, ECEF/ENU
frames) belongs to the World Engine service; see the PR description for the
known duplication between the two packages.
"""

from __future__ import annotations

import math

from libraries.domain.position import GeoPosition

from ._validate import finite_float, finite_result
from .constants import EARTH_MEAN_RADIUS_M
from .errors import PhysicsInputError


def _validated_position(position: GeoPosition, name: str) -> tuple[float, float, float]:
    """Return ``(lat, lon, alt_m)`` of ``position`` after validating it.

    Validation lives in the physics package (task brief §5.12) rather than in
    the frozen domain types, because the frozen types do not reject every
    non-finite value (``GeoPosition`` allows a NaN altitude, for example).
    """
    try:
        lat = position.lat
        lon = position.lon
        alt_m = position.alt_m
    except AttributeError as exc:  # pragma: no cover - defensive
        raise PhysicsInputError(
            f"{name} must be a GeoPosition with lat/lon/alt_m; got {position!r}"
        ) from exc

    lat = finite_float(f"{name}.lat", lat)
    lon = finite_float(f"{name}.lon", lon)
    alt_m = finite_float(f"{name}.alt_m", alt_m)

    if not -90.0 <= lat <= 90.0:
        raise PhysicsInputError(f"{name}.lat must be in [-90, 90]; got {lat!r}")
    if not -180.0 <= lon <= 180.0:
        raise PhysicsInputError(f"{name}.lon must be in [-180, 180]; got {lon!r}")
    return lat, lon, alt_m


def _haversine_validated(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance between two already validated coordinate pairs."""
    if lat_a == lat_b and (lon_a == lon_b or abs(lat_a) == 90.0):
        return 0.0

    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(math.remainder(lon_b - lon_a, 360.0))

    cos_phi_a = math.cos(phi_a)
    cos_phi_b = math.cos(phi_b)
    sin_half_delta_phi = math.sin(delta_phi / 2.0)
    sin_half_delta_lambda = math.sin(delta_lambda / 2.0)

    hav = sin_half_delta_phi**2 + cos_phi_a * cos_phi_b * sin_half_delta_lambda**2
    hav = min(1.0, max(0.0, hav))

    # 1 - hav, evaluated without the cancellation of subtracting from one.
    complement = (
        math.sin((phi_a + phi_b) / 2.0) ** 2
        + cos_phi_a * cos_phi_b * math.cos(delta_lambda / 2.0) ** 2
    )
    complement = min(1.0, max(0.0, complement))

    central_angle = 2.0 * math.atan2(math.sqrt(hav), math.sqrt(complement))
    return finite_result("haversine_distance_m", EARTH_MEAN_RADIUS_M * central_angle)


def haversine_distance_m(a: GeoPosition, b: GeoPosition) -> float:
    """Return the great-circle surface distance between ``a`` and ``b``, in metres.

    Uses a spherical Earth of mean radius ``EARTH_MEAN_RADIUS_M`` (6 371 000 m).
    Altitude is ignored: use :func:`slant_range_m` when the altitude
    difference matters.

    Numerical notes:

    * The longitude difference is wrapped with :func:`math.remainder`, so
      antimeridian crossings (179.999E to 179.999W) take the short way round
      and a ``-180`` / ``+180`` pair is the same meridian.
    * The central angle is evaluated with ``atan2(sqrt(hav), sqrt(1 - hav))``
      where the complementary term is computed *directly* instead of by
      subtracting from one. Near-antipodal points otherwise lose most of the
      significant digits to cancellation.
    * Every longitude denotes the same physical point at a pole, so that case
      is short-circuited instead of relying on ``cos(pi/2)`` being exactly 0.

    Raises:
        PhysicsInputError: if either position has a non-finite or
            out-of-range latitude/longitude, or a non-finite altitude.
    """
    lat_a, lon_a, _ = _validated_position(a, "a")
    lat_b, lon_b, _ = _validated_position(b, "b")
    return _haversine_validated(lat_a, lon_a, lat_b, lon_b)


def slant_range_m(a: GeoPosition, b: GeoPosition) -> float:
    """Return the 3D slant range between ``a`` and ``b``, in metres.

    ``slant_range_m = hypot(haversine_distance_m(a, b), a.alt_m - b.alt_m)``.

    The vertical component is treated as flat, which is accurate while the
    altitude difference is small compared with the Earth radius (terrestrial
    and low-earth-orbit links). It is *not* satellite-grade geometry; a
    radio at 35 786 km altitude over a curved Earth is outside the scope of
    this approximation.

    Raises:
        PhysicsInputError: if either position is invalid, or if the altitude
            difference overflows to infinity.
    """
    lat_a, lon_a, alt_a = _validated_position(a, "a")
    lat_b, lon_b, alt_b = _validated_position(b, "b")
    surface_range = _haversine_validated(lat_a, lon_a, lat_b, lon_b)

    altitude_delta = alt_a - alt_b
    if not math.isfinite(altitude_delta):
        raise PhysicsInputError(
            f"altitude difference must be finite; a.alt_m={alt_a!r}, b.alt_m={alt_b!r}"
        )
    return finite_result("slant_range_m", math.hypot(surface_range, altitude_delta))
