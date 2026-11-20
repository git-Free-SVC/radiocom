# Agent F validation report

This report records the isolated Windows validation performed while creating
the Agent F archive. The temporary verification tree used copies of the frozen
Wave 0 contract and SDK files; the RADIOCOM project checkout was not edited.

## Evidence

- Environment: Windows, Python 3.13.9, NumPy 2.3.4, pytest available.
- Unit/stress suite: 63 passed. The full suite also passed in each of two
  end-to-end `run_wave2.py` invocations.
- Frozen contract: all five codec targets passed all 5 unmodified tests in
  both runner invocations (25 contract tests per invocation).
- Runner: executed twice from the parent workspace rather than its root;
  W2-1 through W2-10 gates, AST source manifest, and public imports passed.
- No Git command was run. No files in the RADIOCOM source checkout were
  written, changed, or used as an extraction destination.

## Stress categories

- **A — Golden/numeric references:** 30 independently tabulated BER points (six Eb/N0 values for each of five codecs),
  ten bandwidth anchors, and fixed
  BPSK/QPSK/OOK/FSK/OFDM signal vectors. Maximum observed BER error against the
  recorded table was `0.0`; tested bandwidth formula anchors were exact.
- **B — Invariants:** 10,000 seeded monotonicity and bandwidth-scaling cases
  per codec; 10,000 noiseless bits per single-carrier codec and 10,000 complete
  OFDM frames; two 30,000-bit AWGN simulations inside four-sigma Wilson
  intervals; repeated deterministic and shared-instance concurrency checks.
- **C — Hostile inputs:** zero, negative, NaN, infinities, tiny positive and
  smallest-subnormal rates, `1e18`/`1e300`, invalid bit arrays, malformed IQ,
  incomplete symbols/frames, invalid worker metadata, payload-length errors,
  mismatched IDs, remote errors, timeouts, and repeated close.
- **D — Contract/determinism:** five codecs × five frozen contract tests;
  1,000 repeated modulation calls per codec; shared-codec multithread check;
  inputs unchanged.
- **E — Sweep/accuracy:** 50,000 distinct BER/bandwidth model combinations.
  Maximum observed OFDM active-bin error was `2.49e-16`, guard/DC error
  `1.25e-16`, and FSK phase-step error `5.56e-17` on this host.
- **F — Performance:** 100,000 BPSK bits modulated/demodulated in `0.012685 s`
  (`126.8 ns/bit`); 100,000 BER plus 100,000 bandwidth calls in `0.266789 s`
  (`1,333.9 ns/call`). Both are below the 5 s workload bound. These are local
  measurements, not a cross-machine performance guarantee.

Hypothesis was not used; deterministic test data uses `random.Random(1234)` or
`numpy.random.default_rng(1234)`. One defect was found and fixed: OFDM's QPSK
symbol vector was flattened before assignment to active bins. Regression:
`test_regression_ofdm_qpsk_bits_preserve_frame_axis`.

GNU Radio and PyZMQ are not installed in this environment. The optional worker
runtime was not smoke-tested; import isolation, protocol validation, worker
dispatch, adapter errors, and lifecycle were tested with a fake transport.
