"""Physical and model constants used by ``libraries.physics``.

All values are plain floats in SI units unless the name says otherwise.
"""

from __future__ import annotations

#: Speed of light in vacuum, m/s (exact, SI definition).
SPEED_OF_LIGHT_M_S: float = 299_792_458.0

#: Mean Earth radius used by the haversine distance, m (spherical model;
#: deliberately *not* WGS84 — see ``libraries.physics.distance``).
EARTH_MEAN_RADIUS_M: float = 6_371_000.0

#: Thermal noise power density at the reference temperature (290 K), dBm/Hz.
#: ``10*log10(k*T0*1000)`` is about -173.98; the engineering value -174 is used
#: because it is the figure in architecture doc §9.
THERMAL_NOISE_DBM_PER_HZ: float = -174.0

#: Constant of the km/MHz form of free-space path loss, dB (architecture doc §9,
#: §24). The exact value ``20*log10(4*pi*1e9/c)`` is 32.4476 dB; the customary
#: rounded figure 32.44 dB is used so results match the published reference
#: case (10 km @ 145.5 MHz = 95.6973 dB). The difference is below 0.008 dB.
FSPL_CONSTANT_DB: float = 32.44

#: Minimum slant range, m, used by the free-space model. Two radios closer than
#: this are treated as being exactly this far apart for *path-loss purposes*
#: (policy for architecture §5.5: clamp, never crash).
MIN_DISTANCE_M: float = 1.0

#: Margin (dB) at or above which a link is classified ``UP``.
LINK_UP_MARGIN_DB: float = 10.0

#: Margin (dB) at or above which (and below ``LINK_UP_MARGIN_DB``) a link is
#: classified ``MARGINAL``. Below this the link is ``DOWN``.
LINK_MARGINAL_MARGIN_DB: float = 0.0
