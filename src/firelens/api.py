"""FastAPI surface for inspectable search and evidence-bound answering."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    HealthResponse,
    QueryRequest,
    ResponseStatus,
    SearchResponse,
)
from firelens.runtime import Runtime, load_runtime


def _error_status(error_kind: str | None) -> int:
    return 502 if error_kind in {"invalid_request", "invalid_response"} else 503


def create_app(
    config: FireLensConfig | None = None,
    *,
    runtime: Runtime | None = None,
) -> FastAPI:
    active_config = config or FireLensConfig.from_env()
    active_runtime = runtime or load_runtime(active_config)
    app = FastAPI(
        title="FireLens BC Static RAG",
        version="0.1.0",
        description="Evidence-bound stable wildfire guidance; not current status.",
    )
    app.state.runtime = active_runtime

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request, exc: RequestValidationError):
        details = [
            {key: value for key, value in error.items() if key != "ctx"}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=400, content={"detail": details})

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return active_runtime.health()

    @app.post("/search", response_model=SearchResponse)
    async def search(request: QueryRequest) -> SearchResponse:
        if active_runtime.service is None:
            raise HTTPException(status_code=503, detail=active_runtime.problems)
        return await active_runtime.service.search(request)

    @app.post("/ask", response_model=AskResponse)
    async def ask(request: QueryRequest) -> AskResponse:
        if active_runtime.service is None:
            raise HTTPException(status_code=503, detail=active_runtime.problems)
        response = await active_runtime.service.ask(request)
        if response.status == ResponseStatus.ERROR:
            raise HTTPException(
                status_code=_error_status(response.error_kind),
                detail=response.model_dump(mode="json"),
            )
        return response

    if active_config.debug:
        @app.get("/debug/chunks/{chunk_id}")
        async def debug_chunk(chunk_id: str):
            chunk = active_runtime.chunks_by_id.get(chunk_id)
            if chunk is None:
                raise HTTPException(status_code=404, detail="Chunk not found.")
            return chunk

    return app


app = create_app()
