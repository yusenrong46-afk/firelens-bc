from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    ConversationTurn,
    GroundedDraft,
    LocationInput,
    PlanningDecision,
    QueryRequest,
)
from firelens.errors import ProviderError
from firelens.privacy_policy import (
    APPROVED_PRODUCTION_PRIVACY,
    LOCAL_DEFAULT_PRIVACY,
    evaluate_zdr_preflight,
    resolve_openrouter_privacy_from_env,
)
from firelens.providers.fake import FakeProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import Runtime
from firelens.runtime_artifact_common import CANDIDATE_SCHEMA, RuntimeArtifactError
from firelens.runtime_candidate import load_runtime_candidate_document

COMMIT = "b00544c1927ffa12d98689f6a4b0b44b6c7de7e1"
CONTEXT_WORDS = " ".join(["reviewed"] * 24)


def _setting(values: dict[str, str]):
    return values.get


def _assert_common_preferences(
    preferences: dict[str, object],
    *,
    zdr: bool,
    require_parameters: bool = True,
) -> None:
    assert preferences["data_collection"] == "deny"
    assert preferences["allow_fallbacks"] is False
    if require_parameters:
        assert preferences["require_parameters"] is True
    else:
        assert "require_parameters" not in preferences
    assert preferences.get("zdr") is not False
    if zdr:
        assert preferences["zdr"] is True
    else:
        assert "zdr" not in preferences


class PrivacyPolicyResolutionTests(unittest.TestCase):
    def test_local_default_keeps_every_stage_optional(self) -> None:
        policy = resolve_openrouter_privacy_from_env(_setting({}))
        self.assertEqual(policy, LOCAL_DEFAULT_PRIVACY)
        self.assertFalse(policy.any_zdr_required)

    def test_legacy_true_selects_approved_mix_not_all_required(self) -> None:
        policy = resolve_openrouter_privacy_from_env(_setting({"FIRELENS_REQUIRE_ZDR": "true"}))
        self.assertEqual(policy, APPROVED_PRODUCTION_PRIVACY)
        self.assertEqual(policy.reranking_zdr, "optional")
        self.assertTrue(policy.any_zdr_required)

    def test_legacy_false_keeps_stages_optional(self) -> None:
        policy = resolve_openrouter_privacy_from_env(
            _setting({"FIRELENS_REQUIRE_ZDR": "false"})
        )
        self.assertEqual(policy.embedding_zdr, "optional")
        self.assertEqual(policy.generation_zdr, "optional")

    def test_explicit_stage_variables_are_the_source_of_truth(self) -> None:
        policy = resolve_openrouter_privacy_from_env(
            _setting(
                {
                    "FIRELENS_EMBEDDING_ZDR": "required",
                    "FIRELENS_RERANKING_ZDR": "required",
                    "FIRELENS_GENERATION_ZDR": "required",
                }
            )
        )
        self.assertEqual(policy.reranking_zdr, "required")

    def test_legacy_true_with_optional_embedding_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "EMBEDDING_ZDR"):
            resolve_openrouter_privacy_from_env(
                _setting(
                    {
                        "FIRELENS_REQUIRE_ZDR": "true",
                        "FIRELENS_EMBEDDING_ZDR": "optional",
                    }
                )
            )

    def test_legacy_false_with_required_stage_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "FIRELENS_REQUIRE_ZDR=false"):
            resolve_openrouter_privacy_from_env(
                _setting(
                    {
                        "FIRELENS_REQUIRE_ZDR": "false",
                        "FIRELENS_GENERATION_ZDR": "required",
                    }
                )
            )

    def test_data_collection_allow_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "DATA_COLLECTION"):
            resolve_openrouter_privacy_from_env(_setting({"FIRELENS_DATA_COLLECTION": "allow"}))

    def test_allow_fallbacks_true_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ALLOW_FALLBACKS"):
            resolve_openrouter_privacy_from_env(_setting({"FIRELENS_ALLOW_FALLBACKS": "true"}))

    def test_production_rejects_optional_embedding_or_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = FireLensConfig.from_env(Path(directory)).model_dump()
            payload["deployment_environment"] = "production"
            with pytest.raises(ValidationError, match="embedding and generation"):
                FireLensConfig.model_validate(payload)
            payload["privacy"] = APPROVED_PRODUCTION_PRIVACY.model_dump()
            payload["privacy"]["reranking_zdr"] = "optional"
            FireLensConfig.model_validate(payload)


def test_legacy_true_is_enough_for_production_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRELENS_REQUIRE_ZDR", "true")
    monkeypatch.setenv("FIRELENS_ENVIRONMENT", "production")
    config = FireLensConfig.from_env(tmp_path)
    assert config.privacy == APPROVED_PRODUCTION_PRIVACY
    assert config.deployment_environment == "production"


class ZdrPreflightPolicyTests(unittest.TestCase):
    def test_missing_reranker_is_optional_under_approved_policy(self) -> None:
        report = evaluate_zdr_preflight(
            APPROVED_PRODUCTION_PRIVACY,
            embedding_model="openai/text-embedding-3-small",
            rerank_model="cohere/rerank-4-pro",
            generation_model="openai/gpt-5.6-luna",
            eligible_models={
                "openai/text-embedding-3-small",
                "openai/gpt-5.6-luna",
            },
        )
        self.assertEqual(report.embedding, "eligible")
        self.assertEqual(report.generation, "eligible")
        self.assertEqual(report.reranking, "zdr_optional")
        self.assertEqual(report.missing_required_models, ())

    def test_missing_embedding_fails_closed(self) -> None:
        report = evaluate_zdr_preflight(
            APPROVED_PRODUCTION_PRIVACY,
            embedding_model="openai/text-embedding-3-small",
            rerank_model="cohere/rerank-4-pro",
            generation_model="openai/gpt-5.6-luna",
            eligible_models={"openai/gpt-5.6-luna", "cohere/rerank-4-pro"},
        )
        self.assertEqual(report.embedding, "failed")
        self.assertEqual(report.missing_required_models, ("openai/text-embedding-3-small",))

    def test_missing_generation_fails_closed(self) -> None:
        report = evaluate_zdr_preflight(
            APPROVED_PRODUCTION_PRIVACY,
            embedding_model="openai/text-embedding-3-small",
            rerank_model="cohere/rerank-4-pro",
            generation_model="openai/gpt-5.6-luna",
            eligible_models={"openai/text-embedding-3-small", "cohere/rerank-4-pro"},
        )
        self.assertEqual(report.generation, "failed")
        self.assertTrue(report.missing_required_models)

    def test_required_reranker_still_fails_when_missing(self) -> None:
        policy = APPROVED_PRODUCTION_PRIVACY.model_copy(update={"reranking_zdr": "required"})
        report = evaluate_zdr_preflight(
            policy,
            embedding_model="openai/text-embedding-3-small",
            rerank_model="cohere/rerank-4-pro",
            generation_model="openai/gpt-5.6-luna",
            eligible_models={
                "openai/text-embedding-3-small",
                "openai/gpt-5.6-luna",
            },
        )
        self.assertEqual(report.reranking, "failed")
        self.assertEqual(report.missing_required_models, ("cohere/rerank-4-pro",))


class StageAwareProviderWireTests(unittest.IsolatedAsyncioTestCase):
    def _config(self, directory: str) -> FireLensConfig:
        return write_test_corpus(Path(directory), [make_chunk("a", "water")]).model_copy(
            update={
                "openrouter_api_key": SecretStr("test-key"),
                "openrouter_base_url": "https://openrouter.test/api/v1",
                "embedding_model": "openai/text-embedding-3-small",
                "rerank_model": "cohere/rerank-4-pro",
                "generation_model": "openai/gpt-5.6-luna",
                "privacy": APPROVED_PRODUCTION_PRIVACY,
            }
        )

    async def test_embedding_and_generation_send_zdr_rerank_omits_it(self) -> None:
        observed: dict[str, dict[str, object]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            path = request.url.path
            observed[path] = body
            if path.endswith("/embeddings"):
                return httpx.Response(
                    200,
                    json={
                        "model": "text-embedding-3-small",
                        "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                    },
                )
            if path.endswith("/rerank"):
                return httpx.Response(
                    200,
                    json={
                        "model": "rerank-v4.0-pro",
                        "results": [{"index": 0, "relevance_score": 0.9}],
                    },
                )
            content = {
                "/chat/completions": (
                    '{"relation":"grounded_candidate","retrieval_queries":["q"],'
                    '"explanation":"probe","required_aspects":[]}'
                )
            }
            return httpx.Response(
                200,
                json={
                    "model": "openai/gpt-5.6-luna",
                    "choices": [{"message": {"content": content["/chat/completions"]}}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                await provider.embed(["water"])
                await provider.rerank("water", ["passage"], top_n=1)
                await provider.plan(
                    [{"role": "user", "content": "plan"}],
                    output_schema=PlanningDecision.model_json_schema(),
                )

        embed_prefs = observed["/api/v1/embeddings"]["provider"]
        rerank_body = observed["/api/v1/rerank"]
        plan_prefs = observed["/api/v1/chat/completions"]["provider"]
        _assert_common_preferences(embed_prefs, zdr=True)
        _assert_common_preferences(rerank_body["provider"], zdr=False)
        _assert_common_preferences(plan_prefs, zdr=True, require_parameters=False)
        self.assertEqual(
            set(rerank_body),
            {"model", "query", "documents", "top_n", "provider"},
        )
        self.assertEqual(rerank_body["query"], "water")
        self.assertEqual(rerank_body["documents"], ["passage"])
        source = Path(__file__).resolve().parents[1] / "src/firelens/providers/openrouter.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn('"zdr": False', text)
        self.assertNotIn('"allow_fallbacks": True', text)

    async def test_grounded_background_and_repair_generation_send_zdr(self) -> None:
        observed: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            observed.append(body)
            name = body["response_format"]["json_schema"]["name"]
            if name == "firelens_grounded_answer":
                content = (
                    '{"claims":[{"text":"Bring water.","evidence_quote_ids":["e1"]}],'
                    '"limitations":[],"requires_live_verification":false}'
                )
            elif name == "firelens_background_answer":
                content = (
                    '{"claims":[{"text":"Smoke can travel."}],'
                    f'"limitations":["{BACKGROUND_LIMITATION}"],'
                    '"requires_live_verification":false}'
                )
            else:
                content = json.dumps(
                    {
                        "items": [
                            {
                                "chunk_id": "chunk-a0",
                                "context": CONTEXT_WORDS,
                            }
                        ]
                    }
                )
            return httpx.Response(
                200,
                json={
                    "model": "openai/gpt-5.6-luna",
                    "choices": [{"message": {"content": content}}],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                await provider.generate_grounded(
                    [{"role": "user", "content": "answer"}],
                    output_schema=GroundedDraft.model_json_schema(),
                )
                await provider.generate_background(
                    [{"role": "user", "content": "background"}],
                    output_schema={
                        "type": "object",
                        "properties": {
                            "claims": {"type": "array"},
                            "limitations": {"type": "array"},
                            "requires_live_verification": {"type": "boolean"},
                        },
                        "required": ["claims", "limitations", "requires_live_verification"],
                    },
                )
                await provider.generate_contexts(
                    [{"role": "user", "content": "repair"}],
                    output_schema={
                        "type": "object",
                        "properties": {"items": {"type": "array"}},
                        "required": ["items"],
                    },
                )

        self.assertEqual(len(observed), 3)
        for body in observed:
            _assert_common_preferences(body["provider"], zdr=True, require_parameters=False)

    async def test_preflight_allows_missing_optional_reranker(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "openai/gpt-5.6-luna"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                report = await OpenRouterProvider(config, client=client).preflight_zdr()
        self.assertEqual(report.reranking, "zdr_optional")
        self.assertEqual(report.missing_required_models, ())

    async def test_preflight_rejects_unreadable_roster(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-json")

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(ProviderError, "invalid ZDR"):
                    await OpenRouterProvider(config, client=client).preflight_zdr()

    async def test_required_reranker_preflight_still_fails_closed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "openai/gpt-5.6-luna"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory).with_privacy(reranking_zdr="required")
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(ProviderError, "required stages"):
                    await OpenRouterProvider(config, client=client).preflight_zdr()


class ProductionLifespanAndReadinessTests(unittest.IsolatedAsyncioTestCase):
    def _candidate(self, config: FireLensConfig) -> None:
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
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    async def test_production_starts_when_cohere_is_absent_from_zdr_roster(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_id": "openai/text-embedding-3-small"},
                        {"model_id": "openai/gpt-5.6-luna"},
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
            self._candidate(config)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                runtime = Runtime(config=config, provider_configured=True, provider=provider)
                app = create_app(config, runtime=runtime)
                async with app.router.lifespan_context(app):
                    health = runtime.health()
                    self.assertEqual(runtime.zdr_policy_state, "required_stages_eligible")
                    self.assertEqual(health.zdr_policy_state, "required_stages_eligible")
                    self.assertEqual(health.embedding_zdr_state, "eligible")
                    self.assertEqual(health.generation_zdr_state, "eligible")
                    self.assertEqual(health.reranking_zdr_state, "zdr_optional")
                    self.assertEqual(health.reranking_zdr, "optional")
                    self.assertTrue(health.zdr_required)
                    self.assertEqual(health.data_collection, "deny")
                    self.assertFalse(health.allow_fallbacks)

    async def test_production_still_fails_when_generation_is_ineligible(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": [{"model_id": "openai/text-embedding-3-small"}]},
            )

        with tempfile.TemporaryDirectory() as directory:
            config = FireLensConfig.from_env(Path(directory)).model_copy(
                update={
                    "deployment_environment": "production",
                    "privacy": APPROVED_PRODUCTION_PRIVACY,
                    "build_commit": COMMIT,
                    "openrouter_api_key": SecretStr("test-key"),
                }
            )
            self._candidate(config)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider(config, client=client)
                runtime = Runtime(config=config, provider_configured=True, provider=provider)
                app = create_app(config, runtime=runtime)
                with self.assertRaisesRegex(RuntimeError, "ZDR endpoint preflight failed"):
                    async with app.router.lifespan_context(app):
                        pass
                self.assertEqual(runtime.zdr_policy_state, "failed")
                self.assertEqual(runtime.generation_zdr_state, "failed")

    def test_loader_rejects_v2_all_model_zdr_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "firelens.runtime_candidate.v2",
                        "candidate_id": f"firelens-v1-5-2:{COMMIT}",
                        "release_version": "1.5.3-rc.1",
                        "build_commit": COMMIT,
                        "corpus_version": "firelens_static_corpus.v1",
                        "embedding_model": "openai/text-embedding-3-small",
                        "retrieval_text_strategy": "metadata_context_v1",
                        "rerank_model": "cohere/rerank-4-pro",
                        "generation_model": "openai/gpt-5.6-luna",
                        "require_zdr": "true",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeArtifactError, "unsupported"):
                load_runtime_candidate_document(path)


class RerankMinimizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rerank_receives_only_normalized_query_and_corpus_passages(self) -> None:
        class RecordingProvider(FakeProvider):
            def __init__(self) -> None:
                super().__init__()
                self.rerank_query = ""
                self.rerank_documents: list[str] = []

            async def rerank(self, query, documents, *, top_n):
                self.rerank_query = query
                self.rerank_documents = list(documents)
                return await super().rerank(query, documents, top_n=top_n)

        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            runtime, _, _ = await make_runtime(Path(directory), provider=provider)
            assert runtime.service is not None
            await runtime.service.ask(
                QueryRequest(
                    question="What belongs in an emergency kit?",
                    history=[
                        ConversationTurn(
                            role="assistant",
                            content="PRIVATE-PREVIOUS-ANSWER should never be reranked.",
                        )
                    ],
                    location=LocationInput(latitude=49.12, longitude=-119.65),
                )
            )

        self.assertTrue(provider.rerank_query)
        self.assertTrue(provider.rerank_documents)
        blob = provider.rerank_query + "\n" + "\n".join(provider.rerank_documents)
        self.assertNotIn("PRIVATE-PREVIOUS-ANSWER", blob)
        self.assertNotIn("49.12", blob)
        self.assertNotIn("-119.65", blob)
        self.assertNotIn("trace_id", blob)
        for document in provider.rerank_documents:
            self.assertTrue(
                document.startswith("Publisher:") or "Passage:" in document or document
            )


def test_pipeline_rerank_call_does_not_include_history_or_coordinates() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src/firelens/retrieval/pipeline.py"
    ).read_text(encoding="utf-8")
    self_index = source.index("response = await self.provider.rerank(")
    snippet = source[self_index : self_index + 400]
    assert "plan.normalized_question" in snippet
    assert "render_retrieval_text(" in snippet
    assert "history" not in snippet
    assert "latitude" not in snippet
    assert "conversation" not in snippet
    assert "trace_id" not in snippet
