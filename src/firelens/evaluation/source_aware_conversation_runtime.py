"""Offline runtime fixture and observation helpers for source-aware evaluation."""

from __future__ import annotations

import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from firelens.agent.coordinator import FireLensAgent
from firelens.config import FireLensConfig
from firelens.contracts import ConversationTurn, LocationInput, QueryRequest
from firelens.errors import ProviderError, ProviderErrorKind
from firelens.evaluation.productbench_v2_offline import OfflineProductBenchLiveDataService
from firelens.live import LiveDataService
from firelens.live_answering import LiveAnswerCoordinator
from firelens.providers.fake import FakeProvider
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.embeddings import build_vector_index
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[3]


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class _FailingProvider(FakeProvider):
    """Provider double that fails only after the fixture index is built."""

    fail_rerank = False

    async def rerank(self, query: str, documents: Any, *, top_n: int) -> Any:
        if self.fail_rerank:
            raise ProviderError(
                ProviderErrorKind.UNAVAILABLE, "offline rerank fixture failure", retryable=True
            )
        return await super().rerank(query, documents, top_n=top_n)


async def fixture_agent(
    root: Path, *, failing_generation: bool = False
) -> tuple[FireLensAgent, FakeProvider, dict[str, str]]:
    """Build the production runtime with a copied corpus and no external I/O."""

    processed, repairs = root / "data/processed", root / "data/repairs"
    processed.mkdir(parents=True)
    repairs.mkdir(parents=True)
    for name in ("firelens_static_corpus.chunks.jsonl", "firelens_static_corpus.manifest.json"):
        shutil.copy2(ROOT / "data/processed" / name, processed / name)
    shutil.copy2(ROOT / "data/repairs/text_overrides.yaml", repairs / "text_overrides.yaml")
    records = load_chunk_records(processed / "firelens_static_corpus.chunks.jsonl")
    provider: FakeProvider = (
        _FailingProvider(dimensions=1536)
        if failing_generation
        else FakeProvider(dimensions=1536)
    )
    config = FireLensConfig.from_env(root).model_copy(
        update={"embedding_model": "fake/embedding", "debug": True}
    )
    await build_vector_index(
        records, corpus_version="firelens_static_corpus.v1", config=config, provider=provider
    )
    if failing_generation:
        assert isinstance(provider, _FailingProvider)
        provider.fail_rerank = True
    runtime = load_runtime(config, provider=provider)
    if runtime.service is None:
        raise RuntimeError(
            "offline fixture runtime could not be assembled: " + "; ".join(runtime.problems)
        )
    return (
        FireLensAgent(
            runtime.service,
            LiveAnswerCoordinator(cast(LiveDataService, OfflineProductBenchLiveDataService())),
        ),
        provider,
        {
            "corpus_sha256": file_sha256(processed / "firelens_static_corpus.chunks.jsonl"),
            "corpus_manifest_sha256": file_sha256(
                processed / "firelens_static_corpus.manifest.json"
            ),
            "vector_matrix_sha256": file_sha256(config.vector_matrix_path),
            "vector_manifest_sha256": file_sha256(config.vector_manifest_path),
        },
    )


def _lane_from_response(response: Any) -> str | None:
    if response.live_results and response.claims:
        return "mixed"
    if response.live_results:
        return "official_live"
    kinds = {claim.publication.kind.value for claim in response.claims if claim.publication}
    if kinds & {"structured_reviewed", "source_linked_explanation"}:
        return "reviewed_guidance"
    if "official_quote_only" in kinds:
        return "official_quote"
    if "general_background" in kinds:
        return "general"
    return None


def _observation(
    case_id: str,
    question: str,
    execution: Any,
    provider: FakeProvider,
    before: dict[str, int],
    history_turns: int,
) -> dict[str, Any]:
    response = execution.response
    after = {name: int(getattr(provider, name)) for name in before}
    provider_calls = {name: after[name] - before[name] for name in before}
    publication_kinds = {
        claim.publication.kind.value for claim in response.claims if claim.publication
    }
    has_authoritative_output = bool(response.live_results) or bool(
        publication_kinds
        & {"structured_reviewed", "official_quote_only", "official_live_typed"}
    )
    return {
        "id": case_id,
        "question": question,
        "request_valid": True,
        "route": execution.route.value,
        "response_mode": response.response_mode.value,
        "status": response.status.value,
        "observed_source_lane": _lane_from_response(response),
        "publication_kinds": sorted(publication_kinds),
        "live_result_kinds": sorted({result.kind.value for result in response.live_results}),
        "tool_traces": [tool.value for tool in execution.tools],
        "provider_stages": list(execution.policy.provider_stages),
        "provider_calls": provider_calls,
        "tier_a_b_generation_calls": (
            provider_calls["generate_calls"] if has_authoritative_output else 0
        ),
        "tier_a_b_generation_cost_usd": 0.0,
        "evidence_count": len(response.evidence),
        "claim_count": len(response.claims),
        "live_result_count": len(response.live_results),
        "reason_code": response.reason_code.value if response.reason_code else None,
        "has_answer": bool(response.answer),
        "history_turns": history_turns,
    }


async def execute_one(
    agent: FireLensAgent,
    provider: FakeProvider,
    case_id: str,
    question: str,
    *,
    location: LocationInput | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Execute one real request and return an auditable runtime observation."""

    before = {
        name: int(getattr(provider, name))
        for name in ("plan_calls", "embed_calls", "rerank_calls", "generate_calls")
    }
    try:
        request = QueryRequest(
            question=question,
            location=location,
            history=[ConversationTurn.model_validate(turn) for turn in (history or [])],
        )
    except Exception as exc:
        return _failure_observation(
            case_id,
            question,
            provider,
            before,
            history,
            "validation_error",
            "request_validation_error",
            exc,
        )
    try:
        execution = await agent.answer(request)
    except Exception as exc:
        return _failure_observation(
            case_id,
            question,
            provider,
            before,
            history,
            "execution_error",
            type(exc).__name__,
            exc,
        )
    return _observation(case_id, question, execution, provider, before, len(history or []))


def _failure_observation(
    case_id: str,
    question: str,
    provider: FakeProvider,
    before: dict[str, int],
    history: list[dict[str, str]] | None,
    status: str,
    reason_code: str,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "question": question,
        "request_valid": status != "validation_error",
        "route": None,
        "response_mode": None,
        "status": status,
        "observed_source_lane": None,
        "publication_kinds": [],
        "live_result_kinds": [],
        "tool_traces": [],
        "provider_stages": [],
        "provider_calls": {
            name: int(getattr(provider, name)) - before[name] for name in before
        },
        "tier_a_b_generation_calls": 0,
        "tier_a_b_generation_cost_usd": 0.0,
        "evidence_count": 0,
        "claim_count": 0,
        "live_result_count": 0,
        "reason_code": reason_code,
        "has_answer": False,
        "history_turns": len(history or []),
        "error": str(exc),
    }
