"""OpenRouter HTTP adapter. No FireLens policy decisions belong here."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from copy import deepcopy
from typing import Any

import httpx
from pydantic import ValidationError

from firelens.config import FireLensConfig
from firelens.contracts import (
    BackgroundDraft,
    DocumentContextDraft,
    DocumentContextResponse,
    EmbeddingResponse,
    GenerationResponse,
    GroundedDraft,
    PlanningDecision,
    PlanningResponse,
    RerankResponse,
    RerankResult,
)
from firelens.errors import ProviderError, ProviderErrorKind

_CANONICAL_RESPONSE_MODELS: dict[str, frozenset[str]] = {
    "openai/text-embedding-3-small": frozenset(
        {"openai/text-embedding-3-small", "text-embedding-3-small"}
    ),
    "cohere/rerank-4-pro": frozenset({"cohere/rerank-4-pro", "rerank-v4.0-pro"}),
}


def _wire_draft_schema(output_schema: dict[str, Any]) -> dict[str, Any]:
    """Remove the redundant local draft-family discriminator from the wire schema.

    ``generate_grounded`` and ``generate_background`` already select distinct
    provider operations, prompts, and schemas.  The model therefore has no
    authority to choose the family.  Omitting that redundant field avoids
    repairing provider output while keeping every model-supplied field under a
    strict JSON Schema.
    """

    schema = deepcopy(output_schema)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("answer_type", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field != "answer_type"]
    return schema


def _locally_type_draft(
    payload: dict[str, Any], *, answer_type: str
) -> GroundedDraft | BackgroundDraft:
    """Add the operation-owned family only after rejecting wire discriminators."""

    if "answer_type" in payload:
        raise ValueError("provider returned a model-owned draft discriminator")
    typed_payload = {"answer_type": answer_type, **payload}
    if answer_type == "grounded":
        return GroundedDraft.model_validate(typed_payload)
    return BackgroundDraft.model_validate(typed_payload)


def _model_identity_matches(requested: str, returned: object) -> bool:
    if not isinstance(returned, str):
        return False
    allowed = _CANONICAL_RESPONSE_MODELS.get(requested, frozenset({requested}))
    return returned in allowed


class OpenRouterProvider:
    def __init__(
        self,
        config: FireLensConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=self.config.request_timeout_seconds)
        self._semaphore = asyncio.Semaphore(config.provider_max_concurrency)

    async def aclose(self) -> None:
        """Close only the client created by this provider."""

        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if self.config.openrouter_api_key is None:
            raise ProviderError(
                ProviderErrorKind.AUTHENTICATION,
                "OpenRouter API key is not configured.",
                status_code=401,
            )
        return {
            "Authorization": (f"Bearer {self.config.openrouter_api_key.get_secret_value()}"),
            "Content-Type": "application/json",
            "HTTP-Referer": "https://firelens.local",
            "X-Title": "FireLens BC",
        }

    def _provider_preferences(self) -> dict[str, Any]:
        preferences: dict[str, Any] = {
            "require_parameters": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
        }
        if self.config.require_zdr:
            preferences["zdr"] = True
        return preferences

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Post with bounded same-model retries for transient failures only."""

        last_error: ProviderError | None = None
        for attempt in range(1, self.config.provider_max_attempts + 1):
            try:
                async with self._semaphore:
                    response = await self._client.post(
                        f"{self.config.openrouter_base_url}/{endpoint.lstrip('/')}",
                        headers=self._headers(),
                        json=payload,
                    )
                try:
                    body = response.json()
                except json.JSONDecodeError as exc:
                    raise ProviderError(
                        ProviderErrorKind.INVALID_RESPONSE,
                        "OpenRouter returned a non-JSON response.",
                        status_code=response.status_code,
                    ) from exc
                if not isinstance(body, dict):
                    raise ProviderError(
                        ProviderErrorKind.INVALID_RESPONSE,
                        "OpenRouter returned an unexpected response shape.",
                        status_code=response.status_code,
                    )
                if response.is_error or body.get("error"):
                    self._raise_provider_error(response.status_code, body)
                return body, attempt
            except httpx.TimeoutException as exc:
                last_error = ProviderError(
                    ProviderErrorKind.TIMEOUT,
                    "OpenRouter request timed out.",
                    status_code=408,
                    retryable=True,
                )
                last_error.__cause__ = exc
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    ProviderErrorKind.UNAVAILABLE,
                    "OpenRouter could not be reached.",
                    retryable=True,
                )
                last_error.__cause__ = exc
            except ProviderError as exc:
                last_error = exc

            if not last_error.retryable or attempt >= self.config.provider_max_attempts:
                raise last_error
            delay = self.config.provider_retry_base_seconds * (2 ** (attempt - 1))
            if delay:
                # Sleeping outside the semaphore lets another local request run.
                await asyncio.sleep(delay)

        raise last_error or ProviderError(
            ProviderErrorKind.UNKNOWN, "OpenRouter request failed."
        )

    @staticmethod
    def _raise_provider_error(status: int, body: dict[str, Any]) -> None:
        error = body.get("error") or {}
        if not isinstance(error, dict):
            error = {}
        raw_code = error.get("code")
        code = raw_code if isinstance(raw_code, int) else status or 500
        kinds = {
            400: ProviderErrorKind.INVALID_REQUEST,
            401: ProviderErrorKind.AUTHENTICATION,
            402: ProviderErrorKind.CREDITS,
            403: ProviderErrorKind.SAFETY,
            404: ProviderErrorKind.MODEL_UNAVAILABLE,
            408: ProviderErrorKind.TIMEOUT,
            429: ProviderErrorKind.RATE_LIMIT,
            524: ProviderErrorKind.TIMEOUT,
            529: ProviderErrorKind.UNAVAILABLE,
            502: ProviderErrorKind.UNAVAILABLE,
            503: ProviderErrorKind.UNAVAILABLE,
        }
        kind = kinds.get(code, ProviderErrorKind.UNKNOWN)
        safe_messages = {
            ProviderErrorKind.AUTHENTICATION: "OpenRouter authentication failed.",
            ProviderErrorKind.CREDITS: "OpenRouter credits are unavailable.",
            ProviderErrorKind.RATE_LIMIT: "OpenRouter rate limit was reached.",
            ProviderErrorKind.TIMEOUT: "OpenRouter request timed out.",
            ProviderErrorKind.UNAVAILABLE: "The required OpenRouter model is unavailable.",
            ProviderErrorKind.MODEL_UNAVAILABLE: "The requested OpenRouter model is unavailable.",
            ProviderErrorKind.INVALID_REQUEST: "OpenRouter rejected the request.",
            ProviderErrorKind.SAFETY: "OpenRouter blocked the request by policy.",
            ProviderErrorKind.UNKNOWN: "OpenRouter returned an unexpected error.",
        }
        raise ProviderError(
            kind,
            safe_messages[kind],
            status_code=code,
            retryable=kind
            in {
                ProviderErrorKind.RATE_LIMIT,
                ProviderErrorKind.TIMEOUT,
                ProviderErrorKind.UNAVAILABLE,
            },
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        body, attempts = await self._post(
            "embeddings",
            {
                "model": self.config.embedding_model,
                "input": list(texts),
                "provider": self._provider_preferences(),
            },
        )
        try:
            if not _model_identity_matches(self.config.embedding_model, body.get("model")):
                raise ValueError("embedding model mismatch")
            rows = sorted(body["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
            if len(vectors) != len(texts):
                raise ValueError("embedding count mismatch")
            return EmbeddingResponse(
                model=body.get("model", self.config.embedding_model),
                vectors=vectors,
                usage=body.get("usage") or {},
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid embeddings.",
            ) from exc

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse:
        body, attempts = await self._post(
            "rerank",
            {
                "model": self.config.rerank_model,
                "query": query,
                "documents": list(documents),
                "top_n": top_n,
                "provider": self._provider_preferences(),
            },
        )
        try:
            if not _model_identity_matches(self.config.rerank_model, body.get("model")):
                raise ValueError("rerank model mismatch")
            results = [
                RerankResult(index=row["index"], relevance_score=row["relevance_score"])
                for row in body["results"]
            ]
            indices = [result.index for result in results]
            if len(indices) != len(set(indices)):
                raise ValueError("duplicate rerank indices")
            if any(index >= len(documents) for index in indices):
                raise ValueError("rerank index out of range")
            if len(results) != min(top_n, len(documents)):
                raise ValueError("rerank result count mismatch")
            return RerankResponse(
                model=body.get("model", self.config.rerank_model),
                results=results,
                usage=body.get("usage") or (body.get("meta") or {}).get("billed_units") or {},
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid rerank results.",
            ) from exc

    async def _chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
        schema_name: str,
        max_tokens: int,
    ) -> tuple[dict[str, Any], str, dict[str, Any], int]:
        body, attempts = await self._post(
            "chat/completions",
            {
                "model": self.config.generation_model,
                "messages": list(messages),
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": self.config.generation_temperature,
                "provider": self._provider_preferences(),
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": output_schema,
                    },
                },
            },
        )
        try:
            if not _model_identity_matches(self.config.generation_model, body.get("model")):
                raise ValueError("generation model mismatch")
            content = body["choices"][0]["message"]["content"]
            payload = json.loads(content) if isinstance(content, str) else content
            if not isinstance(payload, dict):
                raise ValueError("structured response is not an object")
            return (
                payload,
                str(body.get("model", self.config.generation_model)),
                body.get("usage") or {},
                attempts,
            )
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid structured JSON.",
            ) from exc

    async def plan(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse:
        payload, model, usage, attempts = await self._chat_json(
            messages,
            output_schema=output_schema,
            schema_name="firelens_query_plan",
            max_tokens=500,
        )
        try:
            decision = PlanningDecision.model_validate(payload)
        except ValidationError as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned an invalid structured plan.",
            ) from exc
        return PlanningResponse(model=model, decision=decision, usage=usage, attempts=attempts)

    async def generate_contexts(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> DocumentContextResponse:
        payload, model, usage, attempts = await self._chat_json(
            messages,
            output_schema=output_schema,
            schema_name="firelens_document_context",
            max_tokens=1_800,
        )
        try:
            draft = DocumentContextDraft.model_validate(payload)
        except ValidationError as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid document contexts.",
            ) from exc
        return DocumentContextResponse(model=model, draft=draft, usage=usage, attempts=attempts)

    async def generate_grounded(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        payload, model, usage, attempts = await self._chat_json(
            messages,
            output_schema=_wire_draft_schema(output_schema),
            schema_name="firelens_grounded_answer",
            max_tokens=1_200,
        )
        try:
            draft = _locally_type_draft(payload, answer_type="grounded")
        except (ValidationError, ValueError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned an invalid grounded answer.",
            ) from exc
        return GenerationResponse(model=model, draft=draft, usage=usage, attempts=attempts)

    async def generate_background(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        payload, model, usage, attempts = await self._chat_json(
            messages,
            output_schema=_wire_draft_schema(output_schema),
            schema_name="firelens_background_answer",
            max_tokens=500,
        )
        try:
            draft = _locally_type_draft(payload, answer_type="background")
        except (ValidationError, ValueError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned an invalid background answer.",
            ) from exc
        return GenerationResponse(model=model, draft=draft, usage=usage, attempts=attempts)
