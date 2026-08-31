"""OpenRouter HTTP adapter. No FireLens policy decisions belong here."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from time import monotonic
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from firelens.agent.chat import ChatTurn
from firelens.config import FireLensConfig
from firelens.contracts import (
    DocumentContextResponse,
    EmbeddingResponse,
    GenerationResponse,
    PlanningResponse,
    RerankResponse,
    RerankResult,
)
from firelens.errors import ProviderError, ProviderErrorKind
from firelens.privacy_policy import ZdrPreflightReport
from firelens.providers import (
    openrouter_generation,
    openrouter_operations,
    openrouter_productbench,
    openrouter_zdr,
)
from firelens.providers.openrouter_support import (
    CHAT_STAGES,
    PROVIDER_STAGES,
    CircuitState,
    ProviderStage,
    StagePressureState,
    model_identity_matches,
    parse_chat_turn,
)
from firelens.providers.openrouter_support import (
    retry_after_seconds as parse_retry_after_seconds,
)


class OpenRouterProvider:
    def __init__(
        self,
        config: FireLensConfig,
        *,
        client: httpx.AsyncClient | None = None,
        capture_productbench_receipts: bool = False,
    ) -> None:
        if config.provider_adaptive_min_concurrency > config.provider_max_concurrency:
            raise ValueError("provider adaptive minimum cannot exceed maximum concurrency")
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=self.config.request_timeout_seconds)
        self._semaphore = asyncio.Semaphore(config.provider_max_concurrency)
        self._circuit_lock = asyncio.Lock()
        self._circuits = {stage: CircuitState() for stage in PROVIDER_STAGES}
        self._stage_pressure = {
            stage: StagePressureState(limit=config.provider_max_concurrency)
            for stage in PROVIDER_STAGES
        }
        self._productbench_receipts: list[dict[str, object]] | None = (
            [] if capture_productbench_receipts else None
        )

    async def aclose(self) -> None:
        """Close only the client created by this provider."""

        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _headers_for_config(config: FireLensConfig) -> dict[str, str]:
        if config.openrouter_api_key is None:
            raise ProviderError(
                ProviderErrorKind.AUTHENTICATION,
                "OpenRouter API key is not configured.",
                status_code=401,
            )
        return {
            "Authorization": (f"Bearer {config.openrouter_api_key.get_secret_value()}"),
            "Content-Type": "application/json",
            "HTTP-Referer": "https://firelens.local",
            "X-Title": "FireLens BC",
        }

    def _headers(self) -> dict[str, str]:
        return self._headers_for_config(self.config)

    @classmethod
    async def require_productbench_key_cap(
        cls,
        config: FireLensConfig,
        *,
        max_cost_usd: float,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, object]:
        owns_client = client is None
        current_client = client or httpx.AsyncClient(timeout=config.request_timeout_seconds)
        try:
            return await openrouter_productbench.require_productbench_key_cap(
                client=current_client,
                base_url=config.openrouter_base_url,
                headers=cls._headers_for_config(config),
                max_cost_usd=max_cost_usd,
            )
        finally:
            if owns_client:
                await current_client.aclose()

    def productbench_receipts(self) -> list[dict[str, object]] | None:
        receipts = self._productbench_receipts
        return None if receipts is None else [dict(receipt) for receipt in receipts]

    def _generation_model_id(self) -> str:
        return openrouter_generation.model_id(self.config)

    def _provider_preferences(self, stage: ProviderStage) -> dict[str, Any]:
        """Return stage privacy prefs, omitting Luna chat `require_parameters`.

        OpenRouter ZDR chat endpoints for `openai/gpt-5.6-luna` return HTTP 404
        "no endpoints matching your data policy" when `provider.zdr=true` is
        combined with `require_parameters=true`. Embedding still sends it.
        `data_collection=deny` and generation ZDR stay required.
        """

        preferences = dict(self.config.privacy.provider_preferences(stage))
        if stage in CHAT_STAGES and self._generation_model_id() == "openai/gpt-5.6-luna":
            preferences.pop("require_parameters", None)
        return preferences

    def _generation_sampling_parameters(self) -> dict[str, float]:
        return openrouter_generation.sampling_parameters(self.config)

    def _generation_output_schema(self, output_schema: dict[str, Any]) -> dict[str, Any]:
        return openrouter_generation.output_schema(self.config, output_schema)

    async def preflight_zdr_models(self) -> tuple[str, ...]:
        """Fail closed unless every ZDR-required model has an eligible endpoint."""

        return await openrouter_zdr.required_models(
            config=self.config, client=self._client, headers=self._headers()
        )

    async def preflight_zdr(self) -> ZdrPreflightReport:
        return await openrouter_zdr.preflight(
            config=self.config, client=self._client, headers=self._headers()
        )

    def operational_state(
        self,
    ) -> Literal["configured_unprobed", "available", "degraded", "circuit_open"]:
        now = monotonic()
        states = tuple(self._circuits.values())
        if any(state.open_until_monotonic > now for state in states):
            return "circuit_open"
        if any(
            state.consecutive_failures or state.open_until_monotonic or state.probe_in_flight
            for state in states
        ):
            return "degraded"
        if any(
            state.limit < self.config.provider_max_concurrency
            for state in self._stage_pressure.values()
        ):
            return "degraded"
        if any(state.observed_success for state in states):
            return "available"
        return "configured_unprobed"

    async def _admit_stage(self, stage: ProviderStage) -> None:
        async with self._circuit_lock:
            state = self._circuits[stage]
            now = monotonic()
            if state.open_until_monotonic > now:
                raise ProviderError(
                    ProviderErrorKind.UNAVAILABLE,
                    "The required OpenRouter stage is temporarily unavailable.",
                    status_code=503,
                    retryable=True,
                    retry_after_seconds=state.open_until_monotonic - now,
                )
            if state.open_until_monotonic:
                if state.probe_in_flight:
                    raise ProviderError(
                        ProviderErrorKind.UNAVAILABLE,
                        "The required OpenRouter stage is temporarily unavailable.",
                        status_code=503,
                        retryable=True,
                        retry_after_seconds=self.config.provider_circuit_cooldown_seconds,
                    )
                state.probe_in_flight = True

    async def _record_stage_success(self, stage: ProviderStage) -> None:
        async with self._circuit_lock:
            state = self._circuits[stage]
            state.consecutive_failures = 0
            state.open_until_monotonic = 0.0
            state.probe_in_flight = False
            state.observed_success = True
        pressure = self._stage_pressure[stage]
        async with pressure.condition:
            if pressure.limit >= self.config.provider_max_concurrency:
                pressure.consecutive_successes = 0
                return
            pressure.consecutive_successes += 1
            if (
                pressure.consecutive_successes >= self.config.provider_adaptive_success_window
                and pressure.limit < self.config.provider_max_concurrency
            ):
                pressure.limit += 1
                pressure.consecutive_successes = 0
                pressure.condition.notify_all()

    async def _record_stage_pressure_failure(
        self,
        stage: ProviderStage,
        error: ProviderError,
    ) -> None:
        pressure = self._stage_pressure[stage]
        async with pressure.condition:
            current = pressure.limit
            if error.kind == ProviderErrorKind.RATE_LIMIT:
                pressure.limit = max(
                    self.config.provider_adaptive_min_concurrency,
                    current // 2,
                )
            elif error.kind in {
                ProviderErrorKind.TIMEOUT,
                ProviderErrorKind.UNAVAILABLE,
            }:
                pressure.limit = max(
                    self.config.provider_adaptive_min_concurrency,
                    current - 1,
                )
            else:
                return
            pressure.consecutive_successes = 0

    async def _acquire_stage_capacity(self, stage: ProviderStage) -> None:
        pressure = self._stage_pressure[stage]
        async with pressure.condition:
            await pressure.condition.wait_for(lambda: pressure.active < pressure.limit)
            pressure.active += 1

    async def _release_stage_capacity(self, stage: ProviderStage) -> None:
        pressure = self._stage_pressure[stage]
        async with pressure.condition:
            pressure.active -= 1
            if pressure.active < 0:  # defensive invariant; never hide accounting drift
                pressure.active = 0
                raise RuntimeError("provider stage capacity accounting underflow")
            pressure.condition.notify_all()

    def backpressure_limits(self) -> dict[str, int]:
        return {stage: state.limit for stage, state in self._stage_pressure.items()}

    async def _record_stage_failure(
        self,
        stage: ProviderStage,
        error: ProviderError,
    ) -> None:
        async with self._circuit_lock:
            state = self._circuits[stage]
            counts_toward_circuit = (
                error.retryable or error.kind == ProviderErrorKind.INVALID_RESPONSE
            )
            if not counts_toward_circuit:
                if state.probe_in_flight:
                    state.consecutive_failures = 0
                    state.open_until_monotonic = 0.0
                    state.probe_in_flight = False
                return
            was_half_open = state.probe_in_flight or bool(state.open_until_monotonic)
            state.probe_in_flight = False
            state.consecutive_failures += 1
            if (
                was_half_open
                or state.consecutive_failures >= self.config.provider_circuit_failure_threshold
            ):
                cooldown = max(
                    self.config.provider_circuit_cooldown_seconds,
                    error.retry_after_seconds or 0.0,
                )
                state.open_until_monotonic = monotonic() + cooldown

    async def _abandon_stage_probe(self, stage: ProviderStage) -> None:
        async with self._circuit_lock:
            self._circuits[stage].probe_in_flight = False

    async def _post(
        self,
        stage: ProviderStage,
        endpoint: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        await self._admit_stage(stage)
        try:
            result = await self._post_with_retries(stage, endpoint, payload)
        except asyncio.CancelledError:
            await self._abandon_stage_probe(stage)
            raise
        except ProviderError as exc:
            await self._record_stage_failure(stage, exc)
            raise
        return result

    async def _post_attempt(
        self,
        stage: ProviderStage,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self._acquire_stage_capacity(stage)
        try:
            try:
                async with self._semaphore:
                    response = await self._client.post(
                        f"{self.config.openrouter_base_url}/{endpoint.lstrip('/')}",
                        headers=self._headers(),
                        json=payload,
                    )
                retry_after_seconds = parse_retry_after_seconds(
                    response.headers.get("Retry-After")
                )
                try:
                    body = response.json()
                except json.JSONDecodeError as exc:
                    if response.is_error:
                        self._raise_provider_error(
                            response.status_code,
                            {},
                            retry_after_seconds=retry_after_seconds,
                        )
                    raise ProviderError(
                        ProviderErrorKind.INVALID_RESPONSE,
                        "OpenRouter returned a non-JSON response.",
                        status_code=response.status_code,
                    ) from exc
                if not isinstance(body, dict):
                    if response.is_error:
                        self._raise_provider_error(
                            response.status_code,
                            {},
                            retry_after_seconds=retry_after_seconds,
                        )
                    raise ProviderError(
                        ProviderErrorKind.INVALID_RESPONSE,
                        "OpenRouter returned an unexpected response shape.",
                        status_code=response.status_code,
                    )
                if response.is_error or body.get("error"):
                    self._raise_provider_error(
                        response.status_code,
                        body,
                        retry_after_seconds=retry_after_seconds,
                    )
                return body
            except httpx.TimeoutException as exc:
                error = ProviderError(
                    ProviderErrorKind.TIMEOUT,
                    "OpenRouter request timed out.",
                    status_code=408,
                    retryable=True,
                )
                error.__cause__ = exc
                await self._record_stage_pressure_failure(stage, error)
                raise error from exc
            except httpx.HTTPError as exc:
                error = ProviderError(
                    ProviderErrorKind.UNAVAILABLE,
                    "OpenRouter could not be reached.",
                    retryable=True,
                )
                error.__cause__ = exc
                await self._record_stage_pressure_failure(stage, error)
                raise error from exc
            except ProviderError as error:
                await self._record_stage_pressure_failure(stage, error)
                raise
        finally:
            await self._release_stage_capacity(stage)

    async def _post_with_retries(
        self,
        stage: ProviderStage,
        endpoint: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """Post with bounded same-model retries for transient failures only."""

        last_error: ProviderError | None = None
        started = monotonic()
        for attempt in range(1, self.config.provider_max_attempts + 1):
            try:
                body = await self._post_attempt(stage, endpoint, payload)
                if self._productbench_receipts is not None:
                    self._productbench_receipts.append(
                        openrouter_productbench.receipt(
                            stage=stage,
                            endpoint=endpoint,
                            body=body,
                            attempts=attempt,
                        )
                    )
                return body, attempt
            except ProviderError as exc:
                last_error = exc

            if not last_error.retryable or attempt >= self.config.provider_max_attempts:
                raise last_error
            delay = max(
                self.config.provider_retry_base_seconds * (2 ** (attempt - 1)),
                last_error.retry_after_seconds or 0.0,
            )
            remaining = self.config.public_request_deadline_seconds - (monotonic() - started)
            if delay >= remaining:
                # The server-requested delay cannot fit inside the public request budget.
                # Fail immediately and let the caller return the typed provider outcome.
                raise last_error
            if delay:
                # Sleeping outside the semaphore lets another local request run.
                await asyncio.sleep(delay)

        raise last_error or ProviderError(
            ProviderErrorKind.UNKNOWN, "OpenRouter request failed."
        )

    @staticmethod
    def _raise_provider_error(
        status: int,
        body: dict[str, Any],
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
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
            retry_after_seconds=retry_after_seconds,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        body, attempts = await self._post(
            "embedding",
            "embeddings",
            {
                "model": self.config.embedding_model,
                "input": list(texts),
                "provider": self._provider_preferences("embedding"),
            },
        )
        try:
            if not model_identity_matches(self.config.embedding_model, body.get("model")):
                raise ValueError("embedding model mismatch")
            rows = sorted(body["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
            if len(vectors) != len(texts):
                raise ValueError("embedding count mismatch")
            response = EmbeddingResponse(
                model=body.get("model", self.config.embedding_model),
                vectors=vectors,
                usage=body.get("usage") or {},
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            error = ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid embeddings.",
            )
            await self._record_stage_failure("embedding", error)
            raise error from exc
        await self._record_stage_success("embedding")
        return response

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse:
        body, attempts = await self._post(
            "reranking",
            "rerank",
            {
                "model": self.config.rerank_model,
                "query": query,
                "documents": list(documents),
                "top_n": top_n,
                "provider": self._provider_preferences("reranking"),
            },
        )
        try:
            if not model_identity_matches(self.config.rerank_model, body.get("model")):
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
            response = RerankResponse(
                model=body.get("model", self.config.rerank_model),
                results=results,
                usage=body.get("usage") or (body.get("meta") or {}).get("billed_units") or {},
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            error = ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned invalid rerank results.",
            )
            await self._record_stage_failure("reranking", error)
            raise error from exc
        await self._record_stage_success("reranking")
        return response

    async def _chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
        schema_name: str,
        max_tokens: int,
        stage: ProviderStage,
    ) -> tuple[dict[str, Any], str, dict[str, Any], int]:
        return await openrouter_operations.chat_json(
            self,
            messages,
            output_schema=output_schema,
            schema_name=schema_name,
            max_tokens=max_tokens,
            stage=stage,
        )

    async def plan(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse:
        return await openrouter_operations.plan(self, messages, output_schema=output_schema)

    async def generate_contexts(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> DocumentContextResponse:
        return await openrouter_operations.generate_contexts(
            self, messages, output_schema=output_schema
        )

    async def generate_grounded(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        return await openrouter_operations.generate_grounded(
            self, messages, output_schema=output_schema
        )

    async def generate_background(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        return await openrouter_operations.generate_background(
            self, messages, output_schema=output_schema
        )

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        """One OpenRouter chat turn for the Luna tool loop."""

        payload: dict[str, Any] = {
            "model": self.config.generation_model,
            "messages": list(messages),
            "stream": False,
            "max_tokens": 1_200,
            **self._generation_sampling_parameters(),
            "provider": self._provider_preferences("grounded_generation"),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        body, _attempts = await self._post("grounded_generation", "chat/completions", payload)
        try:
            turn = parse_chat_turn(body, self.config.generation_model)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            error = ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "OpenRouter returned an invalid chat turn.",
            )
            await self._record_stage_failure("grounded_generation", error)
            raise error from exc
        await self._record_stage_success("grounded_generation")
        return turn
