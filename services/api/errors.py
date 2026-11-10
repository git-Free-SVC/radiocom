"""API-local error types and FastAPI exception handlers.

The frozen openapi.yaml (foundation-v0) defines NO 4xx/5xx responses and no
error schema at all, so the API adopts exactly one error envelope —
``{"detail": <str> | <list>}`` — on every error path. That envelope is an
assumption recorded in README.txt (task prompt §4/§6).

Mapping decided by the task prompt:
  404  unknown scenario / simulation / radio / link id   (explicit ApiError)
  409  illegal lifecycle transition (engine RuntimeError) (explicit ApiError)
  422  malformed body, schema violation, NaN/inf, unknown or immutable
       PATCH field, and any domain ValueError              (ApiError / handler)
  413  body larger than 1 MiB                             (http middleware)
  500  unexpected exception, or a response violating a declared schema
       (catch-all handler / ResponseContractError)

ResponseContractError deliberately does NOT subclass ValueError: the
ValueError handler maps value errors to 422 (domain input errors must never
surface as 500), while a server-side response bug must surface as 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response


class ApiError(Exception):
    """A deliberate API error carrying its HTTP status and envelope detail."""

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(detail if isinstance(detail, str) else str(detail))
        self.status_code = status_code
        self.detail = detail


class ResponseContractError(ApiError):
    """The server produced a body that violates an API-declared schema -> 500."""

    def __init__(self, detail: str) -> None:
        super().__init__(500, detail)


def error_response(status_code: int, detail: Any) -> JSONResponse:
    """The single error envelope: exactly the key set {detail}."""
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def api_error_handler(request: Request, exc: ApiError) -> Response:
    return error_response(exc.status_code, exc.detail)


async def request_validation_handler(request: Request, exc: RequestValidationError) -> Response:
    # FastAPI's native body is a list of {"loc", "msg", "type", ...} entries;
    # the "input"/"ctx" entries are stripped because they are not guaranteed
    # to be JSON-serialisable (e.g. json.JSONDecodeError inside ctx).
    errors: list[dict[str, Any]] = [
        {
            "loc": [str(part) for part in entry.get("loc", ())],
            "msg": str(entry.get("msg", "")),
            "type": str(entry.get("type", "")),
        }
        for entry in exc.errors()
    ]
    return error_response(422, errors)


async def value_error_handler(request: Request, exc: ValueError) -> Response:
    # Domain constructors raise ValueError (Frequency, GeoPosition, samples<2).
    # Input-side ValueError must never surface as a 500 (task prompt §4).
    return error_response(422, str(exc))


async def internal_error_handler(request: Request, exc: Exception) -> Response:
    # No traceback, no leaked internals (task prompt §4).
    return error_response(500, "internal error")


def install_exception_handlers(app: FastAPI) -> None:
    """Attach the uniform error envelope to every error path."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
