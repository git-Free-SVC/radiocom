"""In-process raw-ASGI test harness for the API (task prompt §9).

Framework reality (verified on both virtualenvs before writing these tests):
  * httpx/httpx2 are NOT installed -> fastapi.testclient.TestClient cannot
    even be imported;
  * pytest-asyncio is NOT installed;
  * websockets/wsproto are NOT installed -> no uvicorn WS server is possible.
So every test drives the FastAPI app directly through the ASGI interface and
runs its async body with asyncio.run() (one fresh loop per test, closed by
asyncio.run; no loop.add_reader anywhere — unavailable on Windows' Proactor
policy).

Also asserts the sandbox/import invariant: services.api and libraries must
resolve inside this repository's root (guards against an editable install of
`radiocom` shadowing the code under test).
"""

from __future__ import annotations

import asyncio
import json as jsonlib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from services.api.mocks import (
    FakeClock,
    InMemoryEventBus,
    InMemoryScenarioStore,
    InMemorySimulationRegistry,
    MockGeodataProvider,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# --------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------


@dataclass
class HttpResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> Any:
        return jsonlib.loads(self.body)

    def header(self, name: str) -> str | None:
        needle = name.lower().encode()
        for key, value in self.headers:
            if key.lower() == needle:
                return value.decode("utf-8")
        return None


async def asgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    json: Any = None,
    raw_body: bytes | None = None,
    headers: dict[str, str] | None = None,
    content_length_override: int | None = None,
) -> HttpResponse:
    """One complete HTTP round trip against the in-process app."""
    route_path, _, query = path.partition("?")
    if json is not None:
        body_bytes = jsonlib.dumps(json).encode("utf-8")
    elif raw_body is not None:
        body_bytes = raw_body
    else:
        body_bytes = b""

    header_pairs: list[tuple[bytes, bytes]] = [
        (b"host", b"testserver"),
        (b"user-agent", b"pytest-raw-asgi"),
        (b"accept", b"application/json"),
    ]
    if body_bytes or json is not None or raw_body is not None:
        header_pairs.append((b"content-type", b"application/json"))
    length = content_length_override if content_length_override is not None else len(body_bytes)
    header_pairs.append((b"content-length", str(length).encode("ascii")))
    for key, value in (headers or {}).items():
        header_pairs.append((key.lower().encode("utf-8"), value.encode("utf-8")))

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": route_path,
        "raw_path": route_path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "root_path": "",
        "headers": header_pairs,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {},
    }

    sent: list[dict[str, Any]] = []
    body_delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal body_delivered
        if not body_delivered:
            body_delivered = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    try:
        await app(scope, receive, send)
    except Exception:
        # Starlette's ServerErrorMiddleware re-raises after sending the 500
        # response (documented behaviour); a complete response still counts.
        if not sent:
            raise

    status = 0
    response_headers: list[tuple[bytes, bytes]] = []
    for message in sent:
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = list(message.get("headers", ()))
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return HttpResponse(status=status, headers=response_headers, body=body)


def request(app: Any, method: str, path: str, **kwargs: Any) -> HttpResponse:
    """Sync wrapper: one asyncio.run per HTTP round trip."""
    return asyncio.run(asgi_request(app, method, path, **kwargs))


def get(app: Any, path: str, **kwargs: Any) -> HttpResponse:
    return request(app, "GET", path, **kwargs)


def post(app: Any, path: str, **kwargs: Any) -> HttpResponse:
    return request(app, "POST", path, **kwargs)


def patch(app: Any, path: str, **kwargs: Any) -> HttpResponse:
    return request(app, "PATCH", path, **kwargs)


# --------------------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------------------


class WebSocketTestClient:
    """Raw ASGI WebSocket client: connect / receive / send_text / disconnect."""

    def __init__(self, app: Any, path: str) -> None:
        self.app = app
        self.path = path
        self.accepted = False
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._pending: dict[str, Any] | None = None

    async def __aenter__(self) -> Self:
        route_path, _, query = self.path.partition("?")
        scope: dict[str, Any] = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": route_path,
            "raw_path": route_path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50001),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
        }

        async def receive() -> dict[str, Any]:
            return await self._incoming.get()

        async def send(message: dict[str, Any]) -> None:
            await self._outgoing.put(message)

        self._task = asyncio.create_task(self.app(scope, receive, send))
        await self._incoming.put({"type": "websocket.connect"})
        first = await asyncio.wait_for(self._outgoing.get(), timeout=5.0)
        if first["type"] == "websocket.accept":
            self.accepted = True
        else:  # closed without accept (e.g. no route matched)
            self._pending = first
        return self

    async def receive(self, timeout: float = 5.0) -> dict[str, Any]:
        if self._pending is not None:
            message, self._pending = self._pending, None
            return message
        return await asyncio.wait_for(self._outgoing.get(), timeout=timeout)

    async def receive_json(self, timeout: float = 5.0) -> dict[str, Any]:
        message = await self.receive(timeout=timeout)
        assert message["type"] == "websocket.send", f"unexpected frame: {message}"
        return jsonlib.loads(message["text"])

    async def send_text(self, text: str) -> None:
        await self._incoming.put({"type": "websocket.receive", "text": text})

    async def disconnect(self, code: int = 1000) -> None:
        await self._incoming.put({"type": "websocket.disconnect", "code": code})

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._task is None:  # pragma: no cover - guard
            return
        if not self._task.done():
            await self.disconnect()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except TimeoutError as timeout:
            self._task.cancel()
            raise AssertionError(
                f"application did not finish within 5s after disconnect for {self.path}"
            ) from timeout
        # Exceptions raised by the application task surface as real failures.


def ws_connect(app: Any, path: str) -> WebSocketTestClient:
    return WebSocketTestClient(app, path)


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------


@pytest.fixture
def deps() -> dict[str, Any]:
    """Fresh, EMPTY (unseeded) ports — exact state control per test.
    The geodata mock ships two default layers; scenario/registry start empty."""
    clock = FakeClock()
    bus = InMemoryEventBus()
    scenario = InMemoryScenarioStore(clock=clock)
    registry = InMemorySimulationRegistry(bus=bus, scenario_store=scenario, clock=clock)
    geodata = MockGeodataProvider()
    return {
        "scenario": scenario,
        "registry": registry,
        "bus": bus,
        "clock": clock,
        "geodata": geodata,
    }


@pytest.fixture
def app(deps: dict[str, Any]) -> Any:
    from services.api import create_app

    application = create_app(**deps)
    _assert_imports_resolve_inside_repository()
    return application


@pytest.fixture
def seeded_app() -> Any:
    """create_app() defaults: two scenarios, two simulations (two radios each,
    one link each), two geodata layers — the prompt's fixture data."""
    from services.api import create_app

    return create_app()


def _assert_imports_resolve_inside_repository() -> None:
    """An editable `radiocom` install exists in both venvs; the sandbox/cwd
    must win or these tests would silently exercise the project's files."""
    import libraries
    import services.api

    libraries_root = Path(libraries.__file__).resolve().parent
    api_root = Path(services.api.__file__).resolve().parent
    assert libraries_root == REPOSITORY_ROOT / "libraries", libraries_root
    assert api_root == REPOSITORY_ROOT / "services" / "api", api_root


# --------------------------------------------------------------------------------------
# Shared assertions / helpers
# --------------------------------------------------------------------------------------


def assert_error(response: HttpResponse, status: int, *needles: str) -> Any:
    """Every error response: the exact status and the exact envelope {detail}."""
    assert response.status == status, (response.status, response.text)
    body = response.json()
    assert isinstance(body, dict), body
    assert set(body.keys()) == {"detail"}, body
    if isinstance(body["detail"], str):
        for needle in needles:
            assert needle in body["detail"], body
    elif needles:
        joined = jsonlib.dumps(body["detail"])
        for needle in needles:
            assert needle in joined, body
    return body


def assert_error_detail_list(response: HttpResponse, status: int = 422) -> list[dict[str, Any]]:
    """Schema/domain-rejection shape: {"detail": [{loc, msg, type}, ...]}."""
    body = assert_error(response, status)
    detail = body["detail"]
    assert isinstance(detail, list) and detail, detail
    for entry in detail:
        assert isinstance(entry, dict)
        assert set(entry.keys()) == {"loc", "msg", "type"}, entry
    return detail


VALID_SCENARIO_BODY: dict[str, Any] = {
    "scenario": {
        "name": "test-grid",
        "seed": 7,
        "nodes": [
            {"id": "n1", "type": "fixed_radio", "position": [48.85, 2.35], "radio": "r1"},
            {
                "id": "n2",
                "type": "mobile_radio",
                "position": [48.86, 2.36, 12.0],
                "radio": "r2",
                "route": "line_1",
            },
        ],
    }
}

VALID_RADIO_BODY: dict[str, Any] = {
    "simulation_id": "",  # filled by callers once the simulation exists
    "frequency": {"center_hz": 2_400_000_000.0, "bandwidth_hz": 5_000_000.0},
    "transmitter": {"power_watt": 0.1, "cable_loss_db": 0.0},
    "receiver": {"sensitivity_dBm": -100.0, "noise_figure_dB": 5.0},
    "antenna": {"antenna_type": "omni", "gain_dBi": 1.5, "height_m": 5.0},
    "position": {"lat": 48.85, "lon": 2.35, "alt_m": 30.0},
}


def create_scenario(app: Any, name: str = "test-grid") -> dict[str, Any]:
    body = {"scenario": {**VALID_SCENARIO_BODY["scenario"], "name": name}}
    response = post(app, "/scenarios", json=body)
    assert response.status == 201, response.text
    return response.json()


def create_simulation(app: Any, scenario_id: str) -> dict[str, Any]:
    response = post(app, "/simulations", json={"scenario_id": scenario_id})
    assert response.status == 201, response.text
    return response.json()


def create_radio(app: Any, simulation_id: str, **overrides: Any) -> dict[str, Any]:
    body = {**VALID_RADIO_BODY, "simulation_id": simulation_id, **overrides}
    response = post(app, "/radios", json=body)
    assert response.status == 201, response.text
    return response.json()
