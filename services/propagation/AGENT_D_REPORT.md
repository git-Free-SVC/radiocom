# Agent D — Propagation Engine (FreeSpace): delivery report

This is the full report for the Agent D ticket. It lives inside
`services/propagation/` because `docs/` is outside the directories this agent
owns (task brief §2), and it is the document the pull-request body points at.

**Delivered**

- `libraries/physics/` — reusable, validated RF link-budget math.
- `services/propagation/` — `FreeSpaceModel`, a real implementation of the
  frozen `PropagationModel` Protocol built on top of that math.

**Base branch.** The pull request targets `master` (the repository's default
branch — there is no `main`). `foundation-v0` is still an ancestor of this
branch (`git merge-base --is-ancestor foundation-v0 agent-d-propagation-engine`
→ true), but the branch is cut from `master` (`22d18df`) on purpose: the frozen
contract harness (`tests/contract/conftest.py`, which registers the
`--propagation-impl` flag) only exists from the wave-0 follow-up commit
onwards, so forking strictly from the tag would make the acceptance command of
§7 unusable. Every frozen path — `libraries/domain/`, `libraries/plugin_sdk/`,
`libraries/protocols/`, `tests/contract/`, `pyproject.toml` — is byte-identical
to `master`.

---

## 1. `link_quality()` thresholds — this should become an ADR

Nothing in `libraries/domain/` or `libraries/plugin_sdk/` defines what
separates `UP` / `MARGINAL` / `DOWN`, so the bands are an **engineering
convention chosen here**:

| margin | quality |
|---|---|
| `margin_db >= 10` | `LinkQuality.UP` |
| `0 <= margin_db < 10` | `LinkQuality.MARGINAL` |
| `margin_db < 0` | `LinkQuality.DOWN` |

Rationale: a positive margin is what it takes to close the link at all; 10 dB
is the buffer before the link is called solidly reliable. The thresholds live
in `libraries/physics/constants.py` as `UP_MARGIN_DB` / `MARGINAL_MARGIN_DB`,
so a future ADR can change them in one place. **This is a convention, not a
specified value, and should be promoted to an ADR.**

The classifier is exhaustive (every finite margin maps to exactly one band),
monotonic (a larger margin never maps to a worse band) and rejects NaN / ±inf
with `PhysicsInputError`.

## 2. Coincident-position handling

Two radios at the *same* `GeoPosition` are degenerate but legal input, and
`20*log10(0)` is undefined. The policy is **clamp, do not crash**: the
path-loss computation uses a minimum distance of **1 m** (`MIN_DISTANCE_M`),
which keeps the model total and reproducible instead of raising
`ValueError: math domain error` from deep inside the physics code. 1 m is a
plausible minimum antenna spacing, so the clamp is a modelling convention
rather than a physical statement.

Consequences, all tested:

- `path_loss_db` = FSPL at 1 m (not at 0 m).
- `delay_s` = **raw** slant range / c = `0.0` for co-located radios (§5.9
  defines the delay from the unclamped slant range).
- Two radios at the same latitude/longitude but **different altitudes** are
  *not* degenerate — their slant range is the altitude gap.

Locked in by `test_regression_coincident_radios_use_the_one_metre_clamp`.

## 3. Known duplication: haversine vs. Agent C's ellipsoidal geodesy

`libraries/physics/distance.py` implements a **spherical** haversine distance
on a mean-radius sphere (`EARTH_MEAN_RADIUS_M = 6 371 000 m`). Agent C (World
Engine) is independently implementing precise WGS84↔ECEF↔ENU geodesy in
`services/world/` this same wave.

The two will **not** agree to high precision: they solve related but different
problems at different precision levels. This is an intentional, known
duplication produced by Wave-1 agent isolation — **not** a bug in either
package, and not something fixable from inside `libraries/physics/`.
**Flag for the Integration Agent to rationalize later** (a shared geodesy
utility in `libraries/` may make sense once both packages exist and can be
compared side by side). Within `libraries/physics/` the spherical choice is
deliberate and documented: a link budget does not need ellipsoid accuracy to
be meaningful, and a spherical model is orders of magnitude cheaper per
evaluation than an iterative geodesic solution.

## 4. The frozen contract test — command and output

The contract test was **not modified** (neither
`tests/contract/test_propagation_model_contract.py` nor
`tests/contract/conftest.py` — `git diff master..HEAD` does not touch
`tests/contract/`).

```text
$ pytest tests/contract/ -q --propagation-impl=services.propagation.free_space:FreeSpaceModel
......................................................                   [100%]
54 passed in 0.43s

$ pytest tests/contract/test_propagation_model_contract.py -v --propagation-impl=services.propagation.free_space:FreeSpaceModel
tests/contract/test_propagation_model_contract.py::test_conforms_to_protocol PASSED
tests/contract/test_propagation_model_contract.py::test_evaluate_returns_well_formed_result PASSED
tests/contract/test_propagation_model_contract.py::test_deterministic_with_seed PASSED
tests/contract/test_propagation_model_contract.py::test_validity_domain_declared PASSED
tests/contract/test_propagation_model_contract.py::test_path_loss_grows_with_distance PASSED
tests/contract/test_propagation_model_contract.py::test_path_loss_grows_with_frequency PASSED
tests/contract/test_propagation_model_contract.py::test_more_tx_power_more_rx_power PASSED
7 passed in 0.07s
```

Other suites:

```text
$ pytest tests/unit/ -q
463 passed in 10.46s

$ pytest tests/ -q            # whole suite, contract against the default fakes
533 passed in 11.76s

$ ruff check libraries/physics services/propagation tests/unit/physics tests/unit/propagation
All checks passed!

$ black --check libraries/physics services/propagation tests/unit/physics tests/unit/propagation
19 files would be left unchanged.
```

## 5. Judgment calls (§5.8 – §5.11)

1. **Tx frequency selects the path loss.** `evaluate()` computes the path loss
   at `tx.frequency.center_hz`. If the two radios sit on different frequencies
   the model does **not** raise: whether they can hear each other is a
   spectral-overlap question (`Frequency.overlaps`, later Interference
   Engine), not a propagation question. Tested by
   `test_regression_frequency_mismatch_uses_the_transmitter_frequency`.
2. **3D slant range, not surface distance.** Path loss uses
   `slant_range_m(tx.position, rx.position)` = `hypot(haversine, Δalt)`;
   altitude is part of the geometry, and a 2D-only distance would silently
   ignore it. The vertical component is a flat-earth approximation (fine while
   `Δalt ≪ R`; it is not satellite-grade geometry — documented, not solved).
3. **`Antenna.height_m` is ignored.** Free space does not depend on antenna
   height in the MVP, so it is not added to `alt_m`.
4. **`Antenna.pattern` and `Antenna.polarization` are ignored** (boresight,
   0 dB relative gain; `Lpol = 0`). `atmospheric_loss_db = 0` and
   `shadowing_db = 0`. Receive-side cable loss is 0 dB because the frozen
   `Receiver` type has no cable-loss field.
5. **`FreeSpaceValidityDomain`** (concrete frozen dataclass in
   `services/propagation/free_space.py`): `min_freq_hz = 30 MHz`,
   `max_freq_hz = 100 GHz`, `min_distance_m = 1 m` (the clamp),
   `max_distance_m = 1e9 m` (1 000 000 km — the path-loss formula has no
   upper distance limit and the model never consults terrain),
   `requires_terrain = False`. FSPL is **non-negative at every corner** of
   that box (worst corner: 1 m / 30 MHz → **+1.98 dB**), which the test suite
   asserts. `evaluate()` never raises or warns for an out-of-domain point —
   the RF Core uses `validity_domain()` for that, per the frozen docstring.
6. **0 dB path-loss floor.** FSPL is only positive when `d·f > c/(4π)`; below
   that the raw formula goes negative (≈ −87 dB at 1 m / 1 kHz), which is
   nonsense for a passive medium. `evaluate()` therefore floors `path_loss_db`
   at `0.0`. The raw value is still available from
   `libraries.physics.free_space_path_loss_db`, so the floor stays a policy
   decision of the *model*.
7. **`seed` is accepted and deliberately ignored.** Free space has no
   stochastic component, so the result does not depend on the seed at all —
   the Protocol's determinism requirement is satisfied by construction rather
   than by a fake RNG. Every seed (`None, 0, 1, 42, -1, 2**63`) gives a
   bit-identical result, and that is now a *tested fact*.
8. **No BER from Eb/N0.** Eb/N0 is computed as a generic link-budget quantity
   only. `WaveformCodec.ber()` is a different frozen Protocol owned by a
   different agent (Wave 2, `services/dsp/`).
9. **Validation lives in `libraries/physics/`**, not in the domain types:
   every physics function validates its own inputs and raises
   `PhysicsInputError` (a `ValueError` subclass) naming the offending
   argument and value. No raw `ValueError: math domain error` and no
   `OverflowError` ever escapes.

## 6. Stress campaign report (§7.1)

`hypothesis` is **not** available and `pyproject.toml` is off-limits, so the
property loops use seeded `random.Random(1234)`-style generators (fixed seeds
→ always reproducible). The campaign lives in `tests/unit/physics/` and
`tests/unit/propagation/`.

### 6.1 Counts per category

| Category | Where | Count |
|---|---|---|
| **A — independent golden values** | `tests/unit/physics/test_stress_numeric.py` | **30** golden FSPL points (1 kHz … 1 THz, 1 m … 1 000 000 km) + 2 max-error tests |
| **B — invariants** | `tests/unit/physics/test_stress_invariants.py` | **21** properties × **10 000** seeded cases = **210 000** sampled cases |
| **C — hostile inputs** | `tests/unit/physics/test_stress_hostile.py` | **72** explicit test items |
| **D — contract / determinism / concurrency** | `tests/unit/propagation/test_stress_free_space.py` + frozen contract | **13** model items + **7** frozen contract tests |
| **E — sweeps and numeric accuracy** | `tests/unit/physics/test_stress_numeric.py` | **50 000**-point grid + **2 000**-point random grid against a 60-digit `decimal` reference |
| **F — performance** | `tests/unit/propagation/test_stress_free_space.py` | **100 000** `evaluate()` calls |
| **G — regressions** | `tests/unit/physics/test_regressions.py`, `tests/unit/propagation/test_regression_free_space.py` | **11** named `test_regression_*` tests |

Category B properties: FSPL strictly increasing with distance and with
frequency; doubling adds 6.020599913 dB and ten-folding adds 20 dB (distance
*and* frequency); haversine symmetry, identity, triangle inequality, one
degree of latitude (111 194.93 m), longitude spacing shrinking with
`cos(lat)`, antipodes ≈ π·R with no NaN, the ±180° antimeridian, the poles;
slant range = surface range at Δalt = 0, Pythagoras against the surface
distance and Δalt, symmetry; `margin = Pr − sensitivity`; `SNR = Pr − N`;
adding X dB to **each** of the five loss terms lowers Pr and margin by
exactly X; `Eb/N0 = SNR` when `bit_rate == bandwidth`; `link_quality` monotonic
and exhaustive; watts → dBm → watts within 1e-9 relative.

### 6.2 Maximum numeric error

Against an independent 60-digit `decimal` reference of
`20*log10(d_km) + 20*log10(f_MHz) + 32.44`:

- **golden set (30 points): 1.421e-14 dB**
- **2 000-point random grid (1 m … 1e9 m, 1 kHz … 1 THz): 5.684e-14 dB**

Both are asserted with a `1e-9 dB` tolerance in the test (deliberately much
looser than the observed error).

### 6.3 Benchmark

```text
100 000 evaluate() calls in 0.908 s (9 082 ns/call)
100 000 evaluate() calls in 0.913 s (9 132 ns/call)
100 000 evaluate() calls in 0.971 s (9 708 ns/call)
```

Windows 11, Python 3.13.9, 100 000 calls ≈ **0.91 – 0.97 s** (bound in the
test: 5 s, generous on purpose so CI cannot flake).

### 6.4 Defects found and fixed

| # | Defect | Fix | Regression test |
|---|---|---|---|
| 1 | `link_budget.py` raised `NameError: PhysicsInputError` instead of the named error (the class was not imported after the module was restructured) | imported it | `test_dbm_to_watts_rejects_nonfinite_or_unrepresentable_power` |
| 2 | `slant_range_m` validated both positions **twice** (directly and again through `haversine_distance_m`), doubling the validation cost per evaluation | shared `_haversine_validated()` helper — validate once | covered by the input-validation tests |
| 3 | `finite_float()` went through the generic `float()` conversion path for every argument (18 calls per evaluation) | `type(value) is float` fast path → ~9.1 µs/call | behaviour unchanged, covered by the hostile-input tests |
| 4 | The numeric sweep contained a golden point **below the 1 m clamp** (0.001 m), so the implementation and the reference disagreed by 60 dB | the clamp is a documented policy → the sweep stays above the clamp | `test_regression_fspl_below_the_clamp_uses_the_clamped_distance` |
| 5 | The random accuracy grid originally drew distances from 1e-3 m and reported a bogus "60 dB error" | grid restricted to ≥ 1 m, clamp documented | same as #4 |
| 6 | The longitude-spacing invariant used the approximation `R·cos(lat)·Δλ`, which is 1.2e-5 relative away from the exact great-circle value `2R·asin(cos(lat)·sin(Δλ/2))` — **the test was wrong, not the code** | exact formula used | `test_regression_longitude_spacing_uses_the_exact_great_circle_form` |
| 7 | "One ULP above the clamp must give a strictly larger path loss" is false: `20·log10(1+2.2e-16)` is 8.7e-15 dB, below the resolution of the dB result | assertion corrected to finite + monotone | `test_regression_one_ulp_above_the_clamp_is_not_representable_in_db` |
| 8 | The duplicate stress suite left over from the previous agent-D commit (`tests/unit/physics/test_stress_physics.py`) duplicated the new suites | removed — every property it asserted is covered by the new files (golden values, monotonicity, scaling, symmetry, identity, triangle inequality, latitude/longitude spacing, antipodes, antimeridian, poles, slant range, link-budget equations, loss deltas, link quality, watts round trip, clamp edges, hostile inputs, 50 k sweep) | — |

Numerical traps inherited from the previous implementation are now pinned by
named regression tests instead of being left implicit:

| Trap | Regression test |
|---|---|
| The textbook `2·asin(sqrt(hav))` form is **0.19 m short** at the antipode (cancellation) — the implementation evaluates the complementary term directly | `test_regression_antipodal_distance_avoids_cancellation` |
| `cos(π/2)` is 6.1e-17, not 0 → two poles at different longitudes would be 8e-10 m apart | `test_regression_poles_have_no_longitude_residue` |
| Converting m → km **before** `log10` underflows a denormal distance to 0 → `log10(0)` raises | `test_regression_denormal_distance_does_not_underflow_before_log10` |
| `bandwidth / bit_rate` overflows to infinity for extreme but finite inputs | `test_regression_eb_n0_ratio_does_not_overflow` |

No test was weakened or deleted to make a defect go away.

## 7. Other flags for the Integration Agent

1. **`GeoPosition` (frozen) accepts a NaN altitude** — `__post_init__`
   validates lat/lon only. `libraries/physics/` validates the altitude
   itself, so the physics is safe, but the frozen type could be tightened in a
   later wave.
2. **`ValidityDomain` (frozen) is a Protocol with data members.**
   `isinstance(domain, ValidityDomain)` works (the frozen contract test relies
   on it), but `issubclass()` on it would raise `TypeError`. A concrete frozen
   dataclass `FreeSpaceValidityDomain` is provided in the service and returned
   by `validity_domain()`.
3. **The architecture document (`radiocom-architecture.md`) is not in the
   repository.** The formulas in §9/§11/§24 were taken from the task brief,
   which quotes them; the §24 reference case "10 km @ 145.5 MHz ≈ 95.7 dB" was
   re-derived independently and matches.
4. **The contract test in the repository is a slightly later revision than the
   one quoted in the brief** (7 tests instead of 4; it additionally asserts
   `isinstance(domain, ValidityDomain)`, path-loss monotonicity in distance and
   frequency, and that more transmit power gives more received power). It was
   passed **unmodified**.
5. **Pre-existing lint debt outside my directories.** `ruff check .` reports 30
   findings and `black --check .` wants to reformat 14 files — all of them
   outside `libraries/physics/`, `services/propagation/`,
   `tests/unit/physics/`, `tests/unit/propagation/` (e.g. `tools/sdk_freeze.py`,
   `tests/contract/*`, `libraries/domain/*`). They were not touched (not my
   scope). My own files are clean under the same tool versions; `ruff` and
   `black` were **not installed** in this environment, so they were installed
   into the local `.venv` (ruff 0.17.1, black 26.10.1) to run the checks the
   CI job runs.
6. **Portability.** The package is pure standard-library arithmetic (`math`,
   `decimal`, `random`, `concurrent.futures`, `time.perf_counter`) with no I/O,
   no locale, no filesystem and no platform-specific behaviour; every float
   assertion uses `pytest.approx` with an explicit tolerance (except the
   determinism tests, where exact equality is the point). **No Linux run could
   be executed locally** (no Linux runtime, no Docker daemon in this sandbox),
   so the Linux leg of the CI matrix is the first place this will be
   exercised — the CI job covers it.
7. **Not in this ticket, by design:** no TwoRay/Hata/ITM/ray-tracing model, no
   fading or multipath, no terrain/LOS or `GeodataProvider` usage, no
   interference/SINR across links, no precision geodesy, no antenna pattern /
   polarization / atmospheric / shadowing modelling, no BER curves.
