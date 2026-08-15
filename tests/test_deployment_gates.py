from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx

from firelens.deployment_gates import qualify_deployment_gates
from firelens.runtime_artifact_common import CANDIDATE_SCHEMA, canonical_json, sha256_bytes

COMMIT = "a" * 40


def _candidate() -> dict[str, str]:
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": f"firelens-v1-5-2:{COMMIT}",
        "release_version": "1.5.3-rc.1",
        "build_commit": COMMIT,
        "corpus_version": "firelens_static_corpus.v1",
        "embedding_model": "openai/text-embedding-3-small",
        "retrieval_text_strategy": "metadata_context_v1",
        "rerank_model": "cohere/rerank-4-pro",
        "generation_model": "openai/gpt-5.6-luna",
        "require_zdr": "true",
    }


def _handler(
    ready: dict[str, object],
    map_payload: dict[str, object] | None = None,
    *,
    ready_status: int = 200,
    ask_payload: dict[str, object] | None = None,
):
    homepage = "<html><title>FireLens BC</title></html>"
    map_body = map_payload or {
        "results": [{"result_id": "incident:1", "status": "Active"}],
        "unavailable_layers": [],
        "limitations": [],
    }
    ask_body = ask_payload or {
        "status": "abstention",
        "reason_code": "personalized_safety_decision",
        "answer": "",
        "claims": [],
        "live_results": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/health/ready":
            return httpx.Response(ready_status, json=ready)
        if request.url.path in {"/", "/index.html"}:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=homepage)
        if request.url.path == "/api/v1/live/map":
            return httpx.Response(200, json=map_body)
        if request.url.path == "/api/v1/ask":
            return httpx.Response(200, json=ask_body)
        return httpx.Response(404, json={"error": "missing"})

    return handler


def _ready(**overrides: object) -> dict[str, object]:
    candidate = _candidate()
    payload: dict[str, object] = {
        "status": "ready",
        "release_version": candidate["release_version"],
        "build_commit": candidate["build_commit"],
        "corpus_version": candidate["corpus_version"],
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": sha256_bytes(canonical_json(candidate)),
        "embedding_model": candidate["embedding_model"],
        "rerank_model": candidate["rerank_model"],
        "generation_model": candidate["generation_model"],
        "retrieval_text_strategy": candidate["retrieval_text_strategy"],
        "zdr_required": True,
        "zdr_policy_state": "eligible",
        "problems": [],
    }
    payload.update(overrides)
    return payload


class DeploymentGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_deployment_gates_pass_when_identity_zdr_and_map_are_honest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "config/runtime_candidate.v1.json"
            candidate_path.parent.mkdir(parents=True)
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(_handler(_ready()))
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                    include_ask_probes=True,
                )
        self.assertTrue(report["qualified"])
        self.assertTrue(report["checks"]["candidate_identity"])
        self.assertTrue(report["checks"]["zdr_required"])
        self.assertTrue(report["checks"]["zdr_policy_eligible"])
        self.assertTrue(report["checks"]["production_refuses_zdr_false"])
        self.assertTrue(report["checks"]["partial_layers_are_visible"])
        self.assertTrue(report["checks"]["ready"])
        self.assertTrue(report["checks"]["safety_boundary"])
        self.assertEqual(report["observed"]["ask_reason_code"], "personalized_safety_decision")

    async def test_deployment_gates_fail_closed_on_wrong_artifact_and_zdr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(
                _handler(
                    _ready(
                        build_commit="b" * 40,
                        zdr_required=False,
                        zdr_policy_state="disabled",
                    )
                )
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["candidate_identity"])
        self.assertFalse(report["checks"]["zdr_required"])
        self.assertFalse(report["checks"]["production_refuses_zdr_false"])

    async def test_deployment_gates_fail_on_silent_partial_layers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(
                _handler(
                    _ready(),
                    map_payload={
                        "results": [],
                        "unavailable_layers": ["evacuations"],
                        "limitations": [],
                    },
                )
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["partial_layers_are_visible"])

    async def test_deployment_gates_fail_on_false_safety_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/api/v1/ask":
                    return httpx.Response(
                        200,
                        json={
                            "status": "answer",
                            "reason_code": None,
                            "answer": "The area is safe right now.",
                            "claims": [{"text": "The area is safe right now."}],
                            "live_results": [],
                        },
                    )
                return _handler(_ready())(request)

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                    include_ask_probes=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["safety_boundary"])
        serialized = json.dumps(report)
        self.assertNotIn("The area is safe right now.", serialized)
        self.assertNotIn("safe right now", serialized)

    async def test_deployment_gates_reject_http_503_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(
                _handler(_ready(status="not_ready"), ready_status=503)
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["ready"])
        self.assertEqual(report["observed"]["ready_status_code"], 503)
        self.assertEqual(report["observed"]["ready_status"], "not_ready")

    async def test_deployment_gates_reject_invented_safety_reason_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(
                _handler(
                    _ready(),
                    ask_payload={
                        "status": "abstention",
                        "reason_code": "safety_boundary",
                        "answer": "",
                        "claims": [],
                        "live_results": [],
                    },
                )
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                    include_ask_probes=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["safety_boundary"])
        self.assertEqual(report["observed"]["ask_reason_code"], "safety_boundary")

    async def test_deployment_gates_require_full_remote_candidate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(), sort_keys=True), encoding="utf-8"
            )
            transport = httpx.MockTransport(
                _handler(
                    _ready(
                        embedding_model="openai/text-embedding-3-large",
                        rerank_model="qwen/qwen3-reranker-8b",
                        candidate_id=None,
                        candidate_sha256=None,
                    )
                )
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                report = await qualify_deployment_gates(
                    client,
                    base_url="http://127.0.0.1",
                    candidate_path=candidate_path,
                    expect_production=True,
                )
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["candidate_identity"])
        self.assertEqual(report["observed"]["embedding_model"], "openai/text-embedding-3-large")
        self.assertIsNone(report["observed"]["candidate_id"])
