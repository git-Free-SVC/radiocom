"""World Engine: WGS84 <-> ECEF <-> ENU transforms and a terrain LOS stub.

Pure math over the frozen domain types; terrain comes only through the
``GeodataProvider`` interface.

Typical use::

    frame = ENUFrame(origin)            # bind the scenario origin once
    enus = frame.to_enu_many(geo_positions)
    result = line_of_sight(a, b, provider)
"""

from .enu import ENUFrame, enu_to_geo, geo_to_enu
from .geodesy import (
    WGS84_A,
    WGS84_B,
    WGS84_E2,
    WGS84_EP2,
    WGS84_F,
    ecef_to_geo,
    geo_to_ecef,
)
from .los import DEFAULT_SAMPLES, LOSResult, line_of_sight

__all__ = [
    "DEFAULT_SAMPLES",
    "WGS84_A",
    "WGS84_B",
    "WGS84_E2",
    "WGS84_EP2",
    "WGS84_F",
    "ENUFrame",
    "LOSResult",
    "ecef_to_geo",
    "enu_to_geo",
    "geo_to_ecef",
    "geo_to_enu",
    "line_of_sight",
]
