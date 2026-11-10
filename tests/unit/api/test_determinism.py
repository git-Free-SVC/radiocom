"""Determinism (task prompt §4/§9): counter ids, injected clock, byte-identical
sequences across fresh apps, unique ids under concurrency, exactly-N engine
entries for N parallel requests, and the source scan proving no wall clock,
no uuid, no random anywhere under services/api."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from conftest import (  # type: ignore[import-not-found]
    REPOSITORY_ROOT,
    VALID_RADIO_BODY,
    VALID_SCENARIO_BODY,
    create_scenario,
    create_simulation,
    get,
    post,
    request,
)

from services.api import create_app

# Patterns forbidden in services/api sources (§4). Tests may use anything.
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bimport\s+uuid\b",
        r"\bfrom\s+uuid\b",
        r"\buuid4?\s*\(",
        r"\bimport\s+random\b",
        r"\bfrom\s+random\b",
        r"\brandom\.",
        r"\bimport\s+secrets\b",
        r"\bsecrets\.",
        r"\btime\.time\s*\(",
        r"\bperf_counter\s*\(",
        r"\bmonotonic\s*\(",
        r"\bdatetime\.now\s*\(",
        r"\butcnow\s*\(",
    )
)


def _sequence(application: Any) -> list[bytes]:
    """One fixed request sequence; responses kept as raw bytes."""
    body = []
    body.append(post(application, "/scenarios", json=VALID_SCENARIO_BODY).body)
    body.append(get(application, "/scenarios").body)
    body.append(post(application, "/simulations", json={"scenario_id": "scn_0001"}).body)
    radio = {**VALID_RADIO_BODY, "simulation_id": "sim_0001"}
    body.append(post(application, "/radios", json=radio).body)
    body.append(post(application, "/radios", json=radio).body)
    body.append(get(application, "/links/rdr_0001/rdr_0002").body)
    body.append(get(application, "/geodata/elevation?lat=48.85&lon=2.35").body)
    body.append(get(application, "/geodata/layers").body)
    body.append(get(application, "/scenarios/scn_0001").body)
    return body


def test_identical_sequence_on_two_fresh_apps_is_byte_identical() -> None:
    first = _sequence(create_app())
    second = _sequence(create_app())
    assert first == second
    assert all(isinstance(chunk, bytes) and chunk for chunk in first)


def test_created_at_comes_only_from_the_injected_fake_clock(deps) -> None:
    application = create_app(**deps)  # empty store: no seeded clock ticks yet
    first = post(application, "/scenarios", json=VALID_SCENARIO_BODY).json()
    second = post(application, "/scenarios", json=VALID_SCENARIO_BODY).json()
    assert first["created_at"] == "2026-01-01T00:00:00Z"
    assert second["created_at"] == "2026-01-01T00:00:01Z"

    # Two seeded defaults agree with each other too (ticks 0 and 1 are used by
    # the two seeded scenarios, so the first user record lands on tick 2).
    other_a, other_b = create_app(), create_app()
    stamp_a = post(other_a, "/scenarios", json=VALID_SCENARIO_BODY).json()["created_at"]
    stamp_b = post(other_b, "/scenarios", json=VALID_SCENARIO_BODY).json()["created_at"]
    assert stamp_a == stamp_b == "2026-01-01T00:00:02Z"  # never wall time


def test_parallel_radio_creations_yield_unique_counter_ids(deps) -> None:
    application = create_app(**deps)
    get(application, "/scenarios")  # warm the middleware stack single-threaded
    scenario = create_scenario(application, "parallel-radios")
    simulation = create_simulation(application, scenario["id"])
    body = {**VALID_RADIO_BODY, "simulation_id": simulation["id"]}

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _index: request(application, "POST", "/radios", json=body),
                range(20),
            )
        )
    assert all(response.status == 201 for response in responses), [
        response.text for response in responses if response.status != 201
    ]
    ids = {response.json()["id"] for response in responses}
    assert ids == {f"rdr_{index:04d}" for index in range(1, 21)}


def test_parallel_scenario_creations_yield_unique_counter_ids(deps) -> None:
    application = create_app(**deps)
    get(application, "/scenarios")

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _index: request(application, "POST", "/scenarios", json=VALID_SCENARIO_BODY),
                range(10),
            )
        )
    assert all(response.status == 201 for response in responses)
    ids = {response.json()["id"] for response in responses}
    assert ids == {f"scn_{index:04d}" for index in range(1, 11)}


def test_parallel_control_requests_produce_exactly_n_engine_entries(deps) -> None:
    """N parallel start() requests -> exactly N log entries, no double-calls,
    exactly one200 (the engine transitions are lock-guarded)."""
    application = create_app(**deps)
    get(application, "/scenarios")
    scenario = create_scenario(application, "race")
    simulation = create_simulation(application, scenario["id"])
    simulation_id = simulation["id"]
    assert application.state.registry.engine_calls == [f"{simulation_id}:load"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(
                lambda _index: request(application, "POST", f"/simulations/{simulation_id}/start"),
                range(10),
            )
        )

    statuses = [response.status for response in responses]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(409) == 9, statuses

    calls = application.state.registry.engine_calls
    assert len(calls) == 11  # 1 load + exactly 10 entries for 10 requests
    assert calls.count(f"{simulation_id}:load") == 1
    assert calls.count(f"{simulation_id}:start") == 10


def test_source_scan_forbids_wall_clock_uuid_and_random() -> None:
    api_dir = REPOSITORY_ROOT / "services" / "api"
    sources = sorted(api_dir.glob("*.py"))
    assert sources, f"no sources found under {api_dir}"
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            assert match is None, f"{path.name}: forbidden pattern {pattern.pattern!r}"
