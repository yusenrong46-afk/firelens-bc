"""Health and content-free feedback routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, Response

from firelens.api.responses import ERROR_RESPONSES
from firelens.config import FireLensConfig
from firelens.contract_base import FrozenStrictModel
from firelens.contracts import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    LivenessResponse,
)
from firelens.operational_logging import log_feedback, log_product_event
from firelens.runtime import Runtime

ProductEventName = Literal[
    "guided_catalog_opened",
    "guided_question_selected",
    "live_summary_loaded",
    "map_opened",
    "evidence_opened",
    "authority_handoff_opened",
    "analysis_exported",
    "saved_scope_added",
    "feedback_submitted",
]


class ProductEventRequest(FrozenStrictModel):
    event: ProductEventName


class ProductEventResponse(FrozenStrictModel):
    accepted: Literal[True] = True


def install_health_feedback_routes(
    app: FastAPI,
    config: FireLensConfig,
    current_runtime: Callable[[], Runtime],
) -> None:
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
            release_version=config.release_version,
            build_commit=config.build_commit,
            deployment_environment=config.deployment_environment,
        )
        return FeedbackResponse()

    @app.post(
        "/api/v1/product-events",
        response_model=ProductEventResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
    )
    async def product_event(payload: ProductEventRequest) -> ProductEventResponse:
        log_product_event(
            event=payload.event,
            release_version=config.release_version,
            build_commit=config.build_commit,
            deployment_environment=config.deployment_environment,
        )
        return ProductEventResponse()
