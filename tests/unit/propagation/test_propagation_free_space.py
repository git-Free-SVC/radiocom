"""FreeSpaceModel: contract-level behaviour, fields, determinism, hostile radios."""

from __future__ import annotations

import dataclasses
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter
from libraries.domain.rf_results import PropagationResult
from libraries.physics.constants import MIN_DISTANCE_M, SPEED_OF_LIGHT_M_S
from libraries.physics.distance import (
    haversine_distance_m,
    slant_range_m,
)
from libraries.physics.errors import PhysicsInputError
from libraries.physics.propagation import free_space_path_loss_db
from libraries.plugin_sdk.propagation import PropagationModel
from services.propagation import FreeSpaceModel, FreeSpaceValidityDomain

ANT = Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0)


"""FreeSpaceModel: contract-level behaviour, fields, determinism, hostile radios."""


def make_radio(
    rid: str = "R",
    *,
    lat: float = 45.0,
    lon: float = 6.0,
    alt: float = 0.0,
    center_hz: float = 145.5e6,
    bw_hz: float = 12.5e3,
    power_w: float = 10.0,
    cable_db: float = 0.0,
    gain: float = 2.15,
) -> Radio:
    return Radio(
        id=rid,
        frequency=Frequency(center_hz=center_hz, bandwidth_hz=bw_hz),
        transmitter=Transmitter(power_watt=power_w, cable_loss_db=cable_db),
        receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
        antenna=dataclasses.replace(ANT, gain_dBi=gain),
        position=GeoPosition(lat=lat, lon=lon, alt_m=alt),
    )


@pytest.fixture
def pair() -> tuple[Radio, Radio]:
    return make_radio("TX"), make_radio("RX", lat=45.09)


model = FreeSpaceModel()


# ------------------------------ conformance -------------------------------
def test_conforms_to_protocol_and_name() -> None:
    # noinspection protocol
    assert isinstance(model, PropagationModel)
    assert model.name == "free_space"


def test_validity_domain_values_and_corners() -> None:
    dom = model.validity_domain()
    assert isinstance(dom, FreeSpaceValidityDomain)
    assert dom.min_freq_hz < dom.max_freq_hz
    assert dom.min_distance_m < dom.max_distance_m
    assert dom.requires_terrain is False
    for d in (dom.min_distance_m, dom.max_distance_m):
        for f in (dom.min_freq_hz, dom.max_freq_hz):
            assert free_space_path_loss_db(d, f) >= 0.0, (d, f)
    with pytest.raises(dataclasses.FrozenInstanceError):
        dom.min_freq_hz = 1.0  # type: ignore[misc]


# ----------------------------- reference values ---------------------------
def test_reference_case(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    r = model.evaluate(tx, rx)
    assert r.path_loss_db == pytest.approx(95.70, abs=0.02)
    assert r.rx_power_dbm == pytest.approx(-51.40, abs=0.02)
    d = slant_range_m(tx.position, rx.position)
    assert d == pytest.approx(10_007.5, abs=1.0)
    assert r.path_loss_db == pytest.approx(free_space_path_loss_db(d, 145.5e6), abs=1e-12)


def test_result_fields_exact(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    r = model.evaluate(tx, rx)
    d = haversine_distance_m(tx.position, rx.position)
    assert isinstance(r, PropagationResult)
    assert r.delay_s == pytest.approx(d / SPEED_OF_LIGHT_M_S, rel=1e-12)
    assert r.delay_s == pytest.approx(33.38e-6, abs=0.01e-6)
    assert r.doppler_hz == 0.0
    assert r.los is True
    assert r.multipath == ()
    assert r.fading_db == 0.0


def test_cable_loss_and_gain_flow_through(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    base = model.evaluate(tx, rx)
    lossy = model.evaluate(make_radio("TX", cable_db=3.0), rx)
    assert base.rx_power_dbm - lossy.rx_power_dbm == pytest.approx(3.0, abs=1e-9)
    assert lossy.path_loss_db == base.path_loss_db
    hi_gain = model.evaluate(make_radio("TX", gain=12.15), rx)
    assert hi_gain.rx_power_dbm - base.rx_power_dbm == pytest.approx(10.0, abs=1e-9)
    hi_pwr = model.evaluate(make_radio("TX", power_w=100.0), rx)
    assert hi_pwr.rx_power_dbm - base.rx_power_dbm == pytest.approx(10.0, abs=1e-9)


def test_uses_rx_gain_not_tx_gain_twice(pair: tuple[Radio, Radio]) -> None:
    tx, _ = pair
    rx_hi = make_radio("RX", lat=45.09, gain=12.15)
    base = model.evaluate(tx, make_radio("RX", lat=45.09))
    assert model.evaluate(tx, rx_hi).rx_power_dbm - base.rx_power_dbm == pytest.approx(10.0)


# ------------------------------ determinism -------------------------------
def test_deterministic_repeat_bit_identical(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    first = model.evaluate(tx, rx)
    for _ in range(1000):
        assert model.evaluate(tx, rx) == first


@pytest.mark.parametrize("seed", [None, 0, 1, 42, -1, 2**63])
def test_independent_of_seed(pair: tuple[Radio, Radio], seed: int | None) -> None:
    tx, rx = pair
    assert model.evaluate(tx, rx, seed=seed) == model.evaluate(tx, rx)


def test_threads_identical_and_inputs_unchanged(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    snapshot = (dataclasses.astuple(tx), dataclasses.astuple(rx))
    expected = model.evaluate(tx, rx)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: model.evaluate(tx, rx), range(4000)))
    assert all(r == expected for r in results)
    assert (dataclasses.astuple(tx), dataclasses.astuple(rx)) == snapshot


def test_swapping_symmetric_radios_same_path_loss() -> None:
    a = make_radio("A", lat=10.0, lon=20.0, alt=100.0)
    b = make_radio("B", lat=10.5, lon=20.7, alt=900.0)
    assert model.evaluate(a, b).path_loss_db == model.evaluate(b, a).path_loss_db


# ------------------------- geometry edge behaviour -------------------------
def test_coincident_radios_clamped_to_min_distance() -> None:
    a, b = make_radio("A"), make_radio("B")
    r = model.evaluate(a, b)
    assert r.path_loss_db == pytest.approx(free_space_path_loss_db(MIN_DISTANCE_M, 145.5e6))
    assert r.delay_s == 0.0
    assert math.isfinite(r.rx_power_dbm)


def test_same_latlon_different_altitude_uses_altitude() -> None:
    a, b = make_radio("A"), make_radio("B", alt=1000.0)
    r = model.evaluate(a, b)
    assert r.path_loss_db == pytest.approx(free_space_path_loss_db(1000.0, 145.5e6), abs=1e-9)
    assert r.delay_s == pytest.approx(1000.0 / SPEED_OF_LIGHT_M_S, rel=1e-12)


def test_clamp_boundary_continuous_and_monotonic() -> None:
    below = math.nextafter(MIN_DISTANCE_M, 0.0)
    above = math.nextafter(MIN_DISTANCE_M, 2.0)
    base = make_radio("A")
    pls = [
        model.evaluate(base, make_radio("B", alt=h)).path_loss_db
        for h in (0.0, 1e-9, below, MIN_DISTANCE_M, above, 2.0)
    ]
    assert pls == sorted(pls)
    assert pls[2] == pls[3]  # clamped region is flat
    assert abs(pls[4] - pls[3]) < 1e-9  # no jump 1 ulp above the clamp


def test_near_field_floor_returns_zero_not_negative() -> None:
    # 1 kHz at 1 m: raw FSPL is -87.56 dB. Outside the domain; floored at 0.
    tx = make_radio("A", center_hz=1e3)
    rx = make_radio("B", alt=1.0)
    assert free_space_path_loss_db(1.0, 1e3) < 0.0
    r = model.evaluate(tx, rx)
    assert r.path_loss_db == 0.0
    assert math.isfinite(r.rx_power_dbm)


def test_frequency_mismatch_uses_tx_frequency_no_error(pair: tuple[Radio, Radio]) -> None:
    tx, _ = pair
    rx_other = make_radio("RX", lat=45.09, center_hz=433e6)
    assert model.evaluate(tx, rx_other) == model.evaluate(tx, make_radio("RX", lat=45.09))


def test_path_loss_independent_of_antenna_height_mvp(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    tall = dataclasses.replace(tx, antenna=dataclasses.replace(tx.antenna, height_m=500.0))
    assert model.evaluate(tall, rx) == model.evaluate(tx, rx)


def test_far_distances_and_frequency_extremes_finite() -> None:
    tx = make_radio("A", lat=0.0, lon=0.0, center_hz=100e9)
    rx = make_radio("B", lat=0.0, lon=180.0, alt=3.6e7)
    r = model.evaluate(tx, rx)
    assert all(math.isfinite(v) for v in (r.path_loss_db, r.rx_power_dbm, r.delay_s))


# ------------------------------ hostile input ------------------------------
@pytest.mark.parametrize("power", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_bad_power(power: float, pair: tuple[Radio, Radio]) -> None:
    _, rx = pair
    with pytest.raises(PhysicsInputError, match="power_watt"):
        model.evaluate(make_radio("TX", power_w=power), rx)


@pytest.mark.parametrize("hz", [math.nan, math.inf])
def test_nonfinite_frequency_defense_in_depth(hz: float, pair: tuple[Radio, Radio]) -> None:
    """The model must reject a non-finite frequency even if the foundation type let it in.

    Before the foundation fix, ``Frequency(nan, ...)`` was constructible; after it, it is
    not. To keep testing the model's own defence in BOTH worlds, build a valid radio and
    force the bad value past ``Frequency.__post_init__`` with ``object.__setattr__``.
    """
    _, rx = pair
    tx = make_radio("TX")
    object.__setattr__(tx.frequency, "center_hz", hz)
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        model.evaluate(tx, rx)


@pytest.mark.parametrize("hz", [math.nan, math.inf])
def test_foundation_may_reject_nonfinite_frequency_itself(hz: float) -> None:
    """Either outcome is acceptable: the foundation rejects it, or the model does."""
    try:
        tx = make_radio("TX", center_hz=hz)
    except ValueError:
        return  # foundation hardened (see proposal 0001)
    with pytest.raises(PhysicsInputError, match="frequency_hz"):
        model.evaluate(tx, make_radio("RX", lat=45.09))


def with_position(radio: Radio, lat: float, lon: float, alt: float) -> Radio:
    """Return ``radio`` with a position that bypasses ``GeoPosition`` validation.

    The foundation's ``GeoPosition`` rejects bad lat/lon at construction (and does not check
    ``alt_m``), so the model's own validation can only be exercised by forcing the value in
    afterwards. The model reads only ``.lat/.lon/.alt_m``, so a duck-typed object is enough.
    """
    forced = dataclasses.replace(radio)  # new frozen instance; never mutate shared fixtures
    object.__setattr__(forced, "position", SimpleNamespace(lat=lat, lon=lon, alt_m=alt))
    return forced


@pytest.mark.parametrize(
    ("lat", "lon", "alt"),
    [
        (91.0, 0.0, 0.0),
        (-91.0, 0.0, 0.0),
        (0.0, 181.0, 0.0),
        (math.nan, 0.0, 0.0),
        (0.0, math.nan, 0.0),
        (0.0, 0.0, math.nan),
        (0.0, 0.0, math.inf),
    ],
)
def test_bad_position(lat: float, lon: float, alt: float, pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    bad = with_position(make_radio("BAD"), lat, lon, alt)
    with pytest.raises(PhysicsInputError):
        model.evaluate(tx, bad)
    with pytest.raises(PhysicsInputError):
        model.evaluate(bad, rx)


@pytest.mark.parametrize(
    ("lat", "lon", "alt"),
    [(91.0, 0.0, 0.0), (0.0, 181.0, 0.0), (math.nan, 0.0, 0.0), (0.0, math.nan, 0.0)],
)
def test_foundation_or_model_rejects_bad_position(
    lat: float, lon: float, alt: float, pair: tuple[Radio, Radio]
) -> None:
    """Either outcome is fine: GeoPosition refuses it, or the model raises PhysicsInputError."""
    tx, _ = pair
    try:
        rx = make_radio("RX", lat=lat, lon=lon, alt=alt)
    except (ValueError, TypeError):
        return
    with pytest.raises(PhysicsInputError):
        model.evaluate(tx, rx)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_bad_gain_and_cable(bad: float, pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    with pytest.raises(PhysicsInputError):
        model.evaluate(make_radio("TX", gain=bad), rx)
    with pytest.raises(PhysicsInputError):
        model.evaluate(tx, make_radio("RX", lat=45.09, gain=bad))
    with pytest.raises(PhysicsInputError):
        model.evaluate(make_radio("TX", cable_db=bad), rx)


# --------------------------- fuzz / sweep / perf ---------------------------
def test_fuzz_random_radios_never_crash_or_emit_nonfinite() -> None:
    rng = random.Random(8)
    specials = [
        0.0,
        -0.0,
        1e-300,
        1e300,
        -1e300,
        math.nan,
        math.inf,
        -math.inf,
        5e-324,
        91.0,
        181.0,
    ]

    def val(lo: float, hi: float) -> float:
        return rng.choice(specials) if rng.random() < 0.15 else rng.uniform(lo, hi)

    ok = errors = 0
    for _ in range(20_000):
        try:
            tx = make_radio(
                lat=val(-90, 90),
                lon=val(-180, 180),
                alt=val(-500, 4e7),
                center_hz=abs(val(1e3, 1e11)) or 1.0,
                power_w=val(-1, 1e3),
                cable_db=val(0, 10),
                gain=val(-5, 30),
            )
            rx = make_radio("RX", lat=val(-90, 90), lon=val(-180, 180), alt=val(-500, 4e7))
        except ValueError:  # Frequency() validation in the foundation type
            continue
        try:
            r = model.evaluate(tx, rx, seed=rng.choice([None, 1, 2]))
        except PhysicsInputError:
            errors += 1
            continue
        ok += 1
        assert all(math.isfinite(v) for v in (r.path_loss_db, r.rx_power_dbm, r.delay_s))
        assert r.path_loss_db >= 0.0
    assert ok > 5000 and errors > 100  # both branches genuinely exercised


def test_performance_100k_evaluations(pair: tuple[Radio, Radio]) -> None:
    tx, rx = pair
    n = 100_000
    t0 = time.perf_counter()
    for _ in range(n):
        model.evaluate(tx, rx)
    elapsed = time.perf_counter() - t0
    print(f"\nBENCH evaluate: {n} calls in {elapsed:.3f}s = {elapsed / n * 1e9:.0f} ns/call")
    assert elapsed < 10.0  # generous bound: only catches pathological slowdowns
