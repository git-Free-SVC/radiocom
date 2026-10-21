"""Geographic distance helpers used by radio link-budget calculations."""

from __future__ import annotations

import math

from libraries.domain.position import GeoPosition

from .errors import PhysicsInputError

EARTH_MEAN_RADIUS_M = 6_371_000.0
MIN_DISTANCE_M = 1.0


def _finite_float(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhysicsInputError(f"{name} must be a finite number; got {value!r}") from exc
    if not math.isfinite(number):
        raise PhysicsInputError(f"{name} must be finite; got {value!r}")
    return number


def _validated_position(position: GeoPosition, name: str) -> tuple[float, float, float]:
    try:
        lat = _finite_float(f"{name}.lat", position.lat)
        lon = _finite_float(f"{name}.lon", position.lon)
        alt = _finite_float(f"{name}.alt_m", position.alt_m)
    except AttributeError as exc:
        raise PhysicsInputError(f"{name} must be a GeoPosition; got {position!r}") from exc

    if not -90.0 <= lat <= 90.0:
        raise PhysicsInputError(f"{name}.lat must be in [-90, 90]; got {lat!r}")
    if not -180.0 <= lon <= 180.0:
        raise PhysicsInputError(f"{name}.lon must be in [-180, 180]; got {lon!r}")
    return lat, lon, alt


def haversine_distance_m(a: GeoPosition, b: GeoPosition) -> float:
    """Return the great-circle surface distance, ignoring altitude.

    This uses a spherical mean Earth radius and is intentionally simpler than
    ellipsoidal geodesy. Altitudes are still checked for finite values because
    they are part of each supplied position.
    """
    lat1, lon1, _ = _validated_position(a, "a")
    lat2, lon2, _ = _validated_position(b, "b")

    if lat1 == lat2 and (lon1 == lon2 or abs(lat1) == 90.0):
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon_deg = math.remainder(lon2 - lon1, 360.0)
    delta_lambda = math.radians(delta_lon_deg)

    sin_delta_phi = math.sin(delta_phi / 2.0)
    cos_phi1 = math.cos(phi1)
    cos_phi2 = math.cos(phi2)
    sin_delta_lambda = math.sin(delta_lambda / 2.0)
    cos_delta_lambda = math.cos(delta_lambda / 2.0)
    hav = sin_delta_phi**2 + cos_phi1 * cos_phi2 * sin_delta_lambda**2
    # Compute the complement separately instead of subtracting a value close
    # to one. This keeps nearly antipodal ranges accurate to floating-point
    # precision rather than losing centimeters through cancellation.
    hav_complement = math.sin((phi1 + phi2) / 2.0) ** 2 + cos_phi1 * cos_phi2 * cos_delta_lambda**2
    hav = min(1.0, max(0.0, hav))
    hav_complement = min(1.0, max(0.0, hav_complement))
    central_angle = 2.0 * math.atan2(math.sqrt(hav), math.sqrt(hav_complement))
    distance = EARTH_MEAN_RADIUS_M * central_angle
    if not math.isfinite(distance):
        raise PhysicsInputError("haversine distance result must be finite")
    return distance


def slant_range_m(a: GeoPosition, b: GeoPosition) -> float:
    """Return 3D range from spherical surface distance and altitude delta.

    The vertical component is treated as flat. This approximation is intended
    for terrestrial links where altitude differences are small compared with
    Earth's radius, not satellite-scale geodesy.
    """
    _, _, alt_a = _validated_position(a, "a")
    _, _, alt_b = _validated_position(b, "b")
    surface_range = haversine_distance_m(a, b)
    altitude_delta = alt_a - alt_b
    if not math.isfinite(altitude_delta):
        raise PhysicsInputError(
            f"altitude difference must be finite; a.alt_m={alt_a!r}, b.alt_m={alt_b!r}"
        )
    distance = math.hypot(surface_range, altitude_delta)
    if not math.isfinite(distance):
        raise PhysicsInputError("slant range result must be finite")
    return distance
