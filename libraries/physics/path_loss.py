"""Free-space path loss (Friis), in the log domain.

``FSPL(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44``

Implemented as ``20*log10(d_m) + 20*log10(f_Hz) - 180 + 32.44`` — algebraically
identical (``20*log10(1e-3) + 20*log10(1e-6) = -180``) but it never divides
before taking the logarithm, so denormal distances cannot underflow to
``log10(0)``.

Sources: H. T. Friis, Proc. IRE 34(5), 1946; ITU-R P.525; architecture doc §9.

Precision: ``math.log10`` double precision; relative error of the result is
below ~1e-15 dB per decade. The rounded constant 32.44 (exact value 32.4476)
introduces a *systematic* offset of at most 0.0076 dB — see
``constants.FSPL_CONSTANT_DB``.
"""

from __future__ import annotations

import math

from libraries.physics import _validate
from libraries.physics.constants import FSPL_CONSTANT_DB

# 20*log10(1e3) + 20*log10(1e6) = 180 dB: converts the km/MHz form to m/Hz.
_M_HZ_OFFSET_DB: float = 180.0


def free_space_path_loss_db(distance_m: float, frequency_hz: float) -> float:
    """Free-space path loss in dB for ``distance_m`` metres at ``frequency_hz`` Hz.

    This is the *raw* formula: it is valid in the far field
    (``d >> wavelength``) and **can be negative** in the near field
    (``d < wavelength / 4pi``). Callers that need a physically meaningful value
    (the ``FreeSpaceModel`` does) must clamp the distance and floor the result.

    Valid input: any finite ``distance_m > 0`` and ``frequency_hz > 0``
    (including denormal values and 1e300).

    Raises:
        PhysicsInputError: for zero, negative, NaN, inf or non-numeric inputs.
    """
    d = _validate.positive("distance_m", distance_m)
    f = _validate.positive("frequency_hz", frequency_hz)
    loss = 20.0 * math.log10(d) + 20.0 * math.log10(f) - _M_HZ_OFFSET_DB + FSPL_CONSTANT_DB
    return _validate.finite_result("free-space path loss", loss)
