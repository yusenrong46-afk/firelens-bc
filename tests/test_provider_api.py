from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr
from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.api import create_app
from firelens.contracts import GroundedDraft, LiveResultKind
from firelens.errors import ProviderError
from firelens.live import LiveDataService
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime


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
                response = await client.post(
                    "/api/v1/ask",
                    content=b"{}",
                    headers={"content-length": "2048", "content-type": "application/json"},
                )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error_kind"], "request_too_large")

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
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(invalid_bbox.status_code, 400)

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
                self.assertEqual(mixed_without_location.json()["response_mode"], "partial")
                self.assertIn(
                    "Current official information", mixed_without_location.json()["answer"]
                )
                self.assertIn("Preparedness guidance", mixed_without_location.json()["answer"])
                self.assertTrue(mixed_without_location.json()["claims"])
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
