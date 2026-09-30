# ADR-000: Freeze the plugin SDK interface contracts (W0-5)

Status: Accepted
SDK-Version: 1.0.0
Date: YYYY-MM-DD
Deciders: <KB>

> Change `Status: Proposed` to `Status: Accepted` once signed off. The CI gate
> (`tools.check_sdk_freeze`) fails until an accepted ADR exists for every SDK version.

## Context
Plugins (propagation models, waveform codecs, geodata providers, event bus, simulation engine)
are developed independently and must not break when the core evolves.

## Decision
Freeze `libraries/plugin_sdk` and `libraries/domain` at SDK 1.0.0. Changes follow semver:
MAJOR for removals/changes/new Protocol or ABC members, MINOR for additive changes.
Each release records an immutable snapshot in `sdk_snapshots/`.

## Consequences
Contract tests in `tests/contract` must pass unmodified for every implementation.
