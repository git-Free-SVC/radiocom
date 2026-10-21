# Agent D: Propagation Engine

## Included implementation

The patch and ZIP add 12 files under the requested package and unit-test paths. The existing contract tests, frozen interfaces, domain types, `pyproject.toml`, and all other project files are unchanged.

The reusable physics package provides validated spherical haversine and 3D slant distance, free-space path loss, watts/dBm conversion, received power, thermal noise, SNR, link margin, Eb/N0, link quality, and `PhysicsInputError`. `FreeSpaceModel` implements the frozen protocol and fills every `PropagationResult` field.

## Design decisions

- Link quality uses `UP` for margin >= 10 dB, `MARGINAL` for 0 to under 10 dB, and `DOWN` below 0 dB. The frozen interfaces do not define thresholds; this convention should become an ADR.
- Distances below 1 m, including zero for co-located radios, are clamped to 1 m for FSPL. Propagation delay still uses the actual slant range, so co-located radios have zero delay.
- Surface distance uses haversine with a mean Earth radius of 6,371,000 m. FSPL uses 3D slant range, computed from surface distance and altitude difference. This is a flat vertical approximation for terrestrial links.
- Path loss uses the transmitter's center frequency when Tx/Rx frequencies differ. Received power uses Tx power, both antenna gains, path loss, and Tx cable loss. Antenna patterns, polarization loss, antenna height, atmospheric loss, and shadowing are ignored. The model sets Doppler and fading to 0, multipath to `()`, and LOS to `True`.
- The validity domain is 30 MHz–100 GHz and 1 m–1e9 m, with no terrain requirement. The minimum-frequency/minimum-distance corner has about 1.9824 dB FSPL. The maximum distance gives a broad operating envelope through 1,000,000 km. Evaluated path loss is floored at 0 dB.
- Haversine geodesy may differ slightly from the World Engine's planned ellipsoidal transforms. That duplicate is intentional for this isolated implementation and should be rationalized during integration.

## Validation

- **A — independent references:** 24 Decimal-generated FSPL golden points from 1 kHz to 100 GHz and 1 m to 1,000 km, including the specified 10 km / 145.5 MHz and contract-fixture values. Maximum observed absolute error: **4.84e-13 dB**.
- **B — invariants:** 18 seeded property loops × 10,000 samples (**180,000 loop samples**) covering FSPL monotonicity/scaling, haversine and slant-range behavior, link-budget equations/loss deltas, link-quality monotonicity, and watts/dBm round trips. The loss-delta loop checks all five path/cable/polarization/atmospheric/shadowing loss fields per sample.
- **C — hostile inputs and boundaries:** 63 focused test items cover zero/negative/subnormal/huge/nonfinite distance, frequency, bandwidth, bit rate, power and margin; coordinate and altitude limits; the 1 m clamp and adjacent ULPs; co-location; near-field flooring; and frequency mismatch.
- **D — contract, determinism, and concurrency:** frozen contract command passed **57 tests** unchanged. Unit coverage checks 1,000 repeated results, six seed values, 2,000 concurrent shared-radio calls, symmetry, exact result fields, and input immutability.
- **E — sweep and accuracy:** a **50,000-point** distance × frequency × power × bandwidth sweep passed with finite outputs. Golden-value maximum absolute error is **4.84e-13 dB**.
- **F — performance and platform:** 100,000 `evaluate()` calls took **1.120 s** (**11,204 ns/call**) on Windows with Python 3.13.9, below the 5-second bound. This environment did not provide Linux, so the Linux run remains unverified.

Commands run:

```text
pytest tests/unit/ -q
121 passed, 1 PytestCacheWarning

pytest tests/contract/ -q --propagation-impl=services.propagation.free_space:FreeSpaceModel
57 passed, 1 PytestCacheWarning
```

The warning is from pytest being unable to create its cache directory in this sandbox; both suites passed. The unit suite also passed with cache disabled (`pytest tests/unit/ -q -p no:cacheprovider`, 121 passed).

`ruff check .` and `black --check .` could not run because neither executable is installed in the environment. No dependencies or project configuration were changed. Stress properties use seeded standard-library `random.Random` loops.

## Workspace notes

The available RADIOCOM snapshot was `radiocom-w0-5-plugin-sdk-v3`. It contains the frozen propagation contract and interfaces but is not a Git checkout; it also lacks the prompt's `radiocom-architecture.md` and `ADR-000-foundation-interfaces.md`. I used the architecture and numerical requirements supplied in the task prompt. The implementation and tests were built in a workspace copy and are supplied as an additions-only patch and ZIP because the Desktop snapshot could not be modified directly. No branch or PR was created.

