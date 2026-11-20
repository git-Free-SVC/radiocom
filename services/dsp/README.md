# RADIOCOM Wave 2 DSP package

This package supplies deterministic NumPy reference codecs for the frozen
WaveformCodec shape. It requires Python 3.10+ and NumPy; optional GNU Radio and
PyZMQ imports live only under `integrations/gnu_radio/`.

## Frozen API implemented

The API remains unchanged:

```python
class WaveformCodec(Protocol):
    name: str
    def modulate(self, bits: numpy.ndarray, sample_rate_hz: float) -> numpy.ndarray: ...
    def demodulate(self, iq: numpy.ndarray, sample_rate_hz: float) -> numpy.ndarray: ...
    def ber(self, ebn0_db: float) -> float: ...
    def occupied_bandwidth_hz(self, symbol_rate_hz: float) -> float: ...
```

All five codec classes implement all four methods. IQ output is contiguous
`complex128`; recovered bits are contiguous `uint8`. Inputs are never mutated.
Invalid inputs raise `DSPInputError(ValueError)` with the argument or framing
condition in the message. Empty one-dimensional payloads round-trip as empty
arrays; incomplete modulation symbols/OFDM frames are rejected.

## Explicit signal choices and rationale

| Codec     | Signal/frame convention                                                            | Reason and limitation                                                                     |
|-----------|------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| BPSK      | 0 -> -1, 1 -> +1; 8 repeated samples/symbol                                        | Simple exact reference signal; rectangular pulse has sidelobes                            |
| Gray QPSK | First bit sets I sign, second sets Q sign; components ±1/sqrt(2); 8 samples/symbol | Unit-magnitude symbol and one-bit Gray neighbors; odd bit counts are invalid              |
| AM/OOK    | 0 -> 0, 1 -> 1; threshold 0.5; 8 samples/symbol                                    | Small coherent binary AM model; no envelope detector or RF carrier                        |
| FM/FSK    | Continuous phase, tones ±Rs/2, Rs=Fs/8                                             | Orthogonal over one symbol, deterministic initial phase 0; educational binary FM model    |
| OFDM      | 64-point transform, active bins -8..-1,+1..+8, DC unused, CP=16                    | 32 QPSK bits / 80 samples per frame; no pilots, coding, synchronization, or channel model |

For single-carrier codecs, `sample_rate_hz` is the complex sample clock and
`Rs=Fs/8`. BPSK/QPSK/OOK bandwidth is the two-sided rectangular-pulse
null-to-null approximation `2*Rs`. FSK uses Carson's rule with deviation and
modulating frequency both `Rs/2`, giving `2*Rs`. For OFDM,
`occupied_bandwidth_hz(symbol_rate_hz)` interprets its argument as subcarrier
spacing `Delta-f`; bandwidth is `16*Delta-f`. These educational models do not
claim a regulatory mask or standards compliance.

## Analytical models

Let `gamma=10**(Eb/N0_dB/10)` and `Q(x)=0.5*erfc(x/sqrt(2))`:

- BPSK, Gray QPSK and ideal OFDM/QPSK: `Q(sqrt(2*gamma))`.
- Coherent equal-prior OOK and coherent orthogonal binary FSK:
  `Q(sqrt(gamma))`, using average energy per bit.

The implementation uses `math.erfc`, handles extreme finite Eb/N0 values, and
returns finite probabilities in `[0, 0.5]`. No SciPy, Hypothesis, or new
runtime dependency is required.

## Stress-campaign regression record

The campaign found and fixed one defect: OFDM QPSK symbols were flattened
before assignment to the 16 active bins, causing a frame-axis shape mismatch.
`test_regression_ofdm_qpsk_bits_preserve_frame_axis` now checks multiple full
frames and their noiseless bit round-trip.

## Integration and tests

The Wave 0 contract is run against each class from the master repository:

```powershell
python -m pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=services.dsp.bpsk:BPSKCodec
python -m pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=services.dsp.qpsk:QPSKCodec
python -m pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=services.dsp.am:AMCodec
python -m pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=services.dsp.fm:FMCodec
python -m pytest tests/contract/test_waveform_codec_contract.py --waveform-impl=services.dsp.ofdm:OFDMCodec
```

Run `python services/dsp/run_wave2.py` from the master-repository root to run
unit/stress tests, those five unmodified contracts, source-content checks, and
public imports. The script uses no Git commands and never installs packages.
GNU Radio smoke tests require an explicitly installed backend; fake-transport
tests cover adapter behavior without that optional environment.
