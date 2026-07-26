"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    ErrorEnvelope,
    HealthResponse,
    LivenessResponse,
    QueryRequest,
    ResponseStatus,
    SearchResponse,
)
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
) -> FastAPI:
    active_config = config or FireLensConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or load_runtime(active_config)
        try:
            yield
        finally:
            if runtime is None:
                await app.state.runtime.aclose()

    app = FastAPI(
        title="FireLens BC Static RAG",
        version="0.1.0",
        description="Evidence-bound stable wildfire guidance; not current status.",
        lifespan=lifespan,
    )
    if runtime is not None:
        app.state.runtime = runtime

    def current_runtime() -> Runtime:
        return app.state.runtime

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
