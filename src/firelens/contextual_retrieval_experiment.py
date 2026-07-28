"""Development-only A/B/C comparison for contextual retrieval text.

The runner deliberately bypasses answer generation.  It saves one bounded
planning decision per grounded development case, reuses those exact plans for
the original and contextual multi-query candidates, and builds the contextual
index under caller-supplied isolated paths.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from firelens.answering.intent import apply_planning_decision, plan_query
from firelens.answering.planner import planning_messages, planning_schema
from firelens.benchmark import (
    ConversationBenchmarkCase,
    GoldEvidence,
    load_conversation_benchmark,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    DocumentContextResponse,
    EmbeddingResponse,
    GenerationResponse,
    PlanningDecision,
    PlanningResponse,
    QueryPlan,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    RerankResponse,
    ResponseMode,
    RetrievalBundle,
    RetrievalTextStrategy,
)
from firelens.errors import IndexValidationError, ProviderError
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.retrieval.embeddings import build_vector_index, sha256_file
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.retrieval.vector import VectorIndex
from firelens.runtime import load_corpus_resources
from firelens.storage import atomic_text_writer

CANDIDATE_A = "A_original_raw_question"
CANDIDATE_B = "B_original_planned_queries"
CANDIDATE_C = "C_contextual_planned_queries"
PRIMARY_METRIC = "rerank_recall_at_5"


def _usage_cost(value: object) -> float:
    if isinstance(value, dict):
        own = value.get("cost")
        total = float(own) if isinstance(own, (int, float)) else 0.0
        return total + sum(_usage_cost(child) for key, child in value.items() if key != "cost")
    if isinstance(value, list):
        return sum(_usage_cost(item) for item in value)
    return 0.0


class _RecordingProvider:
    """Observe provider boundaries without changing the provider protocol."""

    def __init__(self, delegate: AIProvider) -> None:
        self.delegate = delegate
        self.events: list[dict[str, Any]] = []

    async def _record(
        self, operation: str, call: Callable[[], Any]
    ) -> EmbeddingResponse | RerankResponse | PlanningResponse | GenerationResponse:
        started = perf_counter()
        try:
            response = await call()
        except ProviderError as exc:
            self.events.append(
                {
                    "operation": operation,
                    "latency_ms": (perf_counter() - started) * 1_000,
                    "usage": {},
                    "attempts": 0,
                    "model": None,
                    "error_kind": exc.kind.value,
                }
            )
            raise
        self.events.append(
            {
                "operation": operation,
                "latency_ms": (perf_counter() - started) * 1_000,
                "usage": response.usage,
                "attempts": response.attempts,
                "model": response.model,
                "error_kind": None,
            }
        )
        return response

    async def plan(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse:
        response = await self._record(
            "planner", lambda: self.delegate.plan(messages, output_schema=output_schema)
        )
        if not isinstance(response, PlanningResponse):
            raise TypeError("provider returned the wrong planning response type")
        return response

    async def generate_contexts(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> DocumentContextResponse:
        response = await self.delegate.generate_contexts(messages, output_schema=output_schema)
        self.events.append(
            {
                "operation": "document_context",
                "latency_ms": 0.0,
                "usage": response.usage,
                "attempts": response.attempts,
                "model": response.model,
                "error_kind": None,
            }
        )
        return response

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        response = await self._record("embeddings", lambda: self.delegate.embed(texts))
        if not isinstance(response, EmbeddingResponse):
            raise TypeError("provider returned the wrong embedding response type")
        return response

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> RerankResponse:
        response = await self._record(
            "reranker",
            lambda: self.delegate.rerank(query, documents, top_n=top_n),
        )
        if not isinstance(response, RerankResponse):
            raise TypeError("provider returned the wrong rerank response type")
        return response

    async def generate_grounded(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        response = await self._record(
            "grounded_generation",
            lambda: self.delegate.generate_grounded(messages, output_schema=output_schema),
        )
        if not isinstance(response, GenerationResponse):
            raise TypeError("provider returned the wrong generation response type")
        return response

    async def generate_background(
        self,
        messages: Sequence[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> GenerationResponse:
        response = await self._record(
            "background_generation",
            lambda: self.delegate.generate_background(messages, output_schema=output_schema),
        )
        if not isinstance(response, GenerationResponse):
            raise TypeError("provider returned the wrong generation response type")
        return response


def _event_summary(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "call_count": len(events),
        "reported_cost_usd": sum(_usage_cost(event["usage"]) for event in events),
        "latency_ms": sum(float(event["latency_ms"]) for event in events),
        "provider_errors": [
            str(event["error_kind"]) for event in events if event["error_kind"]
        ],
        "models": sorted(
            {str(event["model"]) for event in events if event["model"] is not None}
        ),
    }


def _file_fingerprints(config: FireLensConfig) -> dict[str, str | None]:
    paths = {
        "matrix": config.vector_matrix_path,
        "manifest": config.vector_manifest_path,
        "embedding_cache": config.embedding_cache_path,
    }
    return {name: sha256_file(path) if path.is_file() else None for name, path in paths.items()}


def _experiment_config(
    config: FireLensConfig,
    experiment_dir: Path,
    strategy: RetrievalTextStrategy,
) -> FireLensConfig:
    root = experiment_dir.resolve() / strategy.value
    matrix_path = root / "firelens_vectors.npy"
    manifest_path = root / "firelens_vectors.manifest.json"
    cache_path = root / "embedding_cache.jsonl"
    updates = {
        "retrieval_text_strategy": strategy,
        "vector_matrix_path": matrix_path,
        "vector_manifest_path": manifest_path,
        "embedding_cache_path": cache_path,
        "trace_dir": root / "traces",
    }
    original_paths = {
        config.vector_matrix_path.resolve(),
        config.vector_manifest_path.resolve(),
        config.embedding_cache_path.resolve(),
    }
    experiment_paths = {matrix_path.resolve(), manifest_path.resolve(), cache_path.resolve()}
    if original_paths & experiment_paths:
        raise ValueError("experiment paths must not overlap governed index files")
    return config.model_copy(update=updates)


async def _load_or_build_experiment_index(
    chunks: Sequence[ChunkRecord],
    *,
    corpus_version: str,
    config: FireLensConfig,
    provider: AIProvider,
) -> tuple[VectorIndex, bool]:
    try:
        index = VectorIndex.load(
            chunks,
            matrix_path=config.vector_matrix_path,
            manifest_path=config.vector_manifest_path,
            corpus_path=config.corpus_path,
            corpus_version=corpus_version,
            embedding_model=config.embedding_model,
            retrieval_text_strategy=config.retrieval_text_strategy,
        )
        return index, True
    except IndexValidationError:
        await build_vector_index(
            chunks,
            corpus_version=corpus_version,
            config=config,
            provider=provider,
        )
        return (
            VectorIndex.load(
                chunks,
                matrix_path=config.vector_matrix_path,
                manifest_path=config.vector_manifest_path,
                corpus_path=config.corpus_path,
                corpus_version=corpus_version,
                embedding_model=config.embedding_model,
                retrieval_text_strategy=config.retrieval_text_strategy,
            ),
            False,
        )


def _matches(chunk: ChunkRecord, evidence: GoldEvidence) -> bool:
    if chunk.source_id != evidence.source_id:
        return False
    if evidence.chunk_ids and chunk.chunk_id not in evidence.chunk_ids:
        return False
    return not evidence.pages or chunk.page_number in evidence.pages


def _ranking_result(
    chunk_ids: Sequence[str],
    case: ConversationBenchmarkCase,
    chunks_by_id: Mapping[str, ChunkRecord],
) -> dict[str, float | int | None]:
    relevant_ranks = [
        rank
        for rank, chunk_id in enumerate(chunk_ids, start=1)
        if chunk_id in chunks_by_id
        and any(_matches(chunks_by_id[chunk_id], item) for item in case.acceptable_evidence)
    ]
    first_rank = min(relevant_ranks) if relevant_ranks else None
    return {
        "hit": int(first_rank is not None),
        "first_rank": first_rank,
        "reciprocal_rank": 0.0 if first_rank is None else 1 / first_rank,
    }


def _unique_rankings(bundle: RetrievalBundle, prefix: str) -> list[str]:
    """Flatten per-query top-20 rankings, preserving first occurrence."""

    keys = sorted(
        (key for key in bundle.rankings if key.startswith(f"{prefix}:")),
        key=lambda key: int(key.split(":", 1)[1]),
    )
    return list(dict.fromkeys(chunk_id for key in keys for chunk_id in bundle.rankings[key]))


def _plan_sha256(plan: QueryPlan) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _empty_stage_metrics() -> dict[str, dict[str, float | int | None]]:
    empty: dict[str, float | int | None] = {
        "hit": 0,
        "first_rank": None,
        "reciprocal_rank": 0.0,
    }
    return {stage: dict(empty) for stage in ("bm25", "dense", "fused", "rerank")}


async def _run_candidate(
    name: str,
    *,
    cases: Sequence[ConversationBenchmarkCase],
    plans: Mapping[str, QueryPlan],
    planning_errors: Mapping[str, str],
    pipeline: RetrievalPipeline,
    recorder: _RecordingProvider,
    chunks_by_id: Mapping[str, ChunkRecord],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        plan = plans.get(case.id)
        if plan is None:
            rows.append(
                {
                    "id": case.id,
                    "complete": False,
                    "errors": [planning_errors.get(case.id, "missing_plan")],
                    "plan_sha256": None,
                    "latency_ms": 0.0,
                    "reported_cost_usd": 0.0,
                    "stage_metrics": _empty_stage_metrics(),
                }
            )
            continue
        event_start = len(recorder.events)
        started = perf_counter()
        bundle = await pipeline.search(plan)
        latency_ms = (perf_counter() - started) * 1_000
        events = recorder.events[event_start:]
        rankings = {
            "bm25": _unique_rankings(bundle, "bm25"),
            "dense": _unique_rankings(bundle, "vector"),
            "fused": [hit.chunk_id for hit in bundle.fused_hits[:20]],
            "rerank": [hit.chunk_id for hit in bundle.reranked_hits[:5]],
        }
        rows.append(
            {
                "id": case.id,
                "complete": bundle.complete and not bundle.errors,
                "errors": bundle.errors,
                "plan_sha256": _plan_sha256(plan),
                "retrieval_query_count": len(plan.retrieval_requests),
                "latency_ms": latency_ms,
                "reported_cost_usd": _event_summary(events)["reported_cost_usd"],
                "stage_metrics": {
                    stage: _ranking_result(chunk_ids, case, chunks_by_id)
                    for stage, chunk_ids in rankings.items()
                },
            }
        )

    def recall(stage: str) -> float:
        return sum(float(row["stage_metrics"][stage]["hit"]) for row in rows) / len(rows)

    latencies = [float(row["latency_ms"]) for row in rows]
    summary = {
        "name": name,
        "case_count": len(rows),
        "complete": all(bool(row["complete"]) for row in rows),
        "provider_error_count": sum(len(row["errors"]) for row in rows),
        "reported_cost_usd": sum(float(row["reported_cost_usd"]) for row in rows),
        "latency_ms": {
            "mean": sum(latencies) / len(latencies),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "metrics": {
            "bm25_recall_at_20": recall("bm25"),
            "dense_recall_at_20": recall("dense"),
            "fused_recall_at_20": recall("fused"),
            PRIMARY_METRIC: recall("rerank"),
            "rerank_mrr_at_5": sum(
                float(row["stage_metrics"]["rerank"]["reciprocal_rank"]) for row in rows
            )
            / len(rows),
        },
    }
    return summary, rows


def select_contextual_strategy(
    candidates: Mapping[str, Mapping[str, Any]],
    *,
    safety_passed: bool,
    minimum_gain: float = 0.02,
) -> tuple[str, str]:
    """Select contextual text only on a safe two-point gain over planned original."""

    baseline = candidates[CANDIDATE_B]
    contextual = candidates[CANDIDATE_C]
    if not safety_passed:
        return RetrievalTextStrategy.ORIGINAL_V1.value, "safety conditions did not pass"
    if not baseline["complete"] or not contextual["complete"]:
        return RetrievalTextStrategy.ORIGINAL_V1.value, "comparison did not complete"
    baseline_recall = float(baseline["metrics"][PRIMARY_METRIC])
    contextual_recall = float(contextual["metrics"][PRIMARY_METRIC])
    if contextual_recall + 1e-12 < baseline_recall + minimum_gain:
        return (
            RetrievalTextStrategy.ORIGINAL_V1.value,
            "contextual retrieval did not clear the two-point Recall@5 rule",
        )
    return (
        RetrievalTextStrategy.METADATA_CONTEXT_V1.value,
        "contextual retrieval safely improved Recall@5 by at least two points",
    )


async def run_contextual_retrieval_comparison(
    config: FireLensConfig,
    *,
    dataset_path: Path,
    output_path: Path,
    experiment_dir: Path,
    provider: AIProvider | None = None,
) -> dict[str, Any]:
    """Compare raw, planned, and contextual retrieval on grounded development cases."""

    dataset = load_conversation_benchmark(dataset_path)
    cases = [
        case
        for case in dataset.cases
        if case.split == "development"
        and case.expected_response_mode == ResponseMode.GROUNDED
        and case.acceptable_evidence
    ]
    if not cases:
        raise ValueError("conversation dataset has no grounded development cases")
    scope_valid = all(
        case.risk_level == "ordinary"
        and case.expected_route == QueryRoute.RELATED
        and case.expected_planning_relation == QueryRelation.GROUNDED_CANDIDATE
        for case in cases
    )
    if not scope_valid:
        raise ValueError("retrieval comparison scope contains a non-grounded safety case")

    original_config = _experiment_config(
        config,
        experiment_dir,
        RetrievalTextStrategy.ORIGINAL_V1,
    )
    contextual_config = _experiment_config(
        config,
        experiment_dir,
        RetrievalTextStrategy.METADATA_CONTEXT_V1,
    )
    governed_before = _file_fingerprints(config)
    chunks, corpus_version = load_corpus_resources(config)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}

    owned_provider = provider is None
    delegate = provider or OpenRouterProvider(original_config)
    recorder = _RecordingProvider(delegate)
    planned: dict[str, QueryPlan] = {}
    planning_errors: dict[str, str] = {}
    saved_decisions: dict[str, dict[str, Any]] = {}
    try:
        original_index_event_start = len(recorder.events)
        original_index, original_reused = await _load_or_build_experiment_index(
            chunks,
            corpus_version=corpus_version,
            config=original_config,
            provider=recorder,
        )
        original_index_events = recorder.events[original_index_event_start:]
        planning_event_start = len(recorder.events)
        for case in cases:
            request = QueryRequest(question=case.question, history=case.history)
            try:
                response = await recorder.plan(
                    planning_messages(request), output_schema=planning_schema()
                )
                base_plan = plan_query(request)
                plan = apply_planning_decision(base_plan, response.decision)
                if not plan.retrieval_requests:
                    planning_errors[case.id] = "planner_returned_no_retrieval_queries"
                    continue
                planned[case.id] = plan
                saved_decisions[case.id] = {
                    "decision": response.decision.model_dump(mode="json"),
                    "decision_sha256": hashlib.sha256(
                        json.dumps(
                            response.decision.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    "query_plan_sha256": _plan_sha256(plan),
                }
            except ProviderError as exc:
                planning_errors[case.id] = exc.kind.value
        planning_events = recorder.events[planning_event_start:]

        raw_plans = {
            case.id: apply_planning_decision(
                plan_query(QueryRequest(question=case.question, history=case.history)),
                PlanningDecision(
                    relation=QueryRelation.GROUNDED_CANDIDATE,
                    retrieval_queries=[case.question],
                    explanation="Raw current-question retrieval baseline.",
                ),
            )
            for case in cases
        }
        original_a = RetrievalPipeline(
            chunks,
            vector_index=original_index,
            provider=recorder,
            config=original_config,
        )
        summary_a, rows_a = await _run_candidate(
            CANDIDATE_A,
            cases=cases,
            plans=raw_plans,
            planning_errors={},
            pipeline=original_a,
            recorder=recorder,
            chunks_by_id=chunks_by_id,
        )

        original_b = RetrievalPipeline(
            chunks,
            vector_index=original_index,
            provider=recorder,
            config=original_config,
        )
        summary_b, rows_b = await _run_candidate(
            CANDIDATE_B,
            cases=cases,
            plans=planned,
            planning_errors=planning_errors,
            pipeline=original_b,
            recorder=recorder,
            chunks_by_id=chunks_by_id,
        )

        index_event_start = len(recorder.events)
        index_error: str | None = None
        contextual_reused = False
        try:
            contextual_index, contextual_reused = await _load_or_build_experiment_index(
                chunks,
                corpus_version=corpus_version,
                config=contextual_config,
                provider=recorder,
            )
        except (IndexValidationError, ProviderError, OSError, RuntimeError) as exc:
            index_error = (
                exc.kind.value if isinstance(exc, ProviderError) else type(exc).__name__
            )
            contextual_index = None
        index_events = recorder.events[index_event_start:]

        if contextual_index is None:
            contextual_plans: dict[str, QueryPlan] = {}
            contextual_errors = {case.id: f"contextual_index:{index_error}" for case in cases}
            # Pipeline construction needs an index. Reuse the original only to
            # produce typed failure rows; search is skipped because plans are empty.
            contextual_pipeline = RetrievalPipeline(
                chunks,
                vector_index=original_index,
                provider=recorder,
                config=contextual_config,
            )
        else:
            contextual_plans = planned
            contextual_errors = planning_errors
            contextual_pipeline = RetrievalPipeline(
                chunks,
                vector_index=contextual_index,
                provider=recorder,
                config=contextual_config,
            )
        summary_c, rows_c = await _run_candidate(
            CANDIDATE_C,
            cases=cases,
            plans=contextual_plans,
            planning_errors=contextual_errors,
            pipeline=contextual_pipeline,
            recorder=recorder,
            chunks_by_id=chunks_by_id,
        )
    finally:
        if owned_provider:
            close = getattr(delegate, "aclose", None)
            if close is not None:
                await close()

    governed_after = _file_fingerprints(config)
    candidates = {
        CANDIDATE_A: summary_a,
        CANDIDATE_B: summary_b,
        CANDIDATE_C: summary_c,
    }
    all_provider_errors = [
        str(event["error_kind"]) for event in recorder.events if event["error_kind"]
    ]
    relations_match = len(saved_decisions) == len(cases) and all(
        planned[case.id].relation == case.expected_planning_relation for case in cases
    )
    safety_checks = {
        "development_grounded_cases_only": scope_valid,
        "holdout_opened": False,
        "governed_original_index_unchanged": governed_before == governed_after,
        "saved_planner_relations_match_labels": relations_match,
        "provider_error_count": len(all_provider_errors),
        "all_candidates_complete": all(summary["complete"] for summary in candidates.values()),
    }
    safety_passed = (
        all(
            bool(value)
            for key, value in safety_checks.items()
            if key not in {"holdout_opened", "provider_error_count"}
        )
        and not safety_checks["holdout_opened"]
        and safety_checks["provider_error_count"] == 0
    )
    selected, selection_reason = select_contextual_strategy(
        candidates, safety_passed=safety_passed
    )
    report = {
        "report_version": "firelens_contextual_retrieval_comparison.v1_1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": sha256_file(dataset_path),
        "split": "development",
        "case_filter": "expected_response_mode=grounded and acceptable_evidence present",
        "case_count": len(cases),
        "holdout_opened": False,
        "metric_definitions": {
            "bm25_recall_at_20": "Hit in any planned query's BM25 top 20.",
            "dense_recall_at_20": "Hit in any planned query's dense top 20.",
            "fused_recall_at_20": "Hit in the generalized-RRF top 20.",
            PRIMARY_METRIC: "Hit in the final reranker top 5.",
            "rerank_mrr_at_5": "Reciprocal rank of the first acceptable reranker hit.",
        },
        "configuration": {
            "bm25_top_k": original_config.bm25_top_k,
            "vector_top_k": original_config.vector_top_k,
            "fused_top_k": original_config.fused_top_k,
            "rrf_k": original_config.rrf_k,
            "rerank_top_k": original_config.rerank_top_k,
            "selection_baseline": CANDIDATE_B,
            "selection_candidate": CANDIDATE_C,
            "minimum_absolute_recall_gain": 0.02,
        },
        "planning": {
            **_event_summary(planning_events),
            "complete": not planning_errors and len(saved_decisions) == len(cases),
            "errors": planning_errors,
            "saved_decisions": saved_decisions,
        },
        "original_index": {
            "reused": original_reused,
            "matrix_path": str(original_config.vector_matrix_path),
            "manifest_path": str(original_config.vector_manifest_path),
            "embedding_cache_path": str(original_config.embedding_cache_path),
            **_event_summary(original_index_events),
        },
        "contextual_index": {
            "reused": contextual_reused,
            "error": index_error,
            "matrix_path": str(contextual_config.vector_matrix_path),
            "manifest_path": str(contextual_config.vector_manifest_path),
            "embedding_cache_path": str(contextual_config.embedding_cache_path),
            **_event_summary(index_events),
        },
        "candidates": candidates,
        "safety_checks": {**safety_checks, "passed": safety_passed},
        "provider_errors": all_provider_errors,
        "reported_cost_usd": sum(_usage_cost(event["usage"]) for event in recorder.events),
        "selected_retrieval_text_strategy": selected,
        "selection_reason": selection_reason,
        "details": {
            CANDIDATE_A: rows_a,
            CANDIDATE_B: rows_b,
            CANDIDATE_C: rows_c,
        },
    }
    with atomic_text_writer(output_path) as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report
