"""Development-only comparison of the four locked V1 retrieval configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.benchmark import (
    BenchmarkCase,
    _mean,
    _ranking_metrics,
    _usage_cost,
    file_sha256,
    load_benchmark,
)
from firelens.config import FireLensConfig
from firelens.contracts import QueryRequest
from firelens.runtime import load_runtime
from firelens.storage import atomic_text_writer

RETRIEVAL_CANDIDATES: dict[str, dict[str, int]] = {
    "current": {
        "bm25_top_k": 20,
        "vector_top_k": 20,
        "fused_top_k": 20,
        "rrf_k": 60,
        "rerank_top_k": 5,
    },
    "broader_recall": {
        "bm25_top_k": 30,
        "vector_top_k": 30,
        "fused_top_k": 30,
        "rrf_k": 60,
        "rerank_top_k": 5,
    },
    "rank_sensitive": {
        "bm25_top_k": 20,
        "vector_top_k": 20,
        "fused_top_k": 20,
        "rrf_k": 30,
        "rerank_top_k": 5,
    },
    "wider_evidence": {
        "bm25_top_k": 20,
        "vector_top_k": 20,
        "fused_top_k": 20,
        "rrf_k": 60,
        "rerank_top_k": 8,
    },
}


def _candidate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = all(row["complete"] for row in rows)
    stages: dict[str, dict[str, float]] = {}
    for stage in ("bm25", "vector", "fused", "reranked"):
        metrics = [row["stage_metrics"][stage] for row in rows]
        stages[stage] = {
            "recall": _mean([float(item["hit"]) for item in metrics]),
            "mrr": _mean([float(item["reciprocal_rank"]) for item in metrics]),
            "ndcg": _mean([float(item["ndcg"]) for item in metrics]),
            "mean_source_coverage": _mean([float(item["source_coverage"]) for item in metrics]),
        }
    return {
        "complete": complete,
        "case_count": len(rows),
        "reported_cost_usd": sum(float(row["reported_cost_usd"]) for row in rows),
        "stages": stages,
    }


def select_retrieval_candidate(summaries: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Require a two-point Recall@5 gain without losing source coverage."""

    current = summaries["current"]
    if not current["complete"]:
        return "current", "current configuration did not complete; no change is safe"
    current_rerank = current["stages"]["reranked"]
    eligible: list[tuple[float, float, float, str]] = []
    for name, summary in summaries.items():
        if name == "current" or not summary["complete"]:
            continue
        rerank = summary["stages"]["reranked"]
        if (
            rerank["recall"] >= current_rerank["recall"] + 0.02
            and rerank["mean_source_coverage"] >= current_rerank["mean_source_coverage"]
        ):
            eligible.append(
                (
                    float(rerank["recall"]),
                    float(rerank["ndcg"]),
                    float(rerank["mrr"]),
                    name,
                )
            )
    if not eligible:
        return "current", "no candidate cleared the locked two-point safety rule"
    selected = max(eligible)[-1]
    return selected, "candidate cleared the locked Recall@5 and source-coverage rule"


async def run_retrieval_comparison(
    config: FireLensConfig,
    *,
    dataset_path: Path,
    output_path: Path,
    max_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Compare only development cases; sealed holdout labels are never opened here."""

    dataset = load_benchmark(dataset_path)
    cases: list[BenchmarkCase] = [
        case
        for case in dataset.cases
        if case.split == "development" and case.acceptable_evidence
    ]
    summaries: dict[str, dict[str, Any]] = {}
    details: dict[str, list[dict[str, Any]]] = {}
    total_cost = 0.0

    for candidate_name, updates in RETRIEVAL_CANDIDATES.items():
        rows: list[dict[str, Any]] = []
        runtime = load_runtime(config.model_copy(update=updates))
        try:
            if runtime.service is None:
                raise RuntimeError(
                    f"Runtime is not ready for {candidate_name}: {runtime.problems}"
                )
            chunks_by_id = runtime.chunks_by_id
            for case in cases:
                if max_cost_usd is not None and total_cost >= max_cost_usd:
                    break
                response = await runtime.service.search(QueryRequest(question=case.question))
                bundle = response.retrieval
                rankings = {
                    "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
                    "vector": [hit.chunk_id for hit in bundle.vector_hits],
                    "fused": [hit.chunk_id for hit in bundle.fused_hits],
                    # The release gate is explicitly Recall@5 even when a candidate
                    # exposes eight passages to context construction.
                    "reranked": [hit.chunk_id for hit in bundle.reranked_hits[:5]],
                }
                usage_cost = _usage_cost(bundle.provider_usage)
                total_cost += usage_cost
                rows.append(
                    {
                        "id": case.id,
                        "complete": bundle.complete,
                        "errors": bundle.errors,
                        "stage_metrics": {
                            stage: _ranking_metrics(chunk_ids, case, chunks_by_id)
                            for stage, chunk_ids in rankings.items()
                        },
                        "context_candidate_metrics": _ranking_metrics(
                            [hit.chunk_id for hit in bundle.reranked_hits],
                            case,
                            chunks_by_id,
                        ),
                        "reported_cost_usd": usage_cost,
                    }
                )
        finally:
            await runtime.aclose()
        summaries[candidate_name] = _candidate_summary(rows)
        details[candidate_name] = rows

    selected, reason = select_retrieval_candidate(summaries)
    report = {
        "report_version": "firelens_retrieval_comparison.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": file_sha256(dataset_path),
        "split": "development",
        "holdout_opened": False,
        "case_count_per_complete_candidate": len(cases),
        "cost_budget_usd": max_cost_usd,
        "reported_cost_usd": total_cost,
        "candidates": {
            name: {"configuration": RETRIEVAL_CANDIDATES[name], **summary}
            for name, summary in summaries.items()
        },
        "selected": selected,
        "selection_reason": reason,
        "details": details,
    }
    with atomic_text_writer(output_path) as stream:
        import json

        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report
