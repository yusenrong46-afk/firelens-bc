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

    schema_version: Literal["firelens.operational_event.v3"]
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
    tool_names: tuple[str, ...] = Field(default=(), max_length=20)
    tool_attempts: int = Field(default=0, ge=0)
    retrieval_cycles: int = Field(default=0, ge=0)
    cache_used: bool | None = None
    stage_latency_ms: float | None = Field(default=None, ge=0)
    fallback_category: str | None = Field(default=None, max_length=120)
    candidate_id: str | None = Field(default=None, max_length=200)
    stage_metrics: tuple[StageMetric, ...] = Field(default=(), max_length=12)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class StageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal[
        "planning",
        "official_live_fetch",
        "retrieval",
        "reranking",
        "generation",
        "validation",
        "total",
    ]
    latency_ms: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    cache_state: Literal["hit", "miss", "unknown"] | None = None
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)


class ProductEvent(BaseModel):
    """Allowlisted UI telemetry. Never includes question, place, or identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["firelens.product_event.v1"] = "firelens.product_event.v1"
    event: Literal[
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
    release_version: str = Field(min_length=1, max_length=100)
    build_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    deployment_environment: Literal["local", "preview", "production"] = "local"


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


def usage_tokens(usage: object, *names: str) -> int | None:
    """Read a numeric token field from provider usage. Never inspects content."""

    if not isinstance(usage, dict):
        return None
    for name in names:
        value = usage.get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
    return None


def usage_cost_usd(usage: object) -> float | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get("cost")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def request_stage_metrics(
    *,
    latency_ms: float,
    provider_stages: Sequence[str] = (),
    provider_models: Sequence[str] = (),
    cache_used: bool | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    cost_usd: float | None = None,
) -> tuple[StageMetric, ...]:
    """Build content-free stage metrics. Unknown per-stage times stay off the record."""

    cache_state: Literal["hit", "miss", "unknown"] = (
        "hit" if cache_used is True else "miss" if cache_used is False else "unknown"
    )
    return (
        StageMetric(
            stage="total",
            latency_ms=round(max(latency_ms, 0.0), 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=cost_usd,
            cache_state=cache_state,
            provider=next(iter(provider_stages), None),
            model=next(iter(provider_models), None),
        ),
    )


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
    tool_names: Sequence[str] = (),
    tool_attempts: int = 0,
    retrieval_cycles: int = 0,
    cache_used: bool | None = None,
    stage_latency_ms: float | None = None,
    fallback_category: str | None = None,
    candidate_id: str | None = None,
    stage_metrics: Sequence[StageMetric] | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Log only the allowlisted operational fields; never accept request content."""

    metrics = (
        tuple(stage_metrics)
        if stage_metrics is not None
        else request_stage_metrics(
            latency_ms=latency_ms,
            provider_stages=provider_stages,
            provider_models=provider_models,
            cache_used=cache_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
    )
    event = OperationalEvent(
        schema_version="firelens.operational_event.v3",
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
        tool_names=tuple(name for name in tool_names if name)[:20],
        tool_attempts=max(tool_attempts, 0),
        retrieval_cycles=max(retrieval_cycles, 0),
        cache_used=cache_used,
        stage_latency_ms=(
            round(max(stage_latency_ms, 0.0), 1) if stage_latency_ms is not None else None
        ),
        fallback_category=fallback_category,
        candidate_id=candidate_id,
        stage_metrics=metrics,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
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


def log_product_event(
    *,
    event: str,
    release_version: str,
    build_commit: str | None = None,
    deployment_environment: Literal["local", "preview", "production"] = "local",
) -> ProductEvent:
    payload = ProductEvent.model_validate(
        {
            "event": event,
            "release_version": release_version,
            "build_commit": build_commit,
            "deployment_environment": deployment_environment,
        }
    )
    logging.getLogger(LOGGER_NAME).info(
        json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return payload
