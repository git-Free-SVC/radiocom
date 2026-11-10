# Agent D — Propagation engine (`libraries/physics/`, `services/propagation/`)

## What was built

- `libraries/physics/`: `haversine_distance_m`, `slant_range_m`, `free_space_path_loss_db`,
  `watts_to_dbm`/`dbm_to_watts`, `received_power_dbm`, `noise_floor_dbm`, `snr_db`,
  `link_margin_db`, `eb_n0_db`, `compute_link_budget`, `link_quality`, `PhysicsInputError`.
  Standard library only; pure functions; every invalid input raises `PhysicsInputError`.
- `services/propagation/`: `FreeSpaceModel` (implements the frozen `PropagationModel`,
  `name = "free_space"`) and the concrete `FreeSpaceValidityDomain`.
- Tests: `tests/unit/physics/` and `tests/unit/propagation/`.

## Callouts (§9 step 5)

**(a) Ownership.** Only the four owned paths above were touched. No frozen file, `pyproject.toml`,
CI, or other `services/*` directory was modified.

**(b) Dependencies.** None added. `hypothesis` was not assumed: property tests are seeded
`random.Random` loops (10,000+ cases each).

**(c) Deviations / decisions the architecture left open** (please review, ideally as an ADR):

1. `link_quality` thresholds: margin >= 10 dB UP, >= 0 dB MARGINAL, else DOWN.
2. FSPL uses the rounded constant 32.44 (the exact value is 32.4476), to match the published
   reference (10 km @ 145.5 MHz = 95.6973 dB). Systematic offset <= 0.0076 dB, tested.
3. Distance clamp 1.0 m (`MIN_DISTANCE_M`) and `path_loss_db` floored at 0.0 dB.
4. Path loss uses the 3D slant range; `Antenna.height_m` is ignored; antenna pattern and
   polarization are ignored; Doppler is 0; `delay_s` uses the unclamped range.
5. Path loss is computed at `tx.frequency.center_hz`; a tx/rx frequency mismatch does not raise.
6. `FreeSpaceValidityDomain`: 30 MHz–100 GHz, 1 m–1e9 m, no terrain.

**(d) Contract.**
`pytest tests/contract/test_propagation_model_contract.py --propagation-impl services.propagation.free_space:FreeSpaceModel` ->
4 passed.

**(e) Contract-fixture numbers.** The fixture's distance is 10007.5 m (not exactly 10 km), so
FSPL is 95.7038 dB and Pr is -51.40 dBm. Exactly 10 000 m gives 95.6973 dB (tested separately).

**(f) Stress campaign §7.1 completed.**

- Tests: 207 unit (distance 30, link budget 34, path loss 78, quality 19, sweeps 5, model 41)
    + 4 contract = 211 passing. Run 3x with different random orders, all green.
- Coverage (line + branch): 100 % of `libraries/physics` and `services/propagation`.
- Max numeric error: 5.7e-14 dB vs a 60-digit Decimal reference (5,000 random points).
- Fuzz: 20,000 random radios incl. NaN/inf/denormal/out-of-range; no crash, all outputs finite.
- Sweep: 50,000-point distance x frequency grid plus a link-budget grid; invariants hold everywhere.
- Benchmark: 100,000 `evaluate()` calls in 0.82 s (~8.2 µs/call), measured in this sandbox.
- Mutation: manual mutation check (no mutation tool available): 17/17 mutants killed.
- Defects found: none in the implementation. One error in my own test (an arithmetic slip
  in an expected DOWN case: 160 dB loss still leaves +4.3 dB margin) was fixed in the test.
- Lint/format: ruff and black (line length 100) clean.

## Requests outside my directories

- Confirm the `LinkQuality` thresholds (callout c.1) and record them in an ADR.
- Foundation `Frequency.__post_init__` accepts NaN/inf (`NaN <= 0` is False); consider
  `math.isfinite` checks there. This module defends against it regardless.
