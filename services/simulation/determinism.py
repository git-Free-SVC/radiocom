"""Deterministic per-entity RNG derivation (architecture doc §14 §5.2).

A single root RNG is seeded from scenario.seed; each entity's sub-seed is
derived from a stable hash of (seed, entity_id) rather than drawn
sequentially from the root — sequential drawing would make an entity's
stream depend on the iteration order of the entities dict/list, which is
exactly the kind of implicit-ordering dependency determinism is supposed
to rule out. Python's built-in hash() is salted per-process and must never
be used for this; hashlib.sha256 is stable across processes and platforms.
"""

from __future__ import annotations

import hashlib


def derive_entity_seed(root_seed: int, entity_id: str) -> int:
    digest = hashlib.sha256(f"{root_seed}:{entity_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)
