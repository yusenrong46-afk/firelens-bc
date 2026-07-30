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
from rag_helpers import make_runtime

from firelens.api import ERROR_RESPONSES, create_app
from firelens.operational_logging import LOGGER_NAME


class SecurityAndOperationsTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertEqual(health.headers["x-frame-options"], "DENY")
        self.assertEqual(health.headers["referrer-policy"], "no-referrer")
        self.assertEqual(debug_chunk.status_code, 404)
        self.assertEqual(debug_search.status_code, 404)

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
                "event",
                "trace_id",
                "route",
                "response_mode",
                "latency_ms",
                "provider_stages",
                "error_category",
            },
        )


class ProductionImportBoundaryTests(unittest.TestCase):
    def test_openapi_413_description_is_explicit_and_stable(self) -> None:
        self.assertEqual(ERROR_RESPONSES[413]["description"], "Content Too Large")

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
