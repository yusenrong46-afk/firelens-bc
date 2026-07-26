from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx
from pydantic import SecretStr

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import DraftAnswer
from firelens.errors import ProviderError
from firelens.providers.openrouter import OpenRouterProvider

from rag_helpers import make_runtime, write_test_corpus, make_chunk


class OpenRouterProviderTests(unittest.IsolatedAsyncioTestCase):
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
        def handler(_request: httpx.Request) -> httpx.Response:
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
        self.assertNotIn("secret detail", str(raised.exception))

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
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "not-json"}}]}
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
                with self.assertRaises(ProviderError) as raised:
                    await OpenRouterProvider(config, client=client).generate(
                        [{"role": "user", "content": "answer"}],
                        output_schema=DraftAnswer.model_json_schema(),
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
    async def test_http_contracts_and_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            app = create_app(config, runtime=runtime)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                health = await client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["status"], "ready")
                invalid = await client.post("/ask", json={"question": "   "})
                self.assertEqual(invalid.status_code, 400)
                live = await client.post(
                    "/ask", json={"question": "Is a wildfire active near me right now?"}
                )
                self.assertEqual(live.status_code, 200)
                self.assertEqual(live.json()["status"], "abstention")
                stable = await client.post(
                    "/ask", json={"question": "What belongs in an emergency kit?"}
                )
                self.assertEqual(stable.status_code, 200)
                self.assertEqual(stable.json()["status"], "answer")
                debug = await client.get("/debug/chunks/chunk-a0")
                self.assertEqual(debug.status_code, 200)
