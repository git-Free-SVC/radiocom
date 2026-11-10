"""REST + WebSocket routes of architecture doc §17, over injected ports.

Thin handlers: validate the request (services.api.schemas) -> delegate to a
port -> validate the response against the API-declared schema -> return.
Body-carrying handlers are ``def`` (FastAPI runs them in its threadpool, so
engine calls never block the event loop); WebSocket endpoints are ``async``.

create_app signature (task prompt §7) — keyword-only, every port optional
(defaults are fresh deterministic mocks so ``create_app()`` just works):

    create_app(*, scenario, registry, bus, clock, geodata) -> FastAPI

Note: the radio/link routes of §4 are served by CorePort, which
SimulationRegistryPort extends — radios and links belong to a simulation, so
the five prompt ports carry all six capabilities.

Local run (HTTP only — no WebSocket server library is installed):
    uvicorn services.api.app:create_app --factory
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Body, FastAPI, Query, Request, WebSocket

from libraries.domain.position import GeoPosition
from libraries.plugin_sdk.event_bus import EventBus
from libraries.plugin_sdk.geodata import GeoJSONFile
from services.api.errors import ApiError, error_response, install_exception_handlers
from services.api.mocks import (
    FakeClock,
    InMemoryEventBus,
    InMemoryScenarioStore,
    InMemorySimulationRegistry,
    MockGeodataProvider,
)
from services.api.ports import ClockPort, GeodataPort, ScenarioPort, SimulationRegistryPort
from services.api.schemas import validate_create_scenario, validate_request, validate_response
from services.api.serialization import to_payload
from services.api.ws_connection import stream_events
from services.api.ws_contract import (
    CHANNEL_SPECTRUM,
    CLOSE_UNKNOWN_SIMULATION,
    SPECTRUM_TOPIC,
    WS_PATH_SPECTRUM,
    WS_PATH_TELEMETRY,
    build_telemetry_snapshot,
    spectrum_snapshot,
    telemetry_topic,
)

# Assumed limit (spec silent): bodies larger than 1 MiB are refused with 413
# by the http middleware, before FastAPI parses anything.
MAX_BODY_BYTES = 1024 * 1024


def create_app(
    *,
    scenario: ScenarioPort | None = None,
    registry: SimulationRegistryPort | None = None,
    bus: EventBus | None = None,
    clock: ClockPort | None = None,
    geodata: GeodataPort | None = None,
) -> FastAPI:
    """Build the API application over the given ports (all optional)."""
    # -- resolve ports: inject or build deterministic defaults ------------------
    resolved_clock: ClockPort = clock if clock is not None else FakeClock()
    if scenario is None:
        default_store = InMemoryScenarioStore(clock=resolved_clock)
        default_store.seed_default_scenarios()  # fixture: two scenarios
        resolved_scenario: ScenarioPort = default_store
    else:
        resolved_scenario = scenario
    resolved_bus: EventBus = bus if bus is not None else InMemoryEventBus()
    if registry is None:
        # Fixtures derive from the scenario store actually in use: the default
        # store is seeded above, so the default registry seeds two simulations
        # (two radios each + one link each) from its records.
        store = resolved_scenario if isinstance(resolved_scenario, InMemoryScenarioStore) else None
        resolved_registry: SimulationRegistryPort = InMemorySimulationRegistry(
            bus=resolved_bus, scenario_store=store, clock=resolved_clock
        )
    else:
        resolved_registry = registry
    resolved_geodata: GeodataPort = geodata if geodata is not None else MockGeodataProvider()

    app = FastAPI(title="RADIOCOM Simulation API", version="0.0.1", docs_url="/docs")
    install_exception_handlers(app)

    # -- inspection seam (tests read these; no global mutable state) ------------
    app.state.scenario = resolved_scenario
    app.state.registry = resolved_registry
    app.state.bus = resolved_bus
    app.state.clock = resolved_clock
    app.state.geodata = resolved_geodata
    app.state.ws_connections: set[Any] = set()  # live connections
    app.state.ws_history: list[Any] = []  # stats of completed connections

    # -- body-size guard (413) --------------------------------------------------
    @app.middleware("http")
    async def enforce_body_limit(request: Request, call_next: Any) -> Any:
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return error_response(413, "request body too large")
        return await call_next(request)

    # -- shared control-route logic --------------------------------------------
    def run_control(route_key: str, simulation_id: str, action: str) -> dict[str, Any]:
        engine = resolved_registry.get(simulation_id)
        if engine is None:
            raise ApiError(404, f"simulation {simulation_id} not found")
        try:
            getattr(engine, action)()
        except RuntimeError as exc:  # illegal lifecycle transition -> 409
            raise ApiError(409, str(exc)) from exc
        payload = {
            "id": simulation_id,
            "scenario_id": resolved_registry.scenario_id(simulation_id),
            "status": resolved_registry.status(simulation_id),
        }
        validate_response(route_key, payload)
        return payload

    # --------------------------------------------------------------------------------
    # Scenarios
    # --------------------------------------------------------------------------------
    @app.get("/scenarios")
    def list_scenarios_route() -> dict[str, Any]:
        payload = {"scenarios": resolved_scenario.list_scenarios()}
        validate_response("GET /scenarios", payload)
        return payload

    @app.post("/scenarios", status_code=201)
    def create_scenario_route(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        validate_create_scenario(body)  # frozen scenario.schema.json + strict
        record = resolved_scenario.create_scenario(body)
        validate_response("POST /scenarios", record)
        return record

    @app.get("/scenarios/{id}")
    def get_scenario_route(id: str) -> dict[str, Any]:
        record = resolved_scenario.get_scenario(id)
        if record is None:
            raise ApiError(404, f"scenario {id} not found")
        validate_response("GET /scenarios/{id}", record)
        return record

    # --------------------------------------------------------------------------------
    # Simulations (the YAML summary says "Start a simulation run", but a separate
    # /start route exists -> creation produces LOADED; recorded as an assumption)
    # --------------------------------------------------------------------------------
    @app.post("/simulations", status_code=201)
    def create_simulation_route(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        validate_request("POST /simulations", body)
        scenario_id = body["scenario_id"]
        record = resolved_scenario.get_scenario(scenario_id)
        if record is None:
            raise ApiError(404, f"scenario {scenario_id} not found")
        simulation_id = resolved_registry.create(scenario_id)
        engine = resolved_registry.get(simulation_id)
        engine.load(record)  # state new -> LOADED (frozen lifecycle)
        payload = {
            "id": simulation_id,
            "scenario_id": scenario_id,
            "status": resolved_registry.status(simulation_id),
        }
        validate_response("POST /simulations", payload)
        return payload

    @app.post("/simulations/{id}/start")
    def start_simulation_route(id: str) -> dict[str, Any]:
        return run_control("POST /simulations/{id}/start", id, "start")

    @app.post("/simulations/{id}/pause")
    def pause_simulation_route(id: str) -> dict[str, Any]:
        return run_control("POST /simulations/{id}/pause", id, "pause")

    @app.post("/simulations/{id}/resume")
    def resume_simulation_route(id: str) -> dict[str, Any]:
        return run_control("POST /simulations/{id}/resume", id, "resume")

    @app.post("/simulations/{id}/reset")
    def reset_simulation_route(id: str) -> dict[str, Any]:
        return run_control("POST /simulations/{id}/reset", id, "reset")

    # --------------------------------------------------------------------------------
    # Radios + links (no POST /simulations/{id}/radios: the frozen YAML says
    # POST /radios — conflict C1; step() has no route at all — intentional gap)
    # --------------------------------------------------------------------------------
    @app.post("/radios", status_code=201)
    def add_radio_route(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        validate_request("POST /radios", body)
        try:
            payload = resolved_registry.add_radio(body["simulation_id"], body)
        except ValueError as exc:  # domain constructor (Frequency, GeoPosition) -> 422
            raise ApiError(422, str(exc)) from exc
        validate_response("POST /radios", payload)
        return payload

    @app.patch("/radios/{id}")
    def update_radio_route(id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        validate_request("PATCH /radios/{id}", body)
        try:
            payload = resolved_registry.update_radio(id, body)
        except ValueError as exc:
            raise ApiError(422, str(exc)) from exc
        if payload is None:
            raise ApiError(404, f"radio {id} not found")
        validate_response("PATCH /radios/{id}", payload)
        return payload

    @app.get("/links/{a}/{b}")
    def get_link_route(a: str, b: str) -> dict[str, Any]:
        payload = resolved_registry.get_link(a, b)
        if payload is None:
            raise ApiError(404, f"link between {a} and {b} not found")
        validate_response("GET /links/{a}/{b}", payload)
        return payload

    # --------------------------------------------------------------------------------
    # Geodata (all four YAML paths; served from the injected GeodataProvider —
    # the mock never touches GeoServer)
    # --------------------------------------------------------------------------------
    @app.get("/geodata/layers")
    def list_layers_route() -> dict[str, Any]:
        payload = {"layers": [to_payload(layer) for layer in resolved_geodata.list_layers()]}
        validate_response("GET /geodata/layers", payload)
        return payload

    @app.post("/geodata/layers", status_code=201)
    def publish_layer_route(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        validate_request("POST /geodata/layers", body)
        try:
            if body["kind"] == "raster":
                layer = resolved_geodata.publish_raster(
                    body["name"], body["path_or_uri"], body.get("srs", "EPSG:4326")
                )
            else:
                layer = resolved_geodata.publish_vector(
                    body["name"], GeoJSONFile(path=body["path_or_uri"])
                )
        except ValueError as exc:
            raise ApiError(422, str(exc)) from exc
        payload = to_payload(layer)
        validate_response("POST /geodata/layers", payload)
        return payload

    @app.get("/geodata/elevation")
    def elevation_route(lat: float = Query(...), lon: float = Query(...)) -> dict[str, Any]:
        try:
            position = GeoPosition(lat=lat, lon=lon)  # ValueError -> 422 (range/NaN/inf)
            elevation = resolved_geodata.elevation_at(position)
        except ValueError as exc:
            raise ApiError(422, str(exc)) from exc
        payload = {"lat": lat, "lon": lon, "elevation_m": elevation}
        validate_response("GET /geodata/elevation", payload)
        return payload

    @app.get("/geodata/elevation/profile")
    def elevation_profile_route(
        lat1: float = Query(...),
        lon1: float = Query(...),
        lat2: float = Query(...),
        lon2: float = Query(...),
        samples: int = Query(...),
    ) -> dict[str, Any]:
        try:
            start = GeoPosition(lat=lat1, lon=lon1)
            end = GeoPosition(lat=lat2, lon=lon2)
            points = resolved_geodata.elevation_profile(start, end, samples)
        except ValueError as exc:  # includes samples < 2 from the provider
            raise ApiError(422, str(exc)) from exc
        payload = {"profile_m": points}
        validate_response("GET /geodata/elevation/profile", payload)
        return payload

    # --------------------------------------------------------------------------------
    # WebSockets (§17 — cannot appear in OpenAPI 3.0.3; contract in ws_contract.py)
    # --------------------------------------------------------------------------------
    @app.websocket(WS_PATH_TELEMETRY)
    async def telemetry_websocket(ws: WebSocket, id: str) -> None:
        if not resolved_registry.exists(id):
            # Accept, then close 4404 BEFORE any subscription is created.
            await ws.accept()
            await ws.close(code=CLOSE_UNKNOWN_SIMULATION)
            return
        await ws.accept()
        await stream_events(
            ws,
            bus=resolved_bus,
            topic=telemetry_topic(id),
            snapshot=lambda: build_telemetry_snapshot(
                resolved_registry.radios(id), resolved_registry.links(id)
            ),
            app_state=app.state,
        )

    @app.websocket(WS_PATH_SPECTRUM)
    async def spectrum_websocket(ws: WebSocket) -> None:
        # No {id}, no query parameters -> nothing is validated by design
        # (documented: /spectrum validates nothing).
        await ws.accept()
        last_payload_fn = getattr(resolved_bus, "last_payload", None)
        await stream_events(
            ws,
            bus=resolved_bus,
            topic=SPECTRUM_TOPIC,
            snapshot=lambda: {
                CHANNEL_SPECTRUM: spectrum_snapshot(
                    last_payload_fn(SPECTRUM_TOPIC) if callable(last_payload_fn) else None
                )
            },
            app_state=app.state,
        )

    return app
