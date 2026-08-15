from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from rag_helpers import make_runtime

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime, load_runtime
from firelens.runtime_artifact_common import (
    CANDIDATE_REQUIRED_FIELDS,
    CANDIDATE_SCHEMA,
    RuntimeArtifactError,
)
from firelens.runtime_candidate import (
    apply_runtime_candidate_binding,
    build_runtime_candidate,
    load_runtime_candidate_document,
    write_runtime_candidate,
)
from scripts.write_runtime_candidate import build_runtime_candidate as script_builder

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b00544c1927ffa12d98689f6a4b0b44b6c7de7e1"


def _write_bound_candidate(config: FireLensConfig, **overrides: str) -> Path:
    path = config.project_root / "config/runtime_candidate.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": f"firelens-v1-5-2:{COMMIT}",
        "release_version": config.release_version,
        "build_commit": config.build_commit or COMMIT,
        "corpus_version": "test-corpus.v1",
        "embedding_model": config.embedding_model,
        "retrieval_text_strategy": config.retrieval_text_strategy.value,
        "rerank_model": config.rerank_model,
        "generation_model": config.generation_model,
        **config.privacy.candidate_fields(),
    }
    document.update(overrides)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_runtime_candidate_schema_v3_binds_stage_privacy_policy() -> None:
    document = build_runtime_candidate(
        commit=COMMIT,
        benchmark_id="firelens_v1_5_2",
        release_version="1.5.0-rc.1",
        corpus_manifest_path=ROOT / "data/processed/firelens_static_corpus.manifest.json",
        vector_manifest_path=ROOT / "data/index/firelens_vectors.manifest.json",
        rerank_model="cohere/rerank-4-pro",
        generation_model="openai/gpt-5.6-luna",
        privacy=APPROVED_PRODUCTION_PRIVACY,
    )

    assert document["schema_version"] == "firelens.runtime_candidate.v3"
    assert set(document) == CANDIDATE_REQUIRED_FIELDS
    assert document["rerank_model"] == "cohere/rerank-4-pro"
    assert document["generation_model"] == "openai/gpt-5.6-luna"
    assert document["data_collection"] == "deny"
    assert document["allow_fallbacks"] == "false"
    assert document["require_parameters"] == "true"
    assert document["embedding_zdr"] == "required"
    assert document["reranking_zdr"] == "optional"
    assert document["generation_zdr"] == "required"
    assert script_builder is build_runtime_candidate


def test_runtime_candidate_refuses_secrets_and_invalid_zdr_policy(tmp_path: Path) -> None:
    embedded_key = "vendor/" + "sk" + "-or-v1-" + "secret-material"
    with pytest.raises(ValueError, match="secret"):
        build_runtime_candidate(
            commit=COMMIT,
            benchmark_id="firelens_v1_5_2",
            release_version="1.5.3-rc.1",
            corpus_manifest_path=ROOT / "data/processed/firelens_static_corpus.manifest.json",
            vector_manifest_path=ROOT / "data/index/firelens_vectors.manifest.json",
            rerank_model=embedded_key,
            generation_model="openai/gpt-5.6-luna",
        )
    with pytest.raises(ValueError, match="secret"):
        build_runtime_candidate(
            commit=COMMIT,
            benchmark_id="firelens_v1_5_2",
            release_version="1.5.3-rc.1",
            corpus_manifest_path=ROOT / "data/processed/firelens_static_corpus.manifest.json",
            vector_manifest_path=ROOT / "data/index/firelens_vectors.manifest.json",
            rerank_model="cohere/rerank-4-pro",
            generation_model="sk-not-a-model",
        )
    with pytest.raises(ValueError, match="fields are not exact"):
        write_runtime_candidate(
            tmp_path / "invalid-privacy.json",
            {
                "schema_version": CANDIDATE_SCHEMA,
                "candidate_id": f"firelens-v1-5-2:{COMMIT}",
                "release_version": "1.5.3-rc.1",
                "build_commit": COMMIT,
                "corpus_version": "firelens_static_corpus.v1",
                "embedding_model": "openai/text-embedding-3-small",
                "retrieval_text_strategy": "metadata_context_v1",
                "rerank_model": "cohere/rerank-4-pro",
                "generation_model": "openai/gpt-5.6-luna",
                "require_zdr": "1",
            },
        )
    output = tmp_path / "candidate.json"
    with pytest.raises(ValueError, match="secret"):
        write_runtime_candidate(
            output,
            {
                "schema_version": CANDIDATE_SCHEMA,
                "openrouter_api_key": "secret-material",
            },
        )


def test_loader_rejects_arbitrary_candidate_id_and_unbound_commit(tmp_path: Path) -> None:
    path = tmp_path / "candidate.json"
    document = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": "arbitrary-candidate",
        "release_version": "1.5.3-rc.1",
        "build_commit": COMMIT,
        "corpus_version": "firelens_static_corpus.v1",
        "embedding_model": "openai/text-embedding-3-small",
        "retrieval_text_strategy": "metadata_context_v1",
        "rerank_model": "cohere/rerank-4-pro",
        "generation_model": "openai/gpt-5.6-luna",
        **APPROVED_PRODUCTION_PRIVACY.candidate_fields(),
    }
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="candidate_id"):
        load_runtime_candidate_document(path)

    document["candidate_id"] = f"firelens-v1-5-2:{COMMIT}"
    document["build_commit"] = "not-a-git-sha"
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="build_commit"):
        load_runtime_candidate_document(path)

    other_commit = "c" * 40
    document["build_commit"] = COMMIT
    document["candidate_id"] = f"firelens-v1-5-2:{other_commit}"
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeArtifactError, match="candidate_id"):
        load_runtime_candidate_document(path)
    with pytest.raises(ValueError, match="candidate_id"):
        write_runtime_candidate(tmp_path / "written.json", document)


def test_production_binding_does_not_fail_open_on_retry(tmp_path: Path) -> None:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "production",
            "privacy": APPROVED_PRODUCTION_PRIVACY,
            "build_commit": COMMIT,
            "rerank_model": "cohere/rerank-4-pro",
        }
    )
    _write_bound_candidate(config, rerank_model="qwen/qwen3-reranker-8b")
    runtime = Runtime(config=config)
    with pytest.raises(RuntimeError, match="bound candidate"):
        runtime.apply_bound_candidate()
    assert runtime.bound_candidate is None
    assert runtime.candidate_binding_applied is False
    with pytest.raises(RuntimeError, match="bound candidate"):
        runtime.apply_bound_candidate()


def test_production_refuses_env_mismatch_with_bound_candidate(tmp_path: Path) -> None:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "production",
            "privacy": APPROVED_PRODUCTION_PRIVACY,
            "build_commit": COMMIT,
            "rerank_model": "cohere/rerank-4-pro",
        }
    )
    _write_bound_candidate(config, rerank_model="qwen/qwen3-reranker-8b")
    with pytest.raises(RuntimeError, match="bound candidate"):
        apply_runtime_candidate_binding(config)


def test_production_refuses_missing_candidate(tmp_path: Path) -> None:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "production",
            "privacy": APPROVED_PRODUCTION_PRIVACY,
            "build_commit": COMMIT,
        }
    )
    with pytest.raises(RuntimeError, match="missing the bound candidate"):
        apply_runtime_candidate_binding(config)


def test_preview_refuses_optional_embedding_when_candidate_requires_zdr(
    tmp_path: Path,
) -> None:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "preview",
            "build_commit": COMMIT,
        }
    )
    _write_bound_candidate(config, embedding_zdr="required", generation_zdr="required")
    with pytest.raises(RuntimeError, match="embedding_zdr"):
        apply_runtime_candidate_binding(config)


def test_local_mismatch_stays_usable_and_is_not_production_qualified(
    tmp_path: Path,
) -> None:
    config = FireLensConfig.from_env(tmp_path).model_copy(
        update={
            "deployment_environment": "local",
            "embedding_model": "fake/embedding",
            "debug": True,
        }
    )
    _write_bound_candidate(
        config,
        embedding_zdr="required",
        generation_zdr="required",
        rerank_model="cohere/rerank-4-pro",
    )
    problems = apply_runtime_candidate_binding(config)
    assert problems
    assert any("not a production-qualified artifact" in problem for problem in problems)

    runtime = load_runtime(config)
    health = runtime.health()
    assert health.zdr_required is False
    assert health.zdr_policy_state == "disabled"
    unqualified = [
        problem
        for problem in health.problems
        if "not a production-qualified artifact" in problem
    ]
    assert len(unqualified) == 1
    runtime.apply_bound_candidate()
    assert [
        problem
        for problem in runtime.problems
        if "not a production-qualified artifact" in problem
    ] == unqualified


def test_production_config_still_refuses_optional_required_stages(tmp_path: Path) -> None:
    payload = FireLensConfig.from_env(tmp_path).model_dump()
    payload["deployment_environment"] = "production"
    with pytest.raises(ValidationError, match="embedding and generation"):
        FireLensConfig.model_validate(payload)


class RuntimeCandidateStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_lifespan_allows_optional_non_zdr_reranker(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "openai/gpt-5.6-luna"},
                        {"model_id": "qwen/qwen3-reranker-8b"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = FireLensConfig.from_env(Path(directory)).model_copy(
                update={
                    "deployment_environment": "production",
                    "privacy": APPROVED_PRODUCTION_PRIVACY,
                    "build_commit": COMMIT,
                    "openrouter_api_key": SecretStr("test-key"),
                    "embedding_model": "openai/text-embedding-3-small",
                    "rerank_model": "cohere/rerank-4-pro",
                    "generation_model": "openai/gpt-5.6-luna",
                }
            )
            _write_bound_candidate(config)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                runtime = Runtime(config=config, provider_configured=True, provider=provider)
                app = create_app(config, runtime=runtime)
                async with app.router.lifespan_context(app):
                    self.assertEqual(runtime.zdr_policy_state, "required_stages_eligible")
                    self.assertEqual(runtime.reranking_zdr_state, "zdr_optional")

    async def test_local_create_app_does_not_claim_bound_production_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, _, config = await make_runtime(Path(directory))
            _write_bound_candidate(config, embedding_zdr="required")
            app = create_app(config, runtime=runtime)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/health/ready")
            await runtime.aclose()
        payload = response.json()
        self.assertFalse(payload["zdr_required"])
        unqualified = [
            problem
            for problem in payload["problems"]
            if "not a production-qualified artifact" in problem
        ]
        self.assertEqual(len(unqualified), 1)
        self.assertEqual(payload["embedding_model"], config.embedding_model)
        self.assertEqual(payload["rerank_model"], config.rerank_model)
        self.assertEqual(payload["generation_model"], config.generation_model)
        self.assertIsNone(payload["candidate_id"])
        self.assertIsNone(payload["candidate_sha256"])
