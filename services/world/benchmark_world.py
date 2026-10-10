"""Micro-benchmark for services/world. Run from anywhere:

    python services/world/benchmark_world.py

Reports microseconds per operation (best of several repeats). Not collected by
pytest (name does not match ``test_*.py``) and not asserted on: timings vary by
machine, so this is a tool for you, not a CI gate.
"""

from __future__ import annotations

import importlib
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

# services/world/benchmark_world.py -> repo root is two levels above this folder.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_domain = importlib.import_module("libraries.domain.position")
_fakes = importlib.import_module("tests.contract.fakes.flat_geodata_provider")
_world = importlib.import_module("services.world")

GeoPosition = _domain.GeoPosition
FlatGeodataProvider = _fakes.FlatGeodataProvider

N_POINTS = 50_000
REPEATS = 5


def best_us_per_op(fn: Callable[[], object], ops: int) -> float:
    best = float("inf")
    for _ in range(REPEATS):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best / ops * 1e6


def main() -> None:
    rng = random.Random(3)
    origin = GeoPosition(45.0, 6.0, 1000.0)
    points = [
        GeoPosition(rng.uniform(44.9, 45.1), rng.uniform(5.9, 6.1), rng.uniform(0, 3000))
        for _ in range(N_POINTS)
    ]
    frame = _world.ENUFrame(origin)
    ecefs = [_world.geo_to_ecef(p) for p in points]
    enus = frame.to_enu_many(points)

    rows: list[tuple[str, Callable[[], object], int]] = [
        ("geo_to_ecef", lambda: [_world.geo_to_ecef(p) for p in points], N_POINTS),
        ("ecef_to_geo", lambda: [_world.ecef_to_geo(*c) for c in ecefs], N_POINTS),
        (
            "geo_to_enu (one-shot)",
            lambda: [_world.geo_to_enu(p, origin) for p in points],
            N_POINTS,
        ),
        ("ENUFrame.to_enu", lambda: [frame.to_enu(p) for p in points], N_POINTS),
        ("ENUFrame.to_enu_many", lambda: frame.to_enu_many(points), N_POINTS),
        (
            "enu_to_geo (one-shot)",
            lambda: [_world.enu_to_geo(e, origin) for e in enus],
            N_POINTS,
        ),
        ("ENUFrame.to_geo", lambda: [frame.to_geo(e) for e in enus], N_POINTS),
        ("ENUFrame.to_geo_many", lambda: frame.to_geo_many(enus), N_POINTS),
    ]
    a, b, provider = (
        GeoPosition(45.0, 6.0, 100.0),
        GeoPosition(45.2, 6.2, 100.0),
        FlatGeodataProvider(),
    )
    for samples in (32, 256, 2048):
        rows.append(
            (
                f"line_of_sight (samples={samples})",
                lambda s=samples: [_world.line_of_sight(a, b, provider, s) for _ in range(1000)],
                1000,
            )
        )

    print(f"{'operation':34s}{'us/op':>10s}")
    for name, fn, ops in rows:
        print(f"{name:34s}{best_us_per_op(fn, ops):10.2f}")


if __name__ == "__main__":
    main()
