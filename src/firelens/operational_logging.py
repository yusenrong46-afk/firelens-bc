"""Privacy-safe structured operational events."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from firelens.contracts import FeedbackCategory

LOGGER_NAME = "firelens.operations"


class OperationalEvent(BaseModel):
    """Content-free event contract suitable for a platform log drain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["firelens.operational_event.v2"]
    event: Literal["firelens_request"]
    trace_id: str = Field(min_length=1, max_length=128)
    route: str = Field(min_length=1, max_length=80)
    response_mode: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    latency_ms: float = Field(ge=0)
    provider_stages: tuple[str, ...] = Field(max_length=20)
    provider_models: tuple[str, ...] = Field(max_length=20)
    error_category: str | None = Field(default=None, max_length=120)
    evidence_count: int = Field(default=0, ge=0)
    claim_count: int = Field(default=0, ge=0)
    live_result_count: int = Field(default=0, ge=0)
    validation_disposition: Literal["accepted", "rejected", "not_applicable"]
    corpus_version: str | None = Field(default=None, max_length=200)
    release_version: str = Field(min_length=1, max_length=100)
    build_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    deployment_environment: Literal["local", "preview", "production"]


class FeedbackEvent(BaseModel):
    """Strict content-free feedback event for the restricted operations view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["firelens.feedback_event.v1"]
    event: Literal["firelens_feedback"]
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    category: FeedbackCategory
    release_version: str = Field(min_length=1, max_length=100)
    build_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    deployment_environment: Literal["local", "preview", "production"]


def log_operation(
    *,
    trace_id: str,
    route: str,
    response_mode: str,
    status: str,
    latency_ms: float,
    provider_stages: Sequence[str] = (),
    provider_models: Sequence[str] = (),
    error_category: str | None = None,
    evidence_count: int = 0,
    claim_count: int = 0,
    live_result_count: int = 0,
    validation_disposition: Literal[
        "accepted", "rejected", "not_applicable"
    ] = "not_applicable",
    corpus_version: str | None = None,
    release_version: str,
    build_commit: str | None = None,
    deployment_environment: Literal["local", "preview", "production"] = "local",
) -> None:
    """Log only the allowlisted operational fields; never accept request content."""

    event = OperationalEvent(
        schema_version="firelens.operational_event.v2",
        event="firelens_request",
        trace_id=trace_id,
        route=route,
        response_mode=response_mode,
        status=status,
        latency_ms=round(max(latency_ms, 0.0), 1),
        provider_stages=tuple(sorted(set(provider_stages))),
        provider_models=tuple(sorted(set(provider_models))),
        error_category=error_category,
        evidence_count=evidence_count,
        claim_count=claim_count,
        live_result_count=live_result_count,
        validation_disposition=validation_disposition,
        corpus_version=corpus_version,
        release_version=release_version,
        build_commit=build_commit,
        deployment_environment=deployment_environment,
    )
    logging.getLogger(LOGGER_NAME).info(
        json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def log_feedback(
    *,
    trace_id: str,
    category: FeedbackCategory,
    release_version: str,
    build_commit: str | None = None,
    deployment_environment: Literal["local", "preview", "production"] = "local",
) -> None:
    """Emit only the two user-supplied allowlisted feedback fields."""

    event = FeedbackEvent(
        schema_version="firelens.feedback_event.v1",
        event="firelens_feedback",
        trace_id=trace_id,
        category=category,
        release_version=release_version,
        build_commit=build_commit,
        deployment_environment=deployment_environment,
    )
    logging.getLogger(LOGGER_NAME).info(
        json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
