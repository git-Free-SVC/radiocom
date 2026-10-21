"""Free-space path loss.

Free space is the baseline propagation medium: no terrain, no reflections, no
fading, no absorption. It is the reference every other propagation model is
compared against, and the model that the MVP ships
(:class:`services.propagation.free_space.FreeSpaceModel`).

The engineering form used throughout the project (architecture doc §9) is::

    FSPL(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44

which is the same as ``20*log10(4*pi*d*f/c)`` with the constant rounded.
"""

from __future__ import annotations

import math

from ._validate import finite_result, non_negative_float, positive_float
from .constants import FSPL_CONSTANT_DB, MIN_DISTANCE_M


def free_space_path_loss_db(
    distance_m: float,
    frequency_hz: float,
    *,
    min_distance_m: float = MIN_DISTANCE_M,
) -> float:
    """Return the free-space path loss between two points, in dB.

    Args:
        distance_m: separation between the two radios, in metres. Must be
            finite and non-negative.
        frequency_hz: carrier frequency, in hertz. Must be finite and
            strictly positive.
        min_distance_m: smallest distance the formula is evaluated at.
            Defaults to :data:`libraries.physics.constants.MIN_DISTANCE_M`
            (1 m). Co-located radios are degenerate but legal input, and
            ``20*log10(0)`` is undefined, so the distance is clamped rather
            than crashing the caller. The clamp is a *modeling convention*,
            not a physical statement: 1 m is a plausible minimum spacing
            between two antennas.

    Returns:
        The path loss in dB. It may be negative in the near field (a
        ``distance_m * frequency_hz`` product below ``c / (4*pi)``); a passive
        medium cannot actually provide gain, so propagation models are
        expected to floor the value at 0 dB. This function returns the raw
        value so that the floor stays a policy decision of the model.

    Raises:
        PhysicsInputError: for a non-finite/negative distance, a non-finite
            or non-positive frequency, or a non-positive ``min_distance_m``.
    """
    distance = non_negative_float("distance_m", distance_m)
    frequency = positive_float("frequency_hz", frequency_hz)
    floor = positive_float("min_distance_m", min_distance_m)

    effective_distance = max(distance, floor)

    # The textbook form uses km and MHz. Converting first would underflow for
    # denormal metres, so the unit change is applied to the logarithm
    # instead: log10(d_km) == log10(d_m) - 3.
    result = (
        20.0 * (math.log10(effective_distance) - 3.0)
        + 20.0 * (math.log10(frequency) - 6.0)
        + FSPL_CONSTANT_DB
    )
    return finite_result("free_space_path_loss_db", result)
