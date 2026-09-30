"""Reference PropagationModel: free-space path loss (Friis). Distance-aware, so it
exercises the monotonicity clause of the contract (the old Null fake could not)."""

from __future__ import annotations

import math

from libraries.domain.radio import Radio
from libraries.domain.rf_results import PropagationResult
from libraries.plugin_sdk.propagation import ValidityDomain

_C = 299_792_458.0


class _Domain:
    min_freq_hz = 1e6
    max_freq_hz = 100e9
    min_distance_m = 1.0
    max_distance_m = 1e9
    requires_terrain = False


def _distance_m(a, b) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    ground = 2 * r * math.asin(math.sqrt(h))
    return math.hypot(ground, b.alt_m - a.alt_m)


class FreeSpaceReferenceModel:
    name = "free_space_reference"

    def validity_domain(self) -> ValidityDomain:
        return _Domain()

    def evaluate(self, tx: Radio, rx: Radio, *, seed: int | None = None) -> PropagationResult:
        d = max(_distance_m(tx.position, rx.position), _Domain.min_distance_m)
        f = tx.frequency.center_hz
        pl = 20 * math.log10(4 * math.pi * d * f / _C)
        tx_dbm = 10 * math.log10(tx.transmitter.power_watt * 1000) - tx.transmitter.cable_loss_db
        rx_dbm = tx_dbm + tx.antenna.gain_dBi + rx.antenna.gain_dBi - pl
        return PropagationResult(path_loss_db=pl, rx_power_dbm=rx_dbm, delay_s=d / _C, los=True)
