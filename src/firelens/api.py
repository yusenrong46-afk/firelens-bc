"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from firelens.answering.intent import plan_query
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    ErrorEnvelope,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    LiveMapResponse,
    LivenessResponse,
    LiveResultKind,
    NearMeRequest,
    NearMeResponse,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    ResponseStatus,
    SearchResponse,
)
from firelens.ingestion.chunking import ChunkRecord
from firelens.live import LiveDataErrorKind, LiveDataService, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator
from firelens.operational_logging import log_feedback, log_operation
from firelens.request_guard import AnonymousRequestGuard
from firelens.runtime import Runtime, load_runtime


def _error_status(error_kind: str | None) -> int:
    return 502 if error_kind in {"invalid_request", "invalid_response"} else 503


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope, "description": "Content Too Large"},
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
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
        return cast(Runtime, app.state.runtime)

    def current_live_service() -> LiveDataService:
        return cast(LiveDataService, app.state.live_service)

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

    def deadline_response(route: str) -> JSONResponse:
        trace_id = uuid4().hex
        log_operation(
            trace_id=trace_id,
            route=route,
            response_mode=ResponseMode.ABSTENTION.value,
            status=ResponseStatus.ERROR.value,
            latency_ms=active_config.public_request_deadline_seconds * 1_000,
            provider_stages=(),
            error_category="timeout",
            release_version=active_config.release_version,
            build_commit=active_config.build_commit,
            deployment_environment=active_config.deployment_environment,
        )
        return error_response(
            503,
            trace_id=trace_id,
            error_kind="timeout",
            message="FireLens could not complete the request within its public deadline.",
            retryable=True,
        )

    @app.middleware("http")
    async def bounded_anonymous_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        guarded = request.url.path in {
            "/api/v1/ask",
            "/api/v1/live/map",
            "/api/v1/live/nearby",
            "/api/v1/feedback",
        }
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
            limited_response = error_response(
                429,
                trace_id=uuid4().hex,
                error_kind="rate_limit",
                message="The anonymous FireLens request limit was reached. Try again shortly.",
                retryable=True,
            )
            limited_response.headers["Retry-After"] = str(decision.retry_after_seconds)
            limited_response.headers["X-RateLimit-Limit"] = str(request_guard.limit)
            limited_response.headers["X-RateLimit-Remaining"] = "0"
            limited_response.headers["X-RateLimit-Scope"] = "instance-local"
            return limited_response
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
        guarded_response = await call_next(request)
        guarded_response.headers["X-RateLimit-Limit"] = str(request_guard.limit)
        guarded_response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        guarded_response.headers["X-RateLimit-Scope"] = "instance-local"
        return guarded_response

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; "
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
        content_type = response.headers.get("content-type", "").lower()
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif content_type.startswith("text/html"):
            # A cached SPA shell can reference fingerprinted assets that no longer
            # exist after a deployment, leaving returning users with a blank page.
            # Keep fingerprinted assets cacheable while forcing HTML to be fetched
            # again for every release.
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {key: value for key, value in error.items() if key != "ctx"}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422 if request.url.path == "/api/v1/feedback" else 400,
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
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
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

    @app.post(
        "/api/v1/feedback",
        response_model=FeedbackResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
    )
    async def feedback(payload: FeedbackRequest) -> FeedbackResponse:
        log_feedback(
            trace_id=payload.trace_id,
            category=payload.category,
            release_version=active_config.release_version,
            build_commit=active_config.build_commit,
            deployment_environment=active_config.deployment_environment,
        )
        return FeedbackResponse()

    async def map_request(
        bbox: str | None = Query(default=None, max_length=100),
        layers: str = Query(default="incidents,perimeters,evacuations", max_length=100),
    ) -> LiveMapResponse | JSONResponse:
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

    @app.get(
        "/api/v1/live/map",
        response_model=LiveMapResponse,
        responses=ERROR_RESPONSES,
    )
    async def live_map(
        bbox: str | None = Query(default=None, max_length=100),
        layers: str = Query(default="incidents,perimeters,evacuations", max_length=100),
    ) -> LiveMapResponse | JSONResponse:
        try:
            async with asyncio.timeout(active_config.public_request_deadline_seconds):
                return await map_request(bbox, layers)
        except TimeoutError:
            return deadline_response("live_map")

    @app.post(
        "/api/v1/live/nearby",
        response_model=NearMeResponse,
        responses=ERROR_RESPONSES,
    )
    async def live_nearby(payload: NearMeRequest) -> NearMeResponse | JSONResponse:
        request_started = perf_counter()
        try:
            async with asyncio.timeout(active_config.public_request_deadline_seconds):
                result = await current_live_service().nearby_page(
                    payload.location,
                    layers=tuple(payload.layers),
                    page=payload.page,
                    page_size=payload.page_size,
                )
            log_operation(
                trace_id=uuid4().hex,
                route="live_nearby",
                response_mode=ResponseMode.LIVE.value,
                status=ResponseStatus.ANSWER.value,
                latency_ms=(perf_counter() - request_started) * 1_000,
                live_result_count=len(result.results),
                release_version=active_config.release_version,
                build_commit=active_config.build_commit,
                deployment_environment=active_config.deployment_environment,
            )
            return result
        except TimeoutError:
            return deadline_response("live_nearby")
        except LiveDataUnavailable as exc:
            trace_id = uuid4().hex
            status_code = {
                LiveDataErrorKind.NOT_FOUND: 404,
                LiveDataErrorKind.INVALID_RESPONSE: 502,
            }.get(exc.kind, 503)
            log_operation(
                trace_id=trace_id,
                route="live_nearby",
                response_mode=ResponseMode.ABSTENTION.value,
                status=ResponseStatus.ERROR.value,
                latency_ms=(perf_counter() - request_started) * 1_000,
                error_category=f"live_{exc.kind.value}",
                release_version=active_config.release_version,
                build_commit=active_config.build_commit,
                deployment_environment=active_config.deployment_environment,
            )
            return error_response(
                status_code,
                trace_id=trace_id,
                error_kind=f"live_{exc.kind.value}",
                message=str(exc),
                retryable=exc.kind
                in {
                    LiveDataErrorKind.TIMEOUT,
                    LiveDataErrorKind.UPSTREAM_HTTP,
                    LiveDataErrorKind.UNREACHABLE,
                },
            )

    if active_config.debug and active_config.deployment_environment != "production":

        @app.post("/api/v1/search", response_model=SearchResponse)
        async def search(request: QueryRequest) -> SearchResponse | JSONResponse:
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

    async def answer_request(request: QueryRequest) -> AskResponse | JSONResponse:
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
                status=live_response.status.value,
                latency_ms=(perf_counter() - request_started) * 1_000,
                provider_stages=(),
                error_category=live_response.error_kind,
                evidence_count=len(live_response.evidence),
                claim_count=len(live_response.claims),
                live_result_count=len(live_response.live_results),
                validation_disposition=(
                    "accepted"
                    if live_response.validation is not None
                    and live_response.validation.accepted
                    else "rejected"
                    if live_response.validation is not None
                    else "not_applicable"
                ),
                corpus_version=active_runtime.corpus_version,
                release_version=active_config.release_version,
                build_commit=active_config.build_commit,
                deployment_environment=active_config.deployment_environment,
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
    async def ask(request: QueryRequest) -> AskResponse | JSONResponse:
        try:
            async with asyncio.timeout(active_config.public_request_deadline_seconds):
                return await answer_request(request)
        except TimeoutError:
            return deadline_response("ask")

    if active_config.debug and active_config.deployment_environment != "production":

        @app.get(
            "/api/v1/debug/chunks/{chunk_id}",
            include_in_schema=False,
            response_model=None,
        )
        async def debug_chunk(chunk_id: str) -> ChunkRecord | JSONResponse:
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
        assets = frontend / "assets"

        def frontend_entry_response(asset_hash: str, suffix: str) -> Response:
            if re.fullmatch(r"[A-Za-z0-9_-]+", asset_hash) is None:
                return Response(status_code=404)
            requested = assets / f"index-{asset_hash}.{suffix}"
            candidate = requested if requested.is_file() else None
            if candidate is None:
                index_html = frontend.joinpath("index.html").read_text(encoding="utf-8")
                match = re.search(
                    rf'(?:src|href)=["\']/assets/'
                    rf'(index-[A-Za-z0-9_-]+\.{re.escape(suffix)})["\']',
                    index_html,
                )
                if match is not None:
                    current = assets / match.group(1)
                    candidate = current if current.is_file() else None
            if candidate is None:
                return Response(status_code=404)
            media_type = "text/javascript" if suffix == "js" else "text/css"
            return FileResponse(
                candidate,
                media_type=media_type,
                headers={"Cache-Control": "no-store"},
            )

        @app.get("/assets/index-{asset_hash}.js", include_in_schema=False)
        async def frontend_javascript_entry(asset_hash: str) -> Response:
            return frontend_entry_response(asset_hash, "js")

        @app.get("/assets/index-{asset_hash}.css", include_in_schema=False)
        async def frontend_stylesheet_entry(asset_hash: str) -> Response:
            return frontend_entry_response(asset_hash, "css")

        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app


app = create_app()
