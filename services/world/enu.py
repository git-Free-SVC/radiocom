"""WGS84 <-> local ENU (East/North/Up metres) relative to an explicit origin.

The origin is ALWAYS supplied by the caller: the frozen scenario schema defines
none, and choosing one here would hide that gap (see PR notes).

Two ways in, same numbers:

* :func:`geo_to_enu` / :func:`enu_to_geo` -- one-shot functions, simplest for
  occasional conversions.
* :class:`ENUFrame` -- binds an origin once and precomputes its ECEF position
  and rotation. Use it when converting many positions against one origin (the
  simulation loop): it is ~2x faster per call and has batch methods.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from libraries.domain.position import ENUPosition, GeoPosition

from .geodesy import _to_geo_position, ecef_to_geodetic_rad, geodetic_rad_to_ecef

_radians = math.radians


@dataclass(frozen=True, slots=True)
class ENUFrame:
    """A local East-North-Up frame tangent to the WGS84 ellipsoid at ``origin``.

    Immutable. The rotation rows are::

        east  = (-sin lon0,            cos lon0,            0       )
        north = (-sin lat0 cos lon0,  -sin lat0 sin lon0,   cos lat0 )
        up    = ( cos lat0 cos lon0,   cos lat0 sin lon0,   sin lat0 )

    applied to ``ECEF(point) - ECEF(origin)``; the inverse uses the transpose.
    """

    origin: GeoPosition
    _ecef0: tuple[float, float, float] = field(init=False, repr=False, compare=False)
    _rot: tuple[float, float, float, float, float, float, float, float, float] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        lat0, lon0 = _radians(self.origin.lat), _radians(self.origin.lon)
        sin_lat, cos_lat = math.sin(lat0), math.cos(lat0)
        sin_lon, cos_lon = math.sin(lon0), math.cos(lon0)
        object.__setattr__(self, "_ecef0", geodetic_rad_to_ecef(lat0, lon0, self.origin.alt_m))
        east_row = (-sin_lon, cos_lon, 0.0)
        north_row = (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat)
        up_row = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)
        object.__setattr__(self, "_rot", (*east_row, *north_row, *up_row))

    # -- geodetic -> ENU ----------------------------------------------------
    def to_enu(self, pos: GeoPosition) -> ENUPosition:
        """Express ``pos`` as East/North/Up metres in this frame."""
        x, y, z = geodetic_rad_to_ecef(_radians(pos.lat), _radians(pos.lon), pos.alt_m)
        x0, y0, z0 = self._ecef0
        dx, dy, dz = x - x0, y - y0, z - z0
        ex, ey, _, nx, ny, nz, ux, uy, uz = self._rot
        return ENUPosition(
            east_m=ex * dx + ey * dy,
            north_m=nx * dx + ny * dy + nz * dz,
            up_m=ux * dx + uy * dy + uz * dz,
        )

    def to_enu_many(self, positions: Iterable[GeoPosition]) -> list[ENUPosition]:
        """:meth:`to_enu` over many positions (same results, less overhead)."""
        x0, y0, z0 = self._ecef0
        ex, ey, _, nx, ny, nz, ux, uy, uz = self._rot
        to_ecef, radians, make = geodetic_rad_to_ecef, _radians, ENUPosition
        out: list[ENUPosition] = []
        append = out.append
        for pos in positions:
            x, y, z = to_ecef(radians(pos.lat), radians(pos.lon), pos.alt_m)
            dx, dy, dz = x - x0, y - y0, z - z0
            append(
                make(
                    ex * dx + ey * dy,
                    nx * dx + ny * dy + nz * dz,
                    ux * dx + uy * dy + uz * dz,
                )
            )
        return out

    # -- ENU -> geodetic ----------------------------------------------------
    def to_geo(self, enu: ENUPosition) -> GeoPosition:
        """Inverse of :meth:`to_enu`, back to a WGS84 :class:`GeoPosition`."""
        x0, y0, z0 = self._ecef0
        ex, ey, _, nx, ny, nz, ux, uy, uz = self._rot
        e, n, u = enu.east_m, enu.north_m, enu.up_m
        lat, lon, alt = ecef_to_geodetic_rad(
            x0 + ex * e + nx * n + ux * u,
            y0 + ey * e + ny * n + uy * u,
            z0 + nz * n + uz * u,
        )
        return _to_geo_position(lat, lon, alt)

    def to_geo_many(self, enus: Iterable[ENUPosition]) -> list[GeoPosition]:
        """:meth:`to_geo` over many positions."""
        return [self.to_geo(enu) for enu in enus]


@lru_cache(maxsize=32)
def _frame_for(origin: GeoPosition) -> ENUFrame:
    """Memoised frame per origin (``GeoPosition`` is frozen, hence hashable), so
    the one-shot functions below don't rebuild the frame on every call."""
    return ENUFrame(origin)


def geo_to_enu(pos: GeoPosition, origin: GeoPosition) -> ENUPosition:
    """One-shot :meth:`ENUFrame.to_enu`. For many points, build an ENUFrame."""
    return _frame_for(origin).to_enu(pos)


def enu_to_geo(enu: ENUPosition, origin: GeoPosition) -> GeoPosition:
    """One-shot :meth:`ENUFrame.to_geo`. For many points, build an ENUFrame."""
    return _frame_for(origin).to_geo(enu)
