from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx
from pydantic import SecretStr
from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.api import create_app
from firelens.contracts import GroundedDraft
from firelens.errors import ProviderError
from firelens.providers.openrouter import OpenRouterProvider


class OpenRouterProviderTests(unittest.IsolatedAsyncioTestCase):
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
                response = await OpenRouterProvider(config, client=client).embed(["water"])
        self.assertEqual(response.attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], calls[1]["model"])
        self.assertFalse(calls[0]["provider"]["allow_fallbacks"])

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

                first = await client.post(
                    "/api/v1/ask", json={"question": "Hello"}, headers=headers
                )
                second = await client.post(
                    "/api/v1/ask", json={"question": "Hello"}, headers=headers
                )
                denied = await client.post(
                    "/api/v1/ask", json={"question": "Hello"}, headers=headers
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
                self.assertEqual(live.json()["status"], "abstention")
                unsupported_live = await client.post(
                    "/api/v1/ask",
                    json={
                        "question": "What is the current air quality in Vancouver from wildfire smoke?"
                    },
                )
                self.assertEqual(unsupported_live.status_code, 200)
                self.assertEqual(unsupported_live.json()["status"], "abstention")
                self.assertIn("air quality", unsupported_live.json()["answer"])
                localized_without_input = await client.post(
                    "/api/v1/ask",
                    json={"question": "Are there active wildfires near Kelowna today?"},
                )
                self.assertEqual(localized_without_input.status_code, 200)
                self.assertEqual(localized_without_input.json()["status"], "abstention")
                self.assertIn("approximate location", localized_without_input.json()["answer"])
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
