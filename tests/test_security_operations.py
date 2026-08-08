from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from rag_helpers import make_runtime

from firelens.api import ERROR_RESPONSES, create_app
from firelens.config import FireLensConfig
from firelens.operational_logging import LOGGER_NAME
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime


class SecurityAndOperationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_lifespan_requires_successful_zdr_preflight(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "cohere/rerank-4-pro"},
                        {"model_id": "google/gemini-3.5-flash-lite"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = FireLensConfig.from_env(Path(directory)).model_copy(
                update={
                    "deployment_environment": "production",
                    "require_zdr": True,
                    "openrouter_api_key": SecretStr("test-key"),
                }
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                runtime = Runtime(
                    config=config,
                    provider_configured=True,
                    provider=provider,
                )
                app = create_app(config, runtime=runtime)
                async with app.router.lifespan_context(app):
                    self.assertEqual(runtime.zdr_policy_state, "eligible")

    async def test_feedback_is_categorical_content_free_and_rate_limited(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger(LOGGER_NAME)
        previous_level = logger.level
        previous_propagate = logger.propagate
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        try:
            with tempfile.TemporaryDirectory() as directory:
                runtime, _, config = await make_runtime(Path(directory))
                app = create_app(config, runtime=runtime)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/feedback",
                        json={
                            "trace_id": "a" * 32,
                            "category": "incorrect_or_unsupported",
                        },
                    )
                    invalid = await client.post(
                        "/api/v1/feedback",
                        json={"trace_id": "not-a-trace", "category": "helpful"},
                    )
                    extra = await client.post(
                        "/api/v1/feedback",
                        json={
                            "trace_id": "b" * 32,
                            "category": "helpful",
                            "comment": "PRIVATE-FEEDBACK-CONTENT",
                        },
                    )
                await runtime.aclose()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": True})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(extra.status_code, 422)
        serialized = stream.getvalue()
        self.assertNotIn("PRIVATE-FEEDBACK-CONTENT", serialized)
        event = json.loads(serialized.strip())
        self.assertEqual(
            set(event),
            {
                "schema_version",
                "event",
                "trace_id",
                "category",
                "release_version",
                "build_commit",
                "deployment_environment",
            },
        )

    async def test_security_headers_and_production_debug_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(update={"debug": False})
            runtime.config = config
            app = create_app(config, runtime=runtime)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                health = await client.get("/api/v1/health/live")
                debug_chunk = await client.get("/api/v1/debug/chunks/chunk-a0")
                debug_search = await client.post(
                    "/api/v1/search", json={"question": "emergency kit"}
                )
            await runtime.aclose()

        self.assertEqual(health.status_code, 200)
        content_policy = health.headers["content-security-policy"]
        self.assertIn("default-src 'self'", content_policy)
        self.assertIn("style-src 'self'", content_policy)
        self.assertNotIn("'unsafe-inline'", content_policy)
        self.assertNotIn("tile.openstreetmap.org", content_policy)
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertEqual(health.headers["x-frame-options"], "DENY")
        self.assertEqual(health.headers["referrer-policy"], "no-referrer")
        self.assertEqual(debug_chunk.status_code, 404)
        self.assertEqual(debug_search.status_code, 404)

    async def test_html_shell_is_not_cached_across_deployments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            frontend = Path(directory) / "frontend"
            frontend.mkdir()
            (frontend / "index.html").write_text(
                (
                    "<!doctype html><script type='module' "
                    "src='/assets/index-CURRENT.js'></script>"
                    "<link rel='stylesheet' href='/assets/index-CURRENT.css'>"
                    "<div id='root'></div>"
                ),
                encoding="utf-8",
            )
            assets = frontend / "assets"
            assets.mkdir()
            (assets / "index-CURRENT.js").write_text(
                "document.querySelector('#root').textContent = 'Current';",
                encoding="utf-8",
            )
            (assets / "index-CURRENT.css").write_text(
                "#root { display: block; }",
                encoding="utf-8",
            )
            (frontend / "app.js").write_text(
                "document.querySelector('#root').textContent = 'FireLens';",
                encoding="utf-8",
            )
            config = config.model_copy(update={"frontend_dist_path": frontend})
            runtime.config = config
            app = create_app(config, runtime=runtime)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                homepage = await client.get("/")
                fingerprinted_asset = await client.get("/app.js")
                stale_entry = await client.get("/assets/index-STALE.js")
                stale_styles = await client.get("/assets/index-STALE.css")
            await runtime.aclose()

        self.assertEqual(homepage.status_code, 200)
        self.assertEqual(
            homepage.headers["cache-control"],
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        self.assertEqual(homepage.headers["pragma"], "no-cache")
        self.assertEqual(homepage.headers["expires"], "0")
        self.assertNotIn(
            "no-store",
            fingerprinted_asset.headers.get("cache-control", ""),
        )
        self.assertEqual(stale_entry.status_code, 200)
        self.assertIn("textContent = 'Current'", stale_entry.text)
        self.assertEqual(stale_entry.headers["cache-control"], "no-store")
        self.assertEqual(stale_styles.status_code, 200)
        self.assertIn("display: block", stale_styles.text)
        self.assertEqual(stale_styles.headers["cache-control"], "no-store")

    async def test_debug_routes_stay_disabled_in_production_when_flag_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            config = config.model_copy(
                update={"debug": True, "deployment_environment": "production"}
            )
            runtime.config = config
            app = create_app(config, runtime=runtime)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                debug_chunk = await client.get("/api/v1/debug/chunks/chunk-a0")
                debug_search = await client.post(
                    "/api/v1/search", json={"question": "emergency kit"}
                )
            await runtime.aclose()

        self.assertEqual(debug_chunk.status_code, 404)
        self.assertEqual(debug_search.status_code, 404)

    async def test_operational_log_excludes_question_location_and_evidence(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger(LOGGER_NAME)
        previous_level = logger.level
        previous_propagate = logger.propagate
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        try:
            with tempfile.TemporaryDirectory() as directory:
                runtime, _, config = await make_runtime(Path(directory))
                app = create_app(config, runtime=runtime)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/ask",
                        json={
                            "question": "Am I safe at PRIVATE-HOME-MARKER?",
                            "location": {
                                "latitude": 49.123456,
                                "longitude": -119.654321,
                                "radius_km": 50,
                            },
                        },
                    )
                await runtime.aclose()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate

        self.assertEqual(response.status_code, 200)
        serialized = stream.getvalue()
        self.assertNotIn("PRIVATE-HOME-MARKER", serialized)
        self.assertNotIn("49.123456", serialized)
        self.assertNotIn("-119.654321", serialized)
        event = json.loads(serialized.strip().splitlines()[-1])
        self.assertEqual(
            set(event),
            {
                "schema_version",
                "event",
                "trace_id",
                "route",
                "response_mode",
                "status",
                "latency_ms",
                "provider_stages",
                "provider_models",
                "error_category",
                "evidence_count",
                "claim_count",
                "live_result_count",
                "validation_disposition",
                "corpus_version",
                "release_version",
                "build_commit",
                "deployment_environment",
            },
        )
        self.assertEqual(event["schema_version"], "firelens.operational_event.v2")
        self.assertEqual(event["corpus_version"], "test-corpus.v1")
        self.assertEqual(event["deployment_environment"], "local")
        self.assertGreaterEqual(event["evidence_count"], 0)


class ProductionImportBoundaryTests(unittest.TestCase):
    def test_production_config_requires_zdr_and_content_free_traces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = FireLensConfig.from_env(Path(directory))
            payload = local.model_dump()
            payload["deployment_environment"] = "production"
            with pytest.raises(ValidationError, match="zero-data-retention"):
                FireLensConfig.model_validate(payload)
            payload["require_zdr"] = True
            payload["trace_content"] = True
            with pytest.raises(ValidationError, match="cannot persist"):
                FireLensConfig.model_validate(payload)

    def test_openapi_413_description_is_explicit_and_stable(self) -> None:
        self.assertEqual(ERROR_RESPONSES[413]["description"], "Content Too Large")

    def test_required_zdr_is_not_ready_before_endpoint_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = FireLensConfig.from_env(Path(directory)).model_copy(
                update={
                    "deployment_environment": "production",
                    "require_zdr": True,
                }
            )
            runtime = Runtime(config=config, provider_configured=True)

        health = runtime.health()
        self.assertEqual(health.status, "not_ready")
        self.assertEqual(health.zdr_policy_state, "required_unprobed")

    def test_production_entrypoint_does_not_import_experiments(self) -> None:
        experiment_modules = {
            "firelens.contextual_retrieval_experiment",
            "firelens.graphrag_experiment",
            "firelens.model_bakeoff",
            "firelens.retrieval_experiment",
        }
        code = (
            "import json,sys; import app; "
            f"blocked={experiment_modules!r}; "
            "print(json.dumps(sorted(blocked.intersection(sys.modules))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), [])
