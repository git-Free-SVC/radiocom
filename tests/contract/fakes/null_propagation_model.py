"""Trivial fake: proves the contract test template is runnable before any
real Wave-1 agent implementation exists. Not used outside tests."""

from __future__ import annotations

from libraries.domain.radio import Radio
from libraries.domain.rf_results import PropagationResult
from libraries.plugin_sdk.propagation import ValidityDomain


class _FlatValidityDomain:
    min_freq_hz = 1e6
    max_freq_hz = 100e9
    min_distance_m = 0.0
    max_distance_m = 1e9
    requires_terrain = False


class NullPropagationModel:
    """Constant path loss, no fading — satisfies PropagationModel Protocol."""

    name = "null"

    def validity_domain(self) -> ValidityDomain:
        return _FlatValidityDomain()

    def evaluate(self, tx: Radio, rx: Radio, *, seed: int | None = None) -> PropagationResult:
        import math

        path_loss_db = 100.0  # arbitrary constant, deterministic by construction
        tx_power_dbm = 10.0 * math.log10(tx.transmitter.power_watt * 1000)
        rx_power_dbm = tx_power_dbm + tx.antenna.gain_dBi + rx.antenna.gain_dBi - path_loss_db
        return PropagationResult(
            path_loss_db=path_loss_db,
            rx_power_dbm=rx_power_dbm,
            los=True,
        )
