from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import SecretStr
from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.api import create_app
from firelens.contracts import (
    DraftProposalClaim,
    GenerationResponse,
    GroundedDraft,
    LiveResultKind,
    PlanningDecision,
)
from firelens.errors import ProviderError
from firelens.live import LiveDataService
from firelens.providers.fake import FakeProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime


class OpenRouterProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_luna_planning_omits_unsupported_temperature_parameter(self) -> None:
        observed_body: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal observed_body
            observed_body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": "openai/gpt-5.6-luna",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"relation":"grounded_candidate",'
                                    '"retrieval_queries":["wildfire kit"],'
                                    '"explanation":"probe",'
                                    '"required_aspects":[]}'
                                )
                            }
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "generation_model": "openai/gpt-5.6-luna",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await OpenRouterProvider(config, client=client).plan(
                    [{"role": "user", "content": "plan"}],
                    output_schema=PlanningDecision.model_json_schema(),
                )

        self.assertNotIn("temperature", observed_body)
        self.assertTrue(observed_body["provider"]["require_parameters"])
        wire_schema = observed_body["response_format"]["json_schema"]["schema"]
        self.assertEqual(
            set(wire_schema["required"]),
            set(wire_schema["properties"]),
        )

    async def test_zdr_preflight_requires_every_configured_model(self) -> None:
        observed_authorization = ""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal observed_authorization
            observed_authorization = request.headers["authorization"]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "cohere/rerank-4-pro"},
                        {"model_id": "openai/gpt-5.6-luna"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "require_zdr": True,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                models = await OpenRouterProvider(config, client=client).preflight_zdr_models()

        self.assertEqual(
            models,
            (
                "openai/text-embedding-3-small",
                "cohere/rerank-4-pro",
                "openai/gpt-5.6-luna",
            ),
        )
        self.assertEqual(observed_authorization, "Bearer test-key")

    async def test_zdr_preflight_fails_closed_when_a_model_is_ineligible(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "cohere/rerank-4-pro"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "require_zdr": True,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(ProviderError, "no eligible"):
                    await OpenRouterProvider(config, client=client).preflight_zdr_models()

    async def test_transient_rate_limit_retries_same_request(self) -> None:
        calls: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                return httpx.Response(429, json={"error": {"code": 429}})
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                response = await provider.embed(["water"])
        self.assertEqual(response.attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], calls[1]["model"])
        self.assertFalse(calls[0]["provider"]["allow_fallbacks"])
        self.assertEqual(provider.backpressure_limits()["embedding"], 2)

    async def test_rate_limit_honors_retry_after_outside_the_semaphore(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "2"},
                    json={"error": {"code": 429}},
                )
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with patch(
                    "firelens.providers.openrouter.asyncio.sleep", new_callable=AsyncMock
                ) as sleep:
                    response = await OpenRouterProvider(config, client=client).embed(["water"])

        self.assertEqual(response.attempts, 2)
        self.assertEqual(calls, 2)
        sleep.assert_awaited_once_with(2.0)

    async def test_stage_backpressure_reduces_concurrency_and_recovers_additively(
        self,
    ) -> None:
        failing = True
        active = 0
        max_active = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            if failing:
                return httpx.Response(429, json={"error": {"code": 429}})
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_max_attempts": 1,
                    "provider_max_concurrency": 2,
                    "provider_adaptive_min_concurrency": 1,
                    "provider_adaptive_success_window": 2,
                    "provider_circuit_failure_threshold": 10,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])

                self.assertEqual(provider.backpressure_limits()["embedding"], 1)
                self.assertEqual(provider.backpressure_limits()["reranking"], 2)
                self.assertEqual(provider.operational_state(), "degraded")

                failing = False
                responses = await asyncio.gather(
                    provider.embed(["water"]),
                    provider.embed(["water"]),
                )

        self.assertEqual(max_active, 1)
        self.assertEqual([response.vectors for response in responses], [[[1.0, 0.0]]] * 2)
        self.assertEqual(provider.backpressure_limits()["embedding"], 2)
        self.assertEqual(provider.operational_state(), "available")

    async def test_cancellation_releases_adaptive_stage_capacity(self) -> None:
        started = asyncio.Event()
        never = asyncio.Event()

        async def handler(_request: httpx.Request) -> httpx.Response:
            started.set()
            await never.wait()
            raise AssertionError("cancelled provider request unexpectedly resumed")

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_max_attempts": 1,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                task = asyncio.create_task(provider.embed(["water"]))
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        self.assertEqual(provider._stage_pressure["embedding"].active, 0)
        self.assertEqual(
            provider.backpressure_limits()["embedding"],
            config.provider_max_concurrency,
        )

    async def test_retry_after_larger_than_public_budget_fails_without_sleeping(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "60"},
                json={"error": {"code": 429}},
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "public_request_deadline_seconds": 0.1,
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with patch(
                    "firelens.providers.openrouter.asyncio.sleep", new_callable=AsyncMock
                ) as sleep:
                    with self.assertRaises(ProviderError) as raised:
                        await OpenRouterProvider(config, client=client).embed(["water"])

        self.assertEqual(calls, 1)
        self.assertEqual(raised.exception.kind.value, "rate_limit")
        self.assertEqual(raised.exception.retry_after_seconds, 60.0)
        sleep.assert_not_awaited()

    async def test_non_json_rate_limit_still_uses_status_and_retry_after(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "60"},
                text="private upstream response",
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).embed(["water"])

        self.assertEqual(raised.exception.kind.value, "rate_limit")
        self.assertEqual(raised.exception.retry_after_seconds, 60.0)
        self.assertNotIn("private", str(raised.exception))

    async def test_stage_circuit_opens_after_bounded_operation_failures(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, json={"error": {"code": 503}})

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_max_attempts": 1,
                    "provider_retry_base_seconds": 0,
                    "provider_circuit_failure_threshold": 2,
                    "provider_circuit_cooldown_seconds": 60,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                self.assertEqual(provider.operational_state(), "configured_unprobed")
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])
                self.assertEqual(provider.operational_state(), "degraded")
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])
                self.assertEqual(provider.operational_state(), "circuit_open")
                with self.assertRaises(ProviderError) as blocked:
                    await provider.embed(["water"])

        self.assertEqual(calls, 2)
        self.assertEqual(blocked.exception.kind.value, "unavailable")
        self.assertGreater(blocked.exception.retry_after_seconds or 0, 0)

    async def test_circuit_isolated_by_stage_and_half_open_success_recovers(self) -> None:
        embedding_calls = 0
        rerank_calls = 0
        embedding_succeeds = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal embedding_calls, rerank_calls
            if request.url.path.endswith("/rerank"):
                rerank_calls += 1
                return httpx.Response(
                    200,
                    json={
                        "model": "rerank-v4.0-pro",
                        "results": [{"index": 0, "relevance_score": 0.9}],
                    },
                )
            embedding_calls += 1
            if embedding_succeeds:
                return httpx.Response(
                    200,
                    json={
                        "model": "text-embedding-3-small",
                        "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                    },
                )
            return httpx.Response(503, json={"error": {"code": 503}})

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_max_attempts": 1,
                    "provider_retry_base_seconds": 0,
                    "provider_adaptive_min_concurrency": 4,
                    "provider_circuit_failure_threshold": 2,
                    "provider_circuit_cooldown_seconds": 60,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                for _ in range(2):
                    with self.assertRaises(ProviderError):
                        await provider.embed(["water"])
                rerank = await provider.rerank("water", ["document"], top_n=1)
                self.assertEqual(rerank.results[0].index, 0)
                self.assertEqual(provider.operational_state(), "circuit_open")

                embedding_succeeds = True
                provider._circuits["embedding"].open_until_monotonic = monotonic() - 1
                recovered = await provider.embed(["water"])

        self.assertEqual(recovered.vectors, [[1.0, 0.0]])
        self.assertEqual(provider.operational_state(), "available")
        self.assertEqual(embedding_calls, 3)
        self.assertEqual(rerank_calls, 1)

    async def test_invalid_provider_payload_degrades_and_then_opens_stage(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={
                    "model": "substituted/model",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_max_attempts": 1,
                    "provider_circuit_failure_threshold": 2,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])
                self.assertEqual(provider.operational_state(), "degraded")
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])
                self.assertEqual(provider.operational_state(), "circuit_open")
                with self.assertRaises(ProviderError):
                    await provider.embed(["water"])

        self.assertEqual(calls, 2)
        self.assertEqual(
            provider.backpressure_limits()["embedding"],
            config.provider_max_concurrency,
        )

    async def test_timeout_stops_after_three_same_model_attempts(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("simulated timeout", request=request)

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(calls, 3)
        self.assertEqual(raised.exception.kind.value, "timeout")

    async def test_transient_503_retries_then_succeeds(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503, json={"error": {"code": 503}})
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(calls, 3)
        self.assertEqual(response.attempts, 3)

    async def test_embedding_request_and_response_are_bounded(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(response.vectors, [[1.0, 0.0]])
        self.assertEqual(captured["input"], ["water"])
        self.assertEqual(captured["model"], "openai/text-embedding-3-small")

    async def test_credit_error_is_normalized_without_upstream_text(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(402, json={"error": {"message": "secret detail"}})

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(raised.exception.kind.value, "credits")
        self.assertEqual(calls, 1)
        self.assertNotIn("secret detail", str(raised.exception))

    async def test_unavailable_model_is_not_retried(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404, json={"error": {"code": 404}})

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "provider_retry_base_seconds": 0,
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(calls, 1)
        self.assertEqual(raised.exception.kind.value, "model_unavailable")
        self.assertFalse(raised.exception.retryable)

    async def test_rerank_discards_provider_document_metadata(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "rerank-v4.0-pro",
                    "results": [
                        {
                            "index": 0,
                            "relevance_score": 0.99,
                            "document": {"text": "provider-owned echo"},
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await OpenRouterProvider(config, client=client).rerank(
                    "water", ["local corpus text"], top_n=1
                )
        self.assertEqual(response.results[0].index, 0)
        self.assertEqual(response.results[0].relevance_score, 0.99)

    async def test_malformed_generation_response_is_rejected(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).generate_grounded(
                        [{"role": "user", "content": "answer"}],
                        output_schema=GroundedDraft.model_json_schema(),
                    )
        self.assertEqual(raised.exception.kind.value, "invalid_response")

    async def test_grounded_generation_uses_operation_owned_discriminator(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            requested_schema = json.loads(request.content)["response_format"]["json_schema"][
                "schema"
            ]
            self.assertNotIn("answer_type", requested_schema["properties"])
            self.assertNotIn("answer_type", requested_schema["required"])
            return httpx.Response(
                200,
                json={
                    "model": "google/gemini-3.5-flash-lite",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "claims": [
                                            {
                                                "text": "Store water.",
                                                "evidence_quote_ids": ["E1Q1"],
                                            }
                                        ],
                                        "limitations": ["Static guidance only."],
                                        "requires_live_verification": False,
                                    }
                                )
                            }
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "generation_model": "google/gemini-3.5-flash-lite",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await OpenRouterProvider(config, client=client).generate_grounded(
                    [{"role": "user", "content": "answer"}],
                    output_schema=GroundedDraft.model_json_schema(),
                )
        self.assertEqual(response.draft.answer_type, "grounded")

    async def test_grounded_generation_rejects_model_owned_discriminator(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "google/gemini-3.5-flash-lite",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "answer_type": "factual",
                                        "claims": [
                                            {
                                                "text": "Store water.",
                                                "evidence_quote_ids": ["E1Q1"],
                                            }
                                        ],
                                        "limitations": ["Static guidance only."],
                                        "requires_live_verification": False,
                                    }
                                )
                            }
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "generation_model": "google/gemini-3.5-flash-lite",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).generate_grounded(
                        [{"role": "user", "content": "answer"}],
                        output_schema=GroundedDraft.model_json_schema(),
                    )
        self.assertEqual(raised.exception.kind.value, "invalid_response")

    async def test_embedding_model_substitution_is_rejected(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "substituted/model",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            config = config.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-key"),
                    "openrouter_base_url": "https://openrouter.test/api/v1",
                    "embedding_model": "openai/text-embedding-3-small",
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(raised.exception.kind.value, "invalid_response")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_exposes_provider_circuit_without_leaking_details(self) -> None:
        class CircuitOpenProvider(FakeProvider):
            def operational_state(self) -> str:
                return "circuit_open"

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            runtime.provider = CircuitOpenProvider()
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get("/api/v1/health/ready")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["provider_state"], "circuit_open")
        self.assertNotIn("model", health.text.casefold())
        self.assertNotIn("key", health.text.casefold())

    async def test_public_deadline_cancels_every_provider_stage(self) -> None:
        class StageBlockingProvider(FakeProvider):
            def __init__(self, stage: str) -> None:
                super().__init__()
                self.stage = stage
                self.armed = False
                self.cancelled_stage: str | None = None
                self.entered = asyncio.Event()
                self.repair_attempt = 0

            async def block(self, stage: str) -> None:
                if not self.armed or self.stage != stage:
                    return
                self.entered.set()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    self.cancelled_stage = stage
                    raise

            async def plan(self, messages, *, output_schema):
                await self.block("planner")
                return await super().plan(messages, output_schema=output_schema)

            async def embed(self, texts):
                await self.block("embedding")
                return await super().embed(texts)

            async def rerank(self, query, documents, *, top_n):
                await self.block("reranking")
                return await super().rerank(query, documents, top_n=top_n)

            async def generate_grounded(self, messages, *, output_schema):
                if self.stage == "repair" and self.armed:
                    self.repair_attempt += 1
                    if self.repair_attempt == 1:
                        return GenerationResponse(
                            model="fake/invalid-generator",
                            draft=GroundedDraft(
                                answer_type="grounded",
                                claims=[
                                    DraftProposalClaim(
                                        text="Unsupported first attempt.",
                                        evidence_quote_ids=["UNKNOWN"],
                                    )
                                ],
                                limitations=[],
                                requires_live_verification=False,
                            ),
                        )
                    await self.block("repair")
                else:
                    await self.block("generation")
                return await super().generate_grounded(messages, output_schema=output_schema)

        for stage in ("planner", "embedding", "reranking", "generation", "repair"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                provider = StageBlockingProvider(stage)
                runtime, _, config = await make_runtime(Path(directory), provider=provider)
                provider.armed = True
                # Leave enough time for the repair case to emit its deliberately invalid
                # first draft and enter the second provider call. The assertion is about
                # cancellation propagation, not scheduler performance on a 20 ms budget.
                config = config.model_copy(update={"public_request_deadline_seconds": 0.1})
                runtime.config = config
                app = create_app(config, runtime=runtime)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/ask",
                        json={"question": "What belongs in an emergency kit?"},
                    )
                await runtime.aclose()

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error_kind"], "timeout")
                self.assertEqual(provider.cancelled_stage, stage)

    async def test_caller_cancellation_reaches_active_provider_stage(self) -> None:
        class BlockingPlanner(FakeProvider):
            def __init__(self) -> None:
                super().__init__()
                self.armed = False
                self.entered = asyncio.Event()
                self.cancelled = False

            async def plan(self, messages, *, output_schema):
                if not self.armed:
                    return await super().plan(messages, output_schema=output_schema)
                self.entered.set()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

        with tempfile.TemporaryDirectory() as directory:
            provider = BlockingPlanner()
            runtime, _, config = await make_runtime(Path(directory), provider=provider)
            provider.armed = True
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                request = asyncio.create_task(
                    client.post(
                        "/api/v1/ask",
                        json={"question": "What belongs in an emergency kit?"},
                    )
                )
                await asyncio.wait_for(provider.entered.wait(), timeout=1)
                request.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await request
            await runtime.aclose()

        self.assertTrue(provider.cancelled)

    async def test_public_deadline_cancels_slow_live_map_work(self) -> None:
        class SlowLiveService:
            def __init__(self) -> None:
                self.cancelled = False

            async def map_results(self, *args, **kwargs):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"public_request_deadline_seconds": 0.01})
            runtime.config = config
            live_service = SlowLiveService()
            app = create_app(config, runtime=runtime, live_service=live_service)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/live/map?layers=incidents")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_kind"], "timeout")
        self.assertTrue(live_service.cancelled)

    async def test_public_deadline_cancels_slow_nearby_work(self) -> None:
        class SlowNearbyService:
            def __init__(self) -> None:
                self.cancelled = False

            async def nearby_page(self, *args, **kwargs):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"public_request_deadline_seconds": 0.01})
            runtime.config = config
            live_service = SlowNearbyService()
            app = create_app(config, runtime=runtime, live_service=live_service)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/live/nearby",
                    json={"location": {"label": "Vancouver"}},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_kind"], "timeout")
        self.assertTrue(live_service.cancelled)

    async def test_nearby_place_failure_is_typed_and_sanitized(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "geocoder.api.gov.bc.ca")
            return httpx.Response(200, json={"features": []})

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
                live_service = LiveDataService(client=upstream)
                app = create_app(config, runtime=runtime, live_service=live_service)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/live/nearby",
                        json={"location": {"label": "Unknown community"}},
                    )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_kind"], "live_not_found")
        self.assertEqual(response.json()["message"], "the place label could not be resolved")
        self.assertFalse(response.json()["retryable"])

    async def test_public_deadline_cancels_slow_live_work(self) -> None:
        class SlowLiveService:
            def __init__(self) -> None:
                self.cancelled = False

            async def map_results(self, *args, **kwargs):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

            async def nearby_results(self, *args, **kwargs):
                return await self.map_results(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"public_request_deadline_seconds": 0.01})
            runtime.config = config
            live_service = SlowLiveService()
            app = create_app(config, runtime=runtime, live_service=live_service)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ask",
                    json={"question": "What active wildfires are in BC currently?"},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_kind"], "timeout")
        self.assertTrue(live_service.cancelled)

    async def test_declared_oversized_body_is_rejected_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"max_request_body_bytes": 1_024})
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                responses = [
                    await client.post(
                        path,
                        content=b"{}",
                        headers={
                            "content-length": "2048",
                            "content-type": "application/json",
                        },
                    )
                    for path in ("/api/v1/ask", "/api/v1/live/nearby")
                ]

        self.assertTrue(all(response.status_code == 413 for response in responses))
        self.assertTrue(
            all(response.json()["error_kind"] == "request_too_large" for response in responses)
        )

    async def test_chunked_oversized_body_stops_consuming_after_limit(self) -> None:
        yielded = 0

        async def body():
            nonlocal yielded
            yielded += 1
            yield b"x" * 800
            yielded += 1
            yield b"y" * 800
            yielded += 1
            raise AssertionError("middleware consumed beyond the bounded rejection point")

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"max_request_body_bytes": 1_024})
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ask", content=body(), headers={"content-type": "application/json"}
                )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(yielded, 2)

    async def test_misleading_declared_length_cannot_bypass_streaming_cap(self) -> None:
        consumed_bytes = 0

        async def body():
            nonlocal consumed_bytes
            for value in (b"x" * 700, b"y" * 700):
                consumed_bytes += len(value)
                yield value
            raise AssertionError("middleware consumed beyond the rejecting frame")

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"max_request_body_bytes": 1_024})
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ask",
                    content=body(),
                    headers={
                        "content-length": "100",
                        "content-type": "application/json",
                    },
                )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(consumed_bytes, 1_400)

    async def test_concurrent_oversized_bodies_are_independently_bounded(self) -> None:
        request_count = 8
        consumed_frames = [0] * request_count
        consumed_bytes = [0] * request_count

        async def body(index: int):
            for value in (b"x" * 700, b"y" * 700):
                consumed_frames[index] += 1
                consumed_bytes[index] += len(value)
                yield value
                await asyncio.sleep(0)
            raise AssertionError("middleware consumed beyond the rejecting frame")

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(
                update={
                    "anonymous_rate_limit": request_count,
                    "max_request_body_bytes": 1_024,
                }
            )
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                responses = await asyncio.gather(
                    *(
                        client.post(
                            "/api/v1/ask",
                            content=body(index),
                            headers={"content-type": "application/json"},
                        )
                        for index in range(request_count)
                    )
                )

        self.assertEqual(
            [response.status_code for response in responses], [413] * request_count
        )
        self.assertEqual(consumed_frames, [2] * request_count)
        self.assertEqual(consumed_bytes, [1_400] * request_count)

    async def test_not_ready_uses_503_while_liveness_remains_200(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = write_test_corpus(Path(directory), [make_chunk("a", "water")])
            runtime = Runtime(config=config, problems=["provider unavailable"])
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                alive = await client.get("/api/v1/health/live")
                ready = await client.get("/api/v1/health/ready")

        self.assertEqual(alive.status_code, 200)
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["status"], "not_ready")

    async def test_live_chat_and_map_share_records_and_reject_invalid_queries(self) -> None:
        updated = int(datetime(2026, 7, 28, tzinfo=UTC).timestamp() * 1000)

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/query"):
                return httpx.Response(
                    200,
                    json={
                        "name": "BCWS_ActiveFires_Points",
                        "editingInfo": {"dataLastEditDate": updated},
                        "fields": [
                            {"name": name}
                            for name in (
                                "OBJECTID",
                                "FIRE_STATUS",
                                "FIRE_NUMBER",
                                "INCIDENT_NAME",
                            )
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "OBJECTID": 17,
                                "FIRE_STATUS": "Being Held",
                                "FIRE_NUMBER": "K12345",
                                "INCIDENT_NAME": "Contract Fire",
                            },
                            "geometry": {"type": "Point", "coordinates": [-123.5, 49.5]},
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
                live_service = LiveDataService(client=upstream)
                app = create_app(config, runtime=runtime, live_service=live_service)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    chat = await client.post(
                        "/api/v1/ask",
                        json={"question": "Are there active wildfires in BC currently?"},
                    )
                    map_response = await client.get(
                        "/api/v1/live/map", params={"layers": "incidents"}
                    )
                    unknown = await client.get(
                        "/api/v1/live/map", params={"layers": "incidents,unknown"}
                    )
                    invalid_bbox = await client.get(
                        "/api/v1/live/map", params={"bbox": "-181,49,-120,60"}
                    )
                    nearby = await client.post(
                        "/api/v1/live/nearby",
                        json={
                            "location": {
                                "latitude": 49.5,
                                "longitude": -123.5,
                                "radius_km": 25,
                            },
                            "layers": ["incident"],
                            "page": 1,
                            "page_size": 1,
                        },
                    )
                    duplicate_layers = await client.post(
                        "/api/v1/live/nearby",
                        json={
                            "location": {"label": "Vancouver"},
                            "layers": ["incident", "incident"],
                        },
                    )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["response_mode"], "live")
        self.assertEqual(map_response.status_code, 200)
        chat_records = {
            (row["result_id"], row["status"]) for row in chat.json()["live_results"]
        }
        map_records = {
            (row["result_id"], row["status"]) for row in map_response.json()["results"]
        }
        self.assertEqual(chat_records, map_records)
        self.assertEqual(chat_records, {("incident:17", "Being Held")})
        for row in map_response.json()["results"]:
            self.assertEqual(row["kind"], LiveResultKind.INCIDENT.value)
            self.assertTrue(row["authority"])
            self.assertTrue(row["source_url"])
            self.assertTrue(row["source_updated_at"])
            self.assertTrue(row["retrieved_at"])
        map_layer_status = map_response.json()["layer_statuses"][0]
        self.assertEqual(map_layer_status["kind"], "incident")
        self.assertTrue(map_layer_status["available"])
        self.assertEqual(map_layer_status["matching_result_count"], 1)
        self.assertTrue(map_layer_status["source_updated_at"])
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(invalid_bbox.status_code, 400)
        self.assertEqual(nearby.status_code, 200)
        nearby_payload = nearby.json()
        self.assertEqual(nearby_payload["requested_radius_km"], 25)
        self.assertEqual(nearby_payload["requested_layers"], ["incident"])
        self.assertEqual(
            nearby_payload["resolved_location"], {"latitude": 49.5, "longitude": -123.5}
        )
        self.assertEqual(nearby_payload["pagination"]["total_results"], 1)
        self.assertEqual(nearby_payload["pagination"]["returned_results"], 1)
        self.assertEqual(nearby_payload["results"][0]["result_id"], "incident:17")
        self.assertEqual(
            nearby_payload["layer_statuses"][0]["matching_result_count"],
            nearby_payload["pagination"]["total_results"],
        )
        self.assertTrue(nearby_payload["layer_statuses"][0]["available"])
        self.assertTrue(nearby_payload["official_fallback_urls"])
        self.assertEqual(duplicate_layers.status_code, 400)

    async def test_public_request_bounds_and_build_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(
                update={
                    "anonymous_rate_limit": 2,
                    "anonymous_rate_window_seconds": 60,
                    "max_request_body_bytes": 1_024,
                    "release_version": "1.5.0-test",
                    "build_commit": "abc123",
                }
            )
            runtime.config = config
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            headers = {"x-forwarded-for": "203.0.113.10"}
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get("/api/v1/health/ready")
                self.assertEqual(health.json()["release_version"], "1.5.0-test")
                self.assertEqual(health.json()["build_commit"], "abc123")
                self.assertEqual(health.json()["rate_limit_scope"], "instance_local")
                self.assertEqual(health.json()["provider_state"], "configured_unprobed")

                first = await client.post(
                    "/api/v1/ask", json={"question": "Hello"}, headers=headers
                )
                second = await client.post(
                    "/api/v1/ask", json={"question": "Hello"}, headers=headers
                )
                denied = await client.post(
                    "/api/v1/live/nearby",
                    json={"location": {"label": "Vancouver"}},
                    headers=headers,
                )
                self.assertEqual(first.headers["x-ratelimit-scope"], "instance-local")
                self.assertEqual(second.headers["x-ratelimit-remaining"], "0")
                self.assertEqual(denied.status_code, 429)
                self.assertEqual(denied.json()["error_kind"], "rate_limit")
                self.assertIn("retry-after", denied.headers)

                oversized = await client.post(
                    "/api/v1/ask",
                    json={"question": "x" * 2_000},
                    headers={"x-forwarded-for": "203.0.113.11"},
                )
                self.assertEqual(oversized.status_code, 413)
                self.assertEqual(oversized.json()["error_kind"], "request_too_large")

    async def test_http_contracts_and_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                alive = await client.get("/api/v1/health/live")
                self.assertEqual(alive.status_code, 200)
                self.assertEqual(alive.json()["status"], "alive")
                health = await client.get("/api/v1/health/ready")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["status"], "ready")
                invalid = await client.post("/api/v1/ask", json={"question": "   "})
                self.assertEqual(invalid.status_code, 400)
                self.assertIn("trace_id", invalid.json())
                live = await client.post(
                    "/api/v1/ask",
                    json={"question": "Is a wildfire active near me right now?"},
                )
                self.assertEqual(live.status_code, 200)
                self.assertEqual(live.json()["status"], "answer")
                self.assertEqual(live.json()["response_mode"], "requires_input")
                unsupported_live = await client.post(
                    "/api/v1/ask",
                    json={
                        "question": "What is the current air quality in Vancouver from wildfire smoke?"
                    },
                )
                self.assertEqual(unsupported_live.status_code, 200)
                self.assertEqual(unsupported_live.json()["status"], "answer")
                self.assertEqual(unsupported_live.json()["response_mode"], "scope_redirect")
                self.assertIn("air quality", unsupported_live.json()["answer"])
                self.assertTrue(unsupported_live.json()["related_links"])
                localized_without_input = await client.post(
                    "/api/v1/ask",
                    json={"question": "Are there active wildfires near Kelowna today?"},
                )
                self.assertEqual(localized_without_input.status_code, 200)
                self.assertEqual(localized_without_input.json()["status"], "answer")
                self.assertEqual(localized_without_input.json()["response_mode"], "live")
                self.assertIsNotNone(localized_without_input.json()["resolved_location"])
                self.assertIsNone(localized_without_input.json()["required_input"])
                mixed_without_location = await client.post(
                    "/api/v1/ask",
                    json={
                        "question": (
                            "Are there fires near Kelowna today, and what belongs in an "
                            "emergency kit?"
                        )
                    },
                )
                self.assertEqual(mixed_without_location.status_code, 200)
                self.assertEqual(mixed_without_location.json()["response_mode"], "mixed")
                self.assertIsNotNone(mixed_without_location.json()["resolved_location"])
                self.assertIsNone(mixed_without_location.json()["required_input"])
                unsupported_mixed = await client.post(
                    "/api/v1/ask",
                    json={
                        "question": (
                            "Are roads closed to Vernon and what belongs in an emergency kit?"
                        )
                    },
                )
                self.assertEqual(unsupported_mixed.status_code, 200)
                self.assertEqual(unsupported_mixed.json()["response_mode"], "partial")
                self.assertTrue(
                    any(
                        "road conditions" in limitation
                        for limitation in unsupported_mixed.json()["limitations"]
                    )
                )
                stable = await client.post(
                    "/api/v1/ask",
                    json={"question": "What belongs in an emergency kit?"},
                )
                self.assertEqual(stable.status_code, 200)
                self.assertEqual(stable.json()["status"], "answer")
                self.assertTrue(stable.json()["claims"][0]["supports"])
                self.assertTrue(stable.json()["evidence"])
                debug = await client.get("/api/v1/debug/chunks/chunk-a0")
                self.assertEqual(debug.status_code, 200)
