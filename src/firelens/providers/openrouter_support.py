"""Private wire-schema and resilience helpers for the OpenRouter adapter."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from firelens.contracts import BackgroundDraft, GroundedDraft

_CANONICAL_RESPONSE_MODELS: dict[str, frozenset[str]] = {
    "openai/text-embedding-3-small": frozenset(
        {"openai/text-embedding-3-small", "text-embedding-3-small"}
    ),
    "cohere/rerank-4-pro": frozenset({"cohere/rerank-4-pro", "rerank-v4.0-pro"}),
}

ProviderStage = Literal[
    "embedding",
    "reranking",
    "planning",
    "context_generation",
    "grounded_generation",
    "background_generation",
]
PROVIDER_STAGES: tuple[ProviderStage, ...] = (
    "embedding",
    "reranking",
    "planning",
    "context_generation",
    "grounded_generation",
    "background_generation",
)


@dataclass
class CircuitState:
    """Local circuit-breaker state for one provider stage."""

    consecutive_failures: int = 0
    open_until_monotonic: float = 0.0
    probe_in_flight: bool = False
    observed_success: bool = False


@dataclass
class StagePressureState:
    """Adaptive concurrency state for one provider stage."""

    limit: int
    active: int = 0
    consecutive_successes: int = 0
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)


def wire_draft_schema(output_schema: dict[str, Any]) -> dict[str, Any]:
    """Remove the redundant local draft-family discriminator from the wire schema.

    Grounded and background generation already select distinct provider operations,
    prompts, and schemas. The model therefore has no authority to choose the family.
    """

    schema = deepcopy(output_schema)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("answer_type", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field != "answer_type"]
    return schema


def strict_wire_schema(output_schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize object schemas for OpenAI strict structured outputs."""

    schema = deepcopy(output_schema)

    def normalize(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if node.get("type") == "object" and isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


def locally_type_draft(
    payload: dict[str, Any], *, answer_type: str
) -> GroundedDraft | BackgroundDraft:
    """Add the operation-owned family only after rejecting wire discriminators."""

    if "answer_type" in payload:
        raise ValueError("provider returned a model-owned draft discriminator")
    typed_payload = {"answer_type": answer_type, **payload}
    if answer_type == "grounded":
        return GroundedDraft.model_validate(typed_payload)
    return BackgroundDraft.model_validate(typed_payload)


def model_identity_matches(requested: str, returned: object) -> bool:
    """Accept only the requested model or its explicitly frozen canonical alias."""

    if not isinstance(returned, str):
        return False
    allowed = _CANONICAL_RESPONSE_MODELS.get(requested, frozenset({requested}))
    return returned in allowed


def retry_after_seconds(value: str | None) -> float | None:
    """Parse the standard Retry-After forms without trusting invalid values."""

    if value is None:
        return None
    raw = value.strip()
    if raw.isascii() and raw.isdigit():
        return float(int(raw))
    try:
        retry_at = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None or retry_at.utcoffset() is None:
        return None
    return max(0.0, (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())
