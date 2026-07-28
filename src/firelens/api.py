"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query
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
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    SearchResponse,
)
from firelens.live import LiveDataService, LiveDataUnavailable
from firelens.runtime import Runtime, load_runtime


def _error_status(error_kind: str | None) -> int:
    return 502 if error_kind in {"invalid_request", "invalid_response"} else 503


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope},
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or load_runtime(active_config)
        app.state.live_service = live_service or LiveDataService()
        try:
            yield
        finally:
            if runtime is None:
                await app.state.runtime.aclose()
            if live_service is None:
                await app.state.live_service.aclose()

    app = FastAPI(
        title="FireLens BC Static RAG",
        version="0.1.1",
        description="Evidence-bound stable wildfire guidance; not current status.",
        lifespan=lifespan,
    )
    if runtime is not None:
        app.state.runtime = runtime
    if live_service is not None:
        app.state.live_service = live_service

    def current_runtime() -> Runtime:
        return app.state.runtime

    def current_live_service() -> LiveDataService:
        return app.state.live_service

    def _static_mixed_question(question: str) -> str | None:
        lowered = question.casefold()
        if not any(
            term in lowered for term in ("prepare", "kit", "bag", "smoke", "firesmart", "home")
        ):
            return None
        if "smoke" in lowered:
            return "How can households prepare for wildfire smoke?"
        if any(term in lowered for term in ("firesmart", "home")):
            return "How can households reduce wildfire risk around a home?"
        if any(term in lowered for term in ("kit", "bag")):
            return "What belongs in a household wildfire emergency kit?"
        return "How should households prepare for wildfire?"

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
        requested = tuple(
            layer_aliases[name]
            for name in (part.strip() for part in layers.split(","))
            if name in layer_aliases
        )
        if not requested:
            return error_response(
                400,
                trace_id=uuid4().hex,
                error_kind="invalid_request",
                message="Select at least one supported live map layer.",
            )
        parsed_bbox = None
        if bbox is not None:
            try:
                values = tuple(float(value) for value in bbox.split(","))
                if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
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
            try:
                live = (
                    await current_live_service().nearby_results(request.location)
                    if request.location is not None
                    else await current_live_service().map_results(layers=tuple(LiveResultKind))
                )
            except LiveDataUnavailable:
                live = LiveMapResponse(
                    generated_at=datetime.now(UTC),
                    results=[],
                    unavailable_layers=list(LiveResultKind),
                    limitations=["Official live sources are currently unavailable."],
                )
            if not live.results:
                answer = (
                    "No matching official record was found for this query. This does not mean "
                    "the area is safe; check the issuing authority and BC Wildfire Service map."
                    if len(live.unavailable_layers) < len(LiveResultKind)
                    else "Official live wildfire sources are unavailable, so FireLens cannot establish current conditions."
                )
                return AskResponse(
                    status=ResponseStatus.ABSTENTION,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.ABSTENTION,
                    answer=answer,
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=live.limitations,
                )
            shown = live.results[:100]
            summary = "; ".join(
                f"{item.name or item.incident_number or item.result_id}: {item.status}"
                for item in shown[:5]
            )
            live_answer = "Current official information: " + summary
            mixed_question = _static_mixed_question(request.question)
            if mixed_question is not None:
                static_response = await active_runtime.service.ask(
                    QueryRequest(question=mixed_question, history=request.history)
                )
                if static_response.status == ResponseStatus.ANSWER and static_response.answer:
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
                    )
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.LIVE,
                answer=live_answer,
                live_results=shown,
                limitations=live.limitations,
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
