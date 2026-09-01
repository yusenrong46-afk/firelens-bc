"""Evidence-bound Ask plus development-only search and chunk routes."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from firelens.agent import FireLensAgent
from firelens.api.responses import (
    ERROR_RESPONSES,
    deadline_response,
    error_response,
    provider_error_status,
)
from firelens.api_contracts import (
    GuidedQuestionCategory,
    GuidedQuestionItem,
    GuidedQuestionsResponse,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    QueryRequest,
    ResponseStatus,
    SearchResponse,
)
from firelens.guidance_capabilities import (
    advertised_guided_questions,
    guided_catalogue_sha256,
    load_guided_question_registry,
)
from firelens.ingestion.chunking import ChunkRecord
from firelens.live_answering import LiveAnswerCoordinator
from firelens.operational_logging import log_operation
from firelens.runtime import Runtime

_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _validation_disposition(
    response: AskResponse,
) -> Literal["accepted", "rejected", "not_applicable"]:
    if response.validation is None:
        return "not_applicable"
    return "accepted" if response.validation.accepted else "rejected"


async def _answer_request(
    request: QueryRequest,
    *,
    config: FireLensConfig,
    runtime: Runtime,
    live_coordinator: LiveAnswerCoordinator,
) -> AskResponse | JSONResponse:
    request_started = perf_counter()
    if runtime.service is None:
        return error_response(
            503,
            trace_id=uuid4().hex,
            error_kind="not_ready",
            message="FireLens is not ready.",
            retryable=True,
        )
    execution = await FireLensAgent(runtime.service, live_coordinator).answer(request)
    response = execution.response
    if response.status == ResponseStatus.ERROR:
        return error_response(
            provider_error_status(response.error_kind),
            trace_id=response.trace_id,
            error_kind=response.error_kind or "provider_error",
            message="The required OpenRouter service is unavailable.",
            retryable=response.error_kind
            in {"rate_limit", "timeout", "unavailable", "model_unavailable"},
        )
    latency_ms = (perf_counter() - request_started) * 1_000
    log_operation(
        trace_id=response.trace_id,
        route=execution.route.value,
        response_mode=response.response_mode.value,
        status=response.status.value,
        latency_ms=latency_ms,
        provider_stages=tuple(execution.policy.provider_stages),
        error_category=response.error_kind,
        evidence_count=len(response.evidence),
        claim_count=len(response.claims),
        live_result_count=len(response.live_results),
        validation_disposition=_validation_disposition(response),
        corpus_version=runtime.corpus_version,
        release_version=config.release_version,
        build_commit=(
            config.build_commit if _FULL_COMMIT.match(config.build_commit or "") else None
        ),
        deployment_environment=config.deployment_environment,
        tool_names=tuple(tool.value for tool in execution.tools),
        tool_attempts=execution.policy.tool_rounds + execution.policy.outer_chat_turns,
        retrieval_cycles=execution.policy.retrieval_cycles,
        cache_used=execution.policy.cache_used,
        stage_latency_ms=latency_ms,
        fallback_category=execution.policy.fallback_reason,
        candidate_id=(
            None
            if runtime.bound_candidate is None
            else str(runtime.bound_candidate["candidate_id"])
        ),
    )
    return response


def install_answer_routes(
    app: FastAPI,
    config: FireLensConfig,
    current_runtime: Callable[[], Runtime],
    live_coordinator: LiveAnswerCoordinator,
) -> None:
    @app.get("/api/v1/guided-questions", response_model=GuidedQuestionsResponse)
    async def guided_questions() -> GuidedQuestionsResponse:
        """Return the frozen client catalogue without exposing routing internals."""

        registry = load_guided_question_registry(str(config.project_root))
        advertised = {item.id for item in advertised_guided_questions(str(config.project_root))}
        return GuidedQuestionsResponse(
            schema_version=registry.schema_version,
            catalogue_sha256=guided_catalogue_sha256(str(config.project_root)),
            categories=[
                GuidedQuestionCategory(
                    id=category.id,
                    label=category.label,
                    questions=[
                        GuidedQuestionItem(
                            id=item.id,
                            label=item.label,
                            question=item.question,
                            location_mode=item.location_mode,
                            source_lane=item.source_lane,
                        )
                        for item in category.questions
                        if item.id in advertised
                    ],
                )
                for category in registry.categories
                if any(item.id in advertised for item in category.questions)
            ],
        )

    if config.debug and config.deployment_environment != "production":

        @app.post("/api/v1/search", response_model=SearchResponse)
        async def search(request: QueryRequest) -> SearchResponse | JSONResponse:
            runtime = current_runtime()
            if runtime.service is None:
                return error_response(
                    503,
                    trace_id=uuid4().hex,
                    error_kind="not_ready",
                    message="FireLens retrieval is not ready.",
                    retryable=True,
                )
            return await runtime.service.search(request)

    @app.post(
        "/api/v1/ask",
        response_model=AskResponse,
        responses=ERROR_RESPONSES,
    )
    async def ask(request: QueryRequest) -> AskResponse | JSONResponse:
        try:
            async with asyncio.timeout(config.public_request_deadline_seconds):
                return await _answer_request(
                    request,
                    config=config,
                    runtime=current_runtime(),
                    live_coordinator=live_coordinator,
                )
        except TimeoutError:
            return deadline_response(config, "ask")

    if config.debug and config.deployment_environment != "production":

        @app.get(
            "/api/v1/debug/chunks/{chunk_id}",
            include_in_schema=False,
            response_model=None,
        )
        async def debug_chunk(chunk_id: str) -> ChunkRecord | JSONResponse:
            chunk = current_runtime().chunks_by_id.get(chunk_id)
            if chunk is None:
                return error_response(
                    404,
                    trace_id=uuid4().hex,
                    error_kind="not_found",
                    message="Chunk not found.",
                )
            return chunk
