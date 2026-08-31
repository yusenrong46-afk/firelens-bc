"""Structured operation parsing for the OpenRouter transport adapter."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from firelens.contracts import (
    DocumentContextDraft,
    DocumentContextResponse,
    GenerationResponse,
    PlanningDecision,
    PlanningResponse,
)
from firelens.errors import ProviderError, ProviderErrorKind
from firelens.providers.openrouter_support import (
    ProviderStage,
    locally_type_draft,
    model_identity_matches,
    wire_draft_schema,
)


async def chat_json(
    provider: Any,
    messages: Sequence[dict[str, str]],
    *,
    output_schema: dict[str, Any],
    schema_name: str,
    max_tokens: int,
    stage: ProviderStage,
) -> tuple[dict[str, Any], str, dict[str, Any], int]:
    body, attempts = await provider._post(
        stage,
        "chat/completions",
        {
            "model": provider.config.generation_model,
            "messages": list(messages),
            "stream": False,
            "max_tokens": max_tokens,
            **provider._generation_sampling_parameters(),
            "provider": provider._provider_preferences(stage),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": provider._generation_output_schema(output_schema),
                },
            },
        },
    )
    try:
        if not model_identity_matches(provider.config.generation_model, body.get("model")):
            raise ValueError("generation model mismatch")
        content = body["choices"][0]["message"]["content"]
        payload = json.loads(content) if isinstance(content, str) else content
        if not isinstance(payload, dict):
            raise ValueError("structured response is not an object")
        return (
            payload,
            str(body.get("model", provider.config.generation_model)),
            body.get("usage") or {},
            attempts,
        )
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        error = ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned invalid structured JSON.",
        )
        await provider._record_stage_failure(stage, error)
        raise error from exc


async def plan(
    provider: Any, messages: Sequence[dict[str, str]], *, output_schema: dict[str, Any]
) -> PlanningResponse:
    payload, model, usage, attempts = await chat_json(
        provider,
        messages,
        output_schema=output_schema,
        schema_name="firelens_query_plan",
        max_tokens=500,
        stage="planning",
    )
    try:
        decision = PlanningDecision.model_validate(payload)
    except ValidationError as exc:
        error = ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned an invalid structured plan.",
        )
        await provider._record_stage_failure("planning", error)
        raise error from exc
    response = PlanningResponse(model=model, decision=decision, usage=usage, attempts=attempts)
    await provider._record_stage_success("planning")
    return response


async def generate_contexts(
    provider: Any, messages: Sequence[dict[str, str]], *, output_schema: dict[str, Any]
) -> DocumentContextResponse:
    payload, model, usage, attempts = await chat_json(
        provider,
        messages,
        output_schema=output_schema,
        schema_name="firelens_document_context",
        max_tokens=1_800,
        stage="context_generation",
    )
    try:
        draft = DocumentContextDraft.model_validate(payload)
    except ValidationError as exc:
        error = ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned invalid document contexts.",
        )
        await provider._record_stage_failure("context_generation", error)
        raise error from exc
    response = DocumentContextResponse(model=model, draft=draft, usage=usage, attempts=attempts)
    await provider._record_stage_success("context_generation")
    return response


async def generate_grounded(
    provider: Any, messages: Sequence[dict[str, str]], *, output_schema: dict[str, Any]
) -> GenerationResponse:
    payload, model, usage, attempts = await chat_json(
        provider,
        messages,
        output_schema=wire_draft_schema(output_schema),
        schema_name="firelens_grounded_answer",
        max_tokens=1_200,
        stage="grounded_generation",
    )
    try:
        draft = locally_type_draft(payload, answer_type="grounded")
    except (ValidationError, ValueError) as exc:
        error = ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned an invalid grounded answer.",
        )
        await provider._record_stage_failure("grounded_generation", error)
        raise error from exc
    response = GenerationResponse(model=model, draft=draft, usage=usage, attempts=attempts)
    await provider._record_stage_success("grounded_generation")
    return response


async def generate_background(
    provider: Any, messages: Sequence[dict[str, str]], *, output_schema: dict[str, Any]
) -> GenerationResponse:
    payload, model, usage, attempts = await chat_json(
        provider,
        messages,
        output_schema=wire_draft_schema(output_schema),
        schema_name="firelens_background_answer",
        max_tokens=500,
        stage="background_generation",
    )
    try:
        draft = locally_type_draft(payload, answer_type="background")
    except (ValidationError, ValueError) as exc:
        error = ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned an invalid background answer.",
        )
        await provider._record_stage_failure("background_generation", error)
        raise error from exc
    response = GenerationResponse(model=model, draft=draft, usage=usage, attempts=attempts)
    await provider._record_stage_success("background_generation")
    return response
