"""Freeze gate: fails on ANY change to a public SDK/domain signature.
Intentional change => ADR + bump SDK_VERSION + `python -m tests.contract._snapshot --write`."""

from __future__ import annotations

import json

from tests.contract._snapshot import SNAPSHOT, build


def test_public_surface_matches_frozen_snapshot():
    frozen = json.loads(SNAPSHOT.read_text())
    current = json.loads(json.dumps(build()))  # normalise tuples etc.
    assert current == frozen, (
        "Plugin SDK public surface changed. If intentional: write an ADR, bump "
        "SDK_VERSION, then regenerate with `python -m tests.contract._snapshot --write`."
    )
