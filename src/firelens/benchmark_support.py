"""Shared runtime identity, ranking, usage, and provider-stage benchmark metrics."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, cast

from firelens.answering.service import AskExecution
from firelens.benchmark_contracts import (
    BenchmarkCase,
    ConversationBenchmarkCase,
    GoldEvidence,
    PaidProviderStage,
    file_sha256,
)
from firelens.config import FireLensConfig
from firelens.contracts import QueryRoute
from firelens.git_identity import clean_checkout_commit
from firelens.ingestion.chunking import ChunkRecord
from firelens.runtime import Runtime


def benchmark_runtime_configuration(config: FireLensConfig) -> dict[str, Any]:
    """Return the non-secret settings that can change benchmark behaviour."""

    return {
        "embedding_model": config.embedding_model,
        "retrieval_text_strategy": config.retrieval_text_strategy.value,
        "rerank_model": config.rerank_model,
        "generation_model": config.generation_model,
        "generation_temperature": config.generation_temperature,
        "bm25_top_k": config.bm25_top_k,
        "vector_top_k": config.vector_top_k,
        "fused_top_k": config.fused_top_k,
        "rrf_k": config.rrf_k,
        "rerank_top_k": config.rerank_top_k,
        "neighbor_window": config.neighbor_window,
        "max_evidence_spans": config.max_evidence_spans,
        "max_context_chars": config.max_context_chars,
        "request_timeout_seconds": config.request_timeout_seconds,
        "public_request_deadline_seconds": config.public_request_deadline_seconds,
        "provider_max_attempts": config.provider_max_attempts,
        "provider_retry_base_seconds": config.provider_retry_base_seconds,
        "provider_max_concurrency": config.provider_max_concurrency,
        "provider_adaptive_min_concurrency": config.provider_adaptive_min_concurrency,
        "provider_adaptive_success_window": config.provider_adaptive_success_window,
        "provider_circuit_failure_threshold": config.provider_circuit_failure_threshold,
        "provider_circuit_cooldown_seconds": config.provider_circuit_cooldown_seconds,
        "embedding_batch_size": config.embedding_batch_size,
        "query_embedding_cache_size": config.query_embedding_cache_size,
        "require_parameters": config.privacy.require_parameters,
        "embedding_zdr": config.privacy.embedding_zdr,
        "reranking_zdr": config.privacy.reranking_zdr,
        "generation_zdr": config.privacy.generation_zdr,
        "data_collection": config.privacy.data_collection,
        "allow_fallbacks": config.privacy.allow_fallbacks,
    }


def _current_commit(config: FireLensConfig) -> str | None:
    """Prefer a clean measured checkout, falling back outside Git only."""

    return clean_checkout_commit(
        config.project_root,
        context="benchmark runtime identity",
        fallback=config.build_commit,
    )


def benchmark_runtime_identity(runtime: Runtime) -> dict[str, Any]:
    """Hash-bind a report to the measured code, corpus, index, and configuration."""

    configuration = benchmark_runtime_configuration(runtime.config)
    configuration_json = json.dumps(
        configuration,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "commit": _current_commit(runtime.config),
        "corpus_sha256": file_sha256(runtime.config.corpus_path),
        "corpus_manifest_sha256": file_sha256(runtime.config.corpus_manifest_path),
        "vector_matrix_sha256": file_sha256(runtime.config.vector_matrix_path),
        "vector_manifest_sha256": file_sha256(runtime.config.vector_manifest_path),
        "document_context_sha256": (
            file_sha256(runtime.config.document_context_path)
            if runtime.config.document_context_path.is_file()
            else None
        ),
        "repairs_sha256": file_sha256(
            runtime.config.project_root / "data/repairs/text_overrides.yaml"
        ),
        "configuration_sha256": hashlib.sha256(configuration_json.encode("utf-8")).hexdigest(),
        "runtime_configuration": configuration,
    }


def _matches(chunk: ChunkRecord, evidence: GoldEvidence) -> bool:
    if chunk.source_id != evidence.source_id:
        return False
    if evidence.chunk_ids and chunk.chunk_id not in evidence.chunk_ids:
        return False
    return not evidence.pages or chunk.page_number in evidence.pages


def ranking_metrics(
    chunk_ids: list[str],
    case: BenchmarkCase | ConversationBenchmarkCase,
    chunks_by_id: Mapping[str, ChunkRecord],
) -> dict[str, float | int | None]:
    relevant = [
        index
        for index, chunk_id in enumerate(chunk_ids, start=1)
        if chunk_id in chunks_by_id
        and any(_matches(chunks_by_id[chunk_id], item) for item in case.acceptable_evidence)
    ]
    first_rank = min(relevant) if relevant else None
    dcg = sum(1 / math.log2(rank + 1) for rank in relevant)
    ideal_count = min(len(relevant), len(chunk_ids))
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    expected_sources = {item.source_id for item in case.acceptable_evidence}
    hit_sources = {
        chunks_by_id[chunk_id].source_id
        for chunk_id in chunk_ids
        if chunk_id in chunks_by_id
        and any(_matches(chunks_by_id[chunk_id], item) for item in case.acceptable_evidence)
    }
    return {
        "hit": int(bool(relevant)),
        "first_rank": first_rank,
        "reciprocal_rank": 0.0 if first_rank is None else 1 / first_rank,
        "ndcg": 0.0 if ideal == 0 else dcg / ideal,
        "source_coverage": len(hit_sources) / len(expected_sources)
        if expected_sources
        else 0.0,
    }


def mean(rows: list[float]) -> float:
    return sum(rows) / len(rows) if rows else 0.0


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile_value * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def precision_recall(
    rows: list[dict[str, Any]], *, expected_key: str, actual_key: str, positive: str
) -> dict[str, float]:
    true_positive = sum(
        row[expected_key] == positive and row[actual_key] == positive for row in rows
    )
    predicted_positive = sum(row[actual_key] == positive for row in rows)
    expected_positive = sum(row[expected_key] == positive for row in rows)
    return {
        "precision": true_positive / predicted_positive if predicted_positive else 0.0,
        "recall": true_positive / expected_positive if expected_positive else 0.0,
    }


def usage_total(value: object, field: str) -> int:
    if isinstance(value, dict):
        own = value.get(field)
        total = int(own) if isinstance(own, int) else 0
        return total + sum(
            usage_total(child, field) for key, child in value.items() if key != field
        )
    if isinstance(value, list):
        return sum(usage_total(item, field) for item in value)
    return 0


def usage_cost(value: object) -> float:
    if isinstance(value, dict):
        own = value.get("cost")
        total = float(own) if isinstance(own, (int, float)) else 0.0
        return total + sum(usage_cost(child) for key, child in value.items() if key != "cost")
    if isinstance(value, list):
        return sum(usage_cost(item) for item in value)
    return 0.0


def stage_rankings(execution: AskExecution) -> dict[str, list[str]]:
    bundle = execution.retrieval
    return {
        "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
        "vector": [hit.chunk_id for hit in bundle.vector_hits],
        "fused": [hit.chunk_id for hit in bundle.fused_hits],
        "reranked": [hit.chunk_id for hit in bundle.reranked_hits],
    }


def execution_provider_data(
    execution: AskExecution,
) -> tuple[
    list[PaidProviderStage],
    dict[str, list[dict[str, Any]]],
    dict[str, list[int]],
    dict[str, list[str]],
]:
    """Normalize typed stage observations into report-friendly mappings."""

    stages: list[PaidProviderStage] = []
    usage: dict[str, list[dict[str, Any]]] = {}
    attempts: dict[str, list[int]] = {}
    models: dict[str, list[str]] = {}
    bundle = execution.retrieval
    stage_names = {"embedding": "embeddings", "rerank": "reranker"}
    if execution.plan.route in {QueryRoute.RELATED, QueryRoute.TANGENT}:
        stages.append("planner")
    planning = execution.search.observation.planning
    if planning is not None:
        usage["planner"] = [planning.usage]
        attempts["planner"] = [planning.attempts]
        models["planner"] = [planning.model]
    for internal_name, public_name in stage_names.items():
        stage = cast(PaidProviderStage, public_name)
        if internal_name in bundle.provider_models and stage not in stages:
            stages.append(stage)
        if (stage_usage := bundle.provider_usage.get(internal_name)) is not None:
            usage[stage] = [stage_usage]
        if (stage_attempts := bundle.provider_attempts.get(internal_name)) is not None:
            attempts[stage] = [stage_attempts]
        if (stage_model := bundle.provider_models.get(internal_name)) is not None:
            models[stage] = [stage_model]
    for generation in execution.generations:
        stage = cast(PaidProviderStage, generation.stage)
        if stage not in stages:
            stages.append(stage)
        usage.setdefault(stage, []).append(generation.usage)
        attempts.setdefault(stage, []).append(generation.attempts)
        if generation.model is not None:
            models.setdefault(stage, []).append(generation.model)
    return stages, usage, attempts, models
