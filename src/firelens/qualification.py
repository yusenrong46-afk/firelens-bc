"""Frozen, no-tuning retrieval qualification for the V1 holdout split."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from firelens.benchmark import (
    _mean,
    _ranking_metrics,
    _usage_cost,
    _usage_total,
    file_sha256,
    load_benchmark,
)
from firelens.contracts import QueryRequest
from firelens.retrieval_review import validate_retrieval_owner_review
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer


def _holdout_sha256(cases: list[dict[str, Any]]) -> str:
    """Reproduce the V1 manifest's compact ordered holdout-list hash."""

    encoded = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


async def run_frozen_retrieval_qualification(
    runtime: Runtime,
    *,
    dataset_path: Path,
    dataset_manifest_path: Path,
    output_path: Path,
    owner_review_path: Path | None = None,
    repetitions: int = 3,
    max_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Measure a frozen configuration repeatedly without selecting or tuning it."""

    if runtime.service is None:
        raise RuntimeError("FireLens runtime is not ready")
    if repetitions < 1 or repetitions > 5:
        raise ValueError("repetitions must be between one and five")

    dataset = load_benchmark(dataset_path, require_release_shape=False)
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    raw_dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    if dataset_manifest.get("dataset_version") != raw_dataset.get("dataset_version"):
        raise ValueError("V1 qualification manifest dataset version does not match")
    if dataset_manifest.get("dataset_sha256") != file_sha256(dataset_path):
        raise ValueError("V1 qualification manifest does not match the benchmark dataset")
    holdout_payloads = [case for case in raw_dataset["cases"] if case.get("split") == "holdout"]
    if dataset_manifest.get("holdout_case_count") != len(holdout_payloads):
        raise ValueError("V1 qualification manifest holdout count does not match")
    holdout_sha256 = _holdout_sha256(holdout_payloads)
    if dataset_manifest.get("holdout_sha256") != holdout_sha256:
        raise ValueError("V1 holdout hash does not match the frozen manifest")

    cases = [
        case for case in dataset.cases if case.split == "holdout" and case.acceptable_evidence
    ]
    declared_answerable_count = dataset_manifest.get("answerable_holdout_case_count")
    if declared_answerable_count is not None and declared_answerable_count != len(cases):
        raise ValueError("V1 qualification manifest answerable holdout count does not match")
    if (
        str(raw_dataset.get("dataset_version", "")).startswith("firelens_v1_5_sealed_retrieval")
        and dataset_manifest.get("configuration_frozen_before_dataset") is not True
    ):
        raise ValueError("V1.5 sealed retrieval manifest must freeze configuration first")
    chunks_by_id = runtime.chunks_by_id
    reported_cost_usd = 0.0
    budget_exceeded = False
    repetition_reports: list[dict[str, Any]] = []

    for repetition in range(1, repetitions + 1):
        rows: list[dict[str, Any]] = []
        for case in cases:
            if max_cost_usd is not None and reported_cost_usd >= max_cost_usd:
                budget_exceeded = True
                break
            started = perf_counter()
            response = await runtime.service.search(QueryRequest(question=case.question))
            bundle = response.retrieval
            ranking = [hit.chunk_id for hit in bundle.reranked_hits[:5]]
            metrics = _ranking_metrics(ranking, case, chunks_by_id)
            cost = _usage_cost(bundle.provider_usage)
            reported_cost_usd += cost
            rows.append(
                {
                    "id": case.id,
                    "complete": bundle.complete,
                    "retrieval_eligible": bool(response.plan.retrieval_requests),
                    "reranked_chunk_ids": ranking,
                    "metrics": metrics,
                    "provider_models": bundle.provider_models,
                    "provider_attempts": bundle.provider_attempts,
                    "provider_tokens": {
                        name: _usage_total(bundle.provider_usage, name)
                        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
                    },
                    "reported_cost_usd": cost,
                    "latency_ms": (perf_counter() - started) * 1_000,
                    "errors": bundle.errors,
                }
            )
        repetition_reports.append(
            {
                "repetition": repetition,
                "complete": len(rows) == len(cases) and all(row["complete"] for row in rows),
                "case_count": len(rows),
                "recall_at_5": _mean([float(row["metrics"]["hit"]) for row in rows]),
                "mrr_at_5": _mean([float(row["metrics"]["reciprocal_rank"]) for row in rows]),
                "ndcg_at_5": _mean([float(row["metrics"]["ndcg"]) for row in rows]),
                "mean_source_coverage": _mean(
                    [float(row["metrics"]["source_coverage"]) for row in rows]
                ),
                "p95_latency_ms": sorted(float(row["latency_ms"]) for row in rows)[
                    max(0, int(0.95 * len(rows)) - 1)
                ]
                if rows
                else 0.0,
                "rows": rows,
            }
        )

    repeated_rankings_match = bool(repetition_reports) and all(
        [row["reranked_chunk_ids"] for row in report["rows"]]
        == [row["reranked_chunk_ids"] for row in repetition_reports[0]["rows"]]
        for report in repetition_reports[1:]
    )
    owner_review = (
        validate_retrieval_owner_review(dataset_path, owner_review_path)
        if owner_review_path is not None and owner_review_path.exists()
        else None
    )
    owner_approved = bool(owner_review and owner_review["qualified"])
    requested_gate_compatible = len(cases) == 47
    report = {
        "report_version": "firelens_frozen_retrieval_qualification.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": runtime.config.build_commit,
        "dataset_sha256": file_sha256(dataset_path),
        "dataset_manifest_sha256": file_sha256(dataset_manifest_path),
        "holdout_sha256": holdout_sha256,
        "split": "holdout",
        "tuning_allowed": False,
        "relevance_addendum_used": False,
        "adjudication_statuses": sorted({case.adjudication_status for case in cases}),
        "owner_approved": owner_approved,
        "owner_review": owner_review,
        "case_count_per_repetition": len(cases),
        "repetitions": repetitions,
        "configuration": {
            "bm25_top_k": runtime.config.bm25_top_k,
            "vector_top_k": runtime.config.vector_top_k,
            "fused_top_k": runtime.config.fused_top_k,
            "rrf_k": runtime.config.rrf_k,
            "rerank_top_k": runtime.config.rerank_top_k,
            "retrieval_text_strategy": runtime.config.retrieval_text_strategy.value,
        },
        "cost_budget_usd": max_cost_usd,
        "cost_budget_exceeded": budget_exceeded,
        "reported_cost_usd": reported_cost_usd,
        "repeated_rankings_match": repeated_rankings_match,
        "requested_46_of_47_gate_compatible": requested_gate_compatible,
        "qualified": bool(
            owner_approved
            and requested_gate_compatible
            and not budget_exceeded
            and all(item["complete"] for item in repetition_reports)
            and all(item["recall_at_5"] >= 46 / 47 for item in repetition_reports)
        ),
        "qualification_limitations": [
            *(
                []
                if owner_approved
                else [
                    "The sealed retrieval labels do not have a complete hash-bound owner approval."
                ]
            ),
            *(
                []
                if requested_gate_compatible
                else [
                    f"The frozen holdout contains {len(cases)} retrieval-answerable cases, "
                    "so it cannot prove the requested 46/47 gate."
                ]
            ),
        ],
        "repetition_reports": repetition_reports,
    }
    with atomic_text_writer(output_path) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return report
