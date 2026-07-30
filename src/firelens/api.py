"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from firelens.answering.intent import plan_query
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    ErrorEnvelope,
    HealthResponse,
    LiveMapResponse,
    LivenessResponse,
    LiveResultKind,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    ResponseStatus,
    SearchResponse,
)
from firelens.live import LiveDataService
from firelens.live_answering import LiveAnswerCoordinator
from firelens.operational_logging import log_operation
from firelens.request_guard import AnonymousRequestGuard
from firelens.runtime import Runtime, load_runtime


def _error_status(error_kind: str | None) -> int:
    return 502 if error_kind in {"invalid_request", "invalid_response"} else 503


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
    502: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def create_app(
    config: FireLensConfig | None = None,
    *,
    runtime: Runtime | None = None,
    live_service: LiveDataService | None = None,
) -> FastAPI:
    active_config = config or FireLensConfig.from_env()
    active_live_service = live_service or LiveDataService()
    live_coordinator = LiveAnswerCoordinator(active_live_service)
    request_guard = AnonymousRequestGuard(
        limit=active_config.anonymous_rate_limit,
        window_seconds=active_config.anonymous_rate_window_seconds,
        max_body_bytes=active_config.max_request_body_bytes,
        trusted_proxy_platform=active_config.trusted_proxy_platform,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or load_runtime(active_config)
        app.state.live_service = active_live_service
        try:
            yield
        finally:
            if runtime is None:
                await app.state.runtime.aclose()
            if live_service is None:
                await active_live_service.aclose()

    app = FastAPI(
        title="FireLens BC",
        version=active_config.release_version,
        description=(
            "Evidence-bound wildfire guidance plus bounded official incident, perimeter, "
            "and evacuation records. Not emergency direction."
        ),
        lifespan=lifespan,
    )
    if runtime is not None:
        app.state.runtime = runtime
    app.state.live_service = active_live_service

    def current_runtime() -> Runtime:
        return app.state.runtime

    def current_live_service() -> LiveDataService:
        return app.state.live_service

    def error_response(
        status_code: int,
        *,
        trace_id: str,
        error_kind: str,
        message: str,
        retryable: bool = False,
    ) -> JSONResponse:
        envelope = ErrorEnvelope(
            trace_id=trace_id,
            error_kind=error_kind,
            message=message,
            retryable=retryable,
        )
        return JSONResponse(status_code=status_code, content=envelope.model_dump())

    @app.middleware("http")
    async def bounded_anonymous_requests(request: Request, call_next):
        guarded = request.url.path in {"/api/v1/ask", "/api/v1/live/map"}
        if not guarded:
            return await call_next(request)
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                declared_bytes = int(declared_length)
            except ValueError:
                return error_response(
                    400,
                    trace_id=uuid4().hex,
                    error_kind="invalid_request",
                    message="The Content-Length header was invalid.",
                )
            if declared_bytes < 0 or declared_bytes > request_guard.max_body_bytes:
                return error_response(
                    413,
                    trace_id=uuid4().hex,
                    error_kind="request_too_large",
                    message="The request exceeded the FireLens public API size limit.",
                )
        decision = await request_guard.check(request_guard.anonymous_key(request))
        if not decision.allowed:
            response = error_response(
                429,
                trace_id=uuid4().hex,
                error_kind="rate_limit",
                message="The anonymous FireLens request limit was reached. Try again shortly.",
                retryable=True,
            )
            response.headers["Retry-After"] = str(decision.retry_after_seconds)
            response.headers["X-RateLimit-Limit"] = str(request_guard.limit)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Scope"] = "instance-local"
            return response
        bounded_body = bytearray()
        async for chunk in request.stream():
            if len(bounded_body) + len(chunk) > request_guard.max_body_bytes:
                return error_response(
                    413,
                    trace_id=uuid4().hex,
                    error_kind="request_too_large",
                    message="The request exceeded the FireLens public API size limit.",
                )
            bounded_body.extend(chunk)
        request._body = bytes(bounded_body)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(request_guard.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Scope"] = "instance-local"
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; connect-src 'self'; "
            "font-src 'self' data:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request, exc: RequestValidationError):
        details = [
            {key: value for key, value in error.items() if key != "ctx"}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={
                **ErrorEnvelope(
                    trace_id=uuid4().hex,
                    error_kind="invalid_request",
                    message="The request did not match the FireLens API contract.",
                ).model_dump(),
                "details": details,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request, _exc: Exception):
        return error_response(
            500,
            trace_id=uuid4().hex,
            error_kind="internal_error",
            message="FireLens encountered an unexpected internal error.",
        )

    @app.get("/api/v1/health/live", response_model=LivenessResponse)
    async def liveness() -> LivenessResponse:
        return LivenessResponse()

    @app.get("/api/v1/health/ready", response_model=HealthResponse)
    async def readiness(response: Response) -> HealthResponse:
        health = current_runtime().health()
        if health.status != "ready":
            response.status_code = 503
        return health

    @app.get("/api/v1/live/map", response_model=LiveMapResponse)
    async def live_map(
        bbox: str | None = Query(default=None, max_length=100),
        layers: str = Query(default="incidents,perimeters,evacuations", max_length=100),
    ):
        layer_aliases = {
            "incidents": LiveResultKind.INCIDENT,
            "perimeters": LiveResultKind.PERIMETER,
            "evacuations": LiveResultKind.EVACUATION,
        }
        layer_names = [part.strip() for part in layers.split(",") if part.strip()]
        unknown_layers = sorted(set(layer_names) - layer_aliases.keys())
        requested = tuple(
            dict.fromkeys(layer_aliases[name] for name in layer_names if name in layer_aliases)
        )
        if not requested or unknown_layers:
            detail = (
                " Unsupported layers: " + ", ".join(unknown_layers) + "."
                if unknown_layers
                else ""
            )
            return error_response(
                400,
                trace_id=uuid4().hex,
                error_kind="invalid_request",
                message="Select only supported live map layers." + detail,
            )
        parsed_bbox = None
        if bbox is not None:
            try:
                values = tuple(float(value) for value in bbox.split(","))
                if (
                    len(values) != 4
                    or not all(math.isfinite(value) for value in values)
                    or not (-180 <= values[0] < values[2] <= 180)
                    or not (-90 <= values[1] < values[3] <= 90)
                ):
                    raise ValueError
                parsed_bbox = values
            except ValueError:
                return error_response(
                    400,
                    trace_id=uuid4().hex,
                    error_kind="invalid_request",
                    message="bbox must be minLongitude,minLatitude,maxLongitude,maxLatitude.",
                )
        return await current_live_service().map_results(layers=requested, bbox=parsed_bbox)

    if active_config.debug and active_config.deployment_environment != "production":

        @app.post("/api/v1/search", response_model=SearchResponse)
        async def search(request: QueryRequest):
            active_runtime = current_runtime()
            if active_runtime.service is None:
                return error_response(
                    503,
                    trace_id=uuid4().hex,
                    error_kind="not_ready",
                    message="FireLens retrieval is not ready.",
                    retryable=True,
                )
            return await active_runtime.service.search(request)

    async def answer_request(request: QueryRequest):
        request_started = perf_counter()
        active_runtime = current_runtime()
        if active_runtime.service is None:
            return error_response(
                503,
                trace_id=uuid4().hex,
                error_kind="not_ready",
                message="FireLens is not ready.",
                retryable=True,
            )
        initial_plan = plan_query(request)
        if initial_plan.route == QueryRoute.LIVE:
            static_request = live_coordinator.static_request(request)
            static_response = (
                await active_runtime.service.ask(
                    static_request,
                    allow_live=False,
                )
                if static_request is not None
                else None
            )
            live_response = await live_coordinator.answer(request, static_response)
            log_operation(
                trace_id=live_response.trace_id,
                route=QueryRoute.LIVE.value,
                response_mode=live_response.response_mode.value,
                latency_ms=(perf_counter() - request_started) * 1_000,
                provider_stages=(),
                error_category=live_response.error_kind,
            )
            return live_response
        response = await active_runtime.service.ask(request)
        if response.status == ResponseStatus.ERROR:
            return error_response(
                _error_status(response.error_kind),
                trace_id=response.trace_id,
                error_kind=response.error_kind or "provider_error",
                message="The required OpenRouter service is unavailable.",
                retryable=response.error_kind
                in {"rate_limit", "timeout", "unavailable", "model_unavailable"},
            )
        return response

    @app.post(
        "/api/v1/ask",
        response_model=AskResponse,
        responses=ERROR_RESPONSES,
    )
    async def ask(request: QueryRequest):
        try:
            async with asyncio.timeout(active_config.public_request_deadline_seconds):
                return await answer_request(request)
        except TimeoutError:
            trace_id = uuid4().hex
            log_operation(
                trace_id=trace_id,
                route="deadline",
                response_mode=ResponseMode.ABSTENTION.value,
                latency_ms=active_config.public_request_deadline_seconds * 1_000,
                provider_stages=(),
                error_category="timeout",
            )
            return error_response(
                503,
                trace_id=trace_id,
                error_kind="timeout",
                message="FireLens could not complete the request within its public deadline.",
                retryable=True,
            )

    if active_config.debug and active_config.deployment_environment != "production":

        @app.get("/api/v1/debug/chunks/{chunk_id}")
        async def debug_chunk(chunk_id: str):
            active_runtime = current_runtime()
            chunk = active_runtime.chunks_by_id.get(chunk_id)
            if chunk is None:
                return error_response(
                    404,
                    trace_id=uuid4().hex,
                    error_kind="not_found",
                    message="Chunk not found.",
                )
            return chunk

    frontend = active_config.frontend_dist_path
    if frontend is not None and frontend.joinpath("index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app


app = create_app()
