"""Named physical constants and engineering conventions for RF link budgets.

These are documented constants, not scenario tunables. Values that encode a
*convention* rather than a physical constant are marked as such — they are
candidates for a future ADR (task brief §5.4).
"""

from __future__ import annotations

#: Speed of light in vacuum, m/s. Used to convert a range into a delay.
SPEED_OF_LIGHT_M_S = 299_792_458.0

#: Mean Earth radius used by the spherical (haversine) distance, metres.
#:
#: A spherical approximation is deliberate: link-budget path loss does not need
#: ellipsoid accuracy. It is *not* interchangeable with Agent C's WGS84
#: ellipsoidal transforms (see the PR description).
EARTH_MEAN_RADIUS_M = 6_371_000.0

#: Constant term of the free-space path-loss engineering form
#: ``20*log10(d_km) + 20*log10(f_MHz) + 32.44``.
#:
#: The exact value is ``20*log10(4*pi*1e9/c) == 32.44778...``; the rounded
#: 32.44 form is the one used across the engineering literature and matches
#: the architecture doc §9 formula.
FSPL_CONSTANT_DB = 32.44

#: Thermal noise density at 290 K, dBm/Hz (architecture doc §9).
NOISE_DENSITY_DBM_HZ = -174.0

#: Smallest range used for a free-space path-loss computation, metres.
#:
#: Co-located radios (identical ``GeoPosition``) are degenerate but legal
#: input, and ``20*log10(0)`` is undefined. The clamp keeps the model total
#: and reproducible instead of crashing deep inside the physics code.
MIN_DISTANCE_M = 1.0

#: Link-quality convention: margin at or above this value is ``UP`` (dB).
UP_MARGIN_DB = 10.0

#: Link-quality convention: margin at or above this value still closes the
#: link (``MARGINAL``); below it the link is ``DOWN`` (dB).
MARGINAL_MARGIN_DB = 0.0
