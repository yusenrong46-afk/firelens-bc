"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    static_guidance_fragment,
    unsupported_live_topics,
)
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
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    SearchResponse,
)
from firelens.live import LiveDataService, LiveDataUnavailable
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
    request_guard = AnonymousRequestGuard(
        limit=active_config.anonymous_rate_limit,
        window_seconds=active_config.anonymous_rate_window_seconds,
        max_body_bytes=active_config.max_request_body_bytes,
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
        body = await request.body()
        if len(body) > request_guard.max_body_bytes:
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
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(request_guard.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Scope"] = "instance-local"
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
    async def readiness() -> HealthResponse:
        return current_runtime().health()

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

    if active_config.debug:

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

    @app.post(
        "/api/v1/ask",
        response_model=AskResponse,
        responses=ERROR_RESPONSES,
    )
    async def ask(request: QueryRequest):
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
            layers = live_layers_for_question(request.question)
            unsupported_topics = unsupported_live_topics(request.question)
            mixed_question = static_guidance_fragment(request.question)
            static_response = (
                await active_runtime.service.ask(
                    QueryRequest(question=mixed_question, history=request.history),
                    allow_live=False,
                )
                if mixed_question is not None
                else None
            )

            def supported_static_partial(
                current_information: str,
                *,
                limitations: list[str],
                unavailable_layers: list[LiveResultKind] | None = None,
            ) -> AskResponse | None:
                if not (
                    static_response is not None
                    and static_response.status == ResponseStatus.ANSWER
                    and static_response.response_mode
                    in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
                    and static_response.answer
                    and static_response.claims
                    and static_response.evidence
                    and static_response.validation is not None
                    and static_response.validation.accepted
                ):
                    return None
                return AskResponse(
                    status=ResponseStatus.ANSWER,
                    trace_id=static_response.trace_id,
                    response_mode=ResponseMode.PARTIAL,
                    answer=(
                        "Current official information: "
                        + current_information
                        + "\n\nPreparedness guidance: "
                        + static_response.answer
                        + "\n\nUncertainty: the current-information part was not established."
                    ),
                    claims=static_response.claims,
                    evidence=static_response.evidence,
                    limitations=[*limitations, *static_response.limitations],
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    validation=static_response.validation,
                    unavailable_layers=unavailable_layers or [],
                )

            if not layers:
                topics = ", ".join(unsupported_topics) or "that live information"
                current_gap = (
                    f"FireLens V1.5 does not have an official live source for {topics}."
                )
                partial = supported_static_partial(
                    current_gap,
                    limitations=[
                        "No matching record is not a safety determination.",
                        f"Unsupported live topics: {topics}",
                    ],
                )
                if partial is not None:
                    return partial
                return AskResponse(
                    status=ResponseStatus.ABSTENTION,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.ABSTENTION,
                    answer=(
                        f"FireLens V1.5 does not have an official live source for {topics}. "
                        "It will not substitute wildfire incident records for the requested data."
                    ),
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=["No matching record is not a safety determination."],
                )
            if request.location is None and live_query_requires_location(request.question):
                location_gap = (
                    "A city or approximate location must be supplied in the location field; "
                    "FireLens does not infer it from conversation text."
                )
                partial = supported_static_partial(
                    location_gap,
                    limitations=["No matching record is not a safety determination."],
                )
                if partial is not None:
                    return partial
                return AskResponse(
                    status=ResponseStatus.ABSTENTION,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.ABSTENTION,
                    answer=(
                        "Share a city or approximate location for this live query, or open "
                        "the official BC Wildfire Service map. FireLens does not infer location."
                    ),
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=["No matching record is not a safety determination."],
                )
            try:
                live = (
                    await current_live_service().nearby_results(request.location, layers=layers)
                    if request.location is not None
                    else await current_live_service().map_results(layers=layers)
                )
            except LiveDataUnavailable:
                live = LiveMapResponse(
                    generated_at=datetime.now(UTC),
                    results=[],
                    unavailable_layers=list(layers),
                    limitations=["Official live sources are currently unavailable."],
                )
            if not live.results:
                answer = (
                    "No matching official record was found for this query. This does not mean "
                    "the area is safe; check the issuing authority and BC Wildfire Service map."
                    if len(live.unavailable_layers) < len(layers)
                    else "Official live wildfire sources are unavailable, so FireLens cannot establish current conditions."
                )
                partial = supported_static_partial(
                    answer,
                    limitations=[
                        *live.limitations,
                        "No matching record is not a safety determination.",
                        *(
                            ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                            if unsupported_topics
                            else []
                        ),
                    ],
                    unavailable_layers=live.unavailable_layers,
                )
                if partial is not None:
                    return partial
                return AskResponse(
                    status=ResponseStatus.ABSTENTION,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.ABSTENTION,
                    answer=answer,
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=[
                        *live.limitations,
                        *(
                            ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                            if unsupported_topics
                            else []
                        ),
                    ],
                    unavailable_layers=live.unavailable_layers,
                )
            shown = live.results[:100]
            summary = "; ".join(
                f"{item.name or item.incident_number or item.result_id}: {item.status}"
                for item in shown[:5]
            )
            live_answer = "Current official information: " + summary
            if static_response is not None:
                if (
                    static_response.status == ResponseStatus.ANSWER
                    and static_response.response_mode
                    in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
                    and static_response.answer
                    and static_response.claims
                    and static_response.evidence
                    and static_response.validation is not None
                    and static_response.validation.accepted
                ):
                    return AskResponse(
                        status=ResponseStatus.ANSWER,
                        trace_id=static_response.trace_id,
                        response_mode=ResponseMode.MIXED,
                        answer=(
                            live_answer + "\n\nPreparedness guidance: " + static_response.answer
                        ),
                        claims=static_response.claims,
                        evidence=static_response.evidence,
                        live_results=shown,
                        limitations=[*live.limitations, *static_response.limitations],
                        validation=static_response.validation,
                        unavailable_layers=live.unavailable_layers,
                    )
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.LIVE,
                answer=live_answer,
                live_results=shown,
                limitations=[
                    *live.limitations,
                    *(
                        ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                        if unsupported_topics
                        else []
                    ),
                ],
                unavailable_layers=live.unavailable_layers,
            )
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

    if active_config.debug:

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
