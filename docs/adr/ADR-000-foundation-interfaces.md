# ADR-000 — Foundation Interfaces Frozen at `foundation-v0`

## Status
Accepted — this tag marks the point after which no agent edits
`libraries/plugin_sdk/` or `libraries/protocols/` without a deliberate,
reviewed "interface change" task (see architecture doc §36).

## Frozen Protocols (`libraries/plugin_sdk/`)

| Interface | File | Key methods |
|---|---|---|
| `PropagationModel` | `propagation.py` | `validity_domain()`, `evaluate(tx, rx, *, seed=None) -> PropagationResult` |
| `WaveformCodec` | `waveform.py` | `modulate(bits, sample_rate_hz)`, `demodulate(iq, sample_rate_hz)`, `ber(ebn0_db)`, `occupied_bandwidth_hz(symbol_rate_hz)` |
| `GeodataProvider` | `geodata.py` | `publish_raster`, `publish_vector`, `set_style`, `elevation_at`, `elevation_profile`, `features_in`, `tile_url` |
| `SimulationEngine` (+ `Scheduler`/`Clock`/`Event`/`State`) | `simulation.py` | `load`, `start`, `pause`, `resume`, `reset`, `step`, `.state` |
| `EventBus` | `event_bus.py` | `publish(topic, payload)`, `subscribe(topic, handler)`, `unsubscribe` |

## Frozen domain types (`libraries/domain/`)
`GeoPosition`, `ENUPosition`, `Frequency`, `Antenna`, `Transmitter`, `Receiver`,
`Radio`, `PropagationResult`, `LinkState`, `LinkQuality`, `LinkBudgetInput`.
Field names match architecture doc §9/§11 verbatim.

## Frozen schemas (`libraries/protocols/`)
`scenario.schema.json`, `openapi.yaml`, `events/link_state_changed.schema.json`.

## Consequences
- Any Wave 1+ agent implements against these signatures only — never reads
  another agent's source to understand an interface.
- A signature change here ripples to every contract test; treat it like
  any other ADR: propose, review, bump a version note in this file.
- Contract test templates in `tests/contract/` are the executable spec —
  if a template needs to change to accept a valid new implementation, that
  itself is a sign the Protocol was underspecified and belongs in a new ADR.

## Naming deviation from the architecture doc
The doc's `libraries/plugin-sdk/` (hyphen) is written here as
`libraries/plugin_sdk/` (underscore) — hyphens are not valid in Python
import paths. The doc's directory listing (§25) should be read with this
substitution.
