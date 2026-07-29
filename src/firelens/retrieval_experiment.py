"""Development-only comparison of bounded retrieval and query-intent policies."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.answering.intent import apply_planning_decision, plan_query
from firelens.benchmark import (
    BenchmarkCase,
    _mean,
    _ranking_metrics,
    _usage_cost,
    apply_relevance_addendum,
    file_sha256,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    PlanningDecision,
    QueryPlan,
    QueryRequest,
    QueryRoute,
    RetrievalBundle,
)
from firelens.runtime import load_runtime
from firelens.storage import atomic_text_writer

CURRENT_CONFIGURATION = {
    "bm25_top_k": 30,
    "vector_top_k": 30,
    "fused_top_k": 30,
    "rrf_k": 60,
    "rerank_top_k": 5,
}

RETRIEVAL_CANDIDATES: dict[str, dict[str, Any]] = {
    "current": {
        "configuration": CURRENT_CONFIGURATION,
        "preserve_original_question": False,
        "rerank_with_original_question": False,
    },
    "original_question_retrieval": {
        "configuration": CURRENT_CONFIGURATION,
        "preserve_original_question": True,
        "rerank_with_original_question": False,
    },
    "original_question_rerank": {
        "configuration": CURRENT_CONFIGURATION,
        "preserve_original_question": False,
        "rerank_with_original_question": True,
    },
    "user_intent_preserved": {
        "configuration": CURRENT_CONFIGURATION,
        "preserve_original_question": True,
        "rerank_with_original_question": True,
    },
}


def _candidate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = all(row["complete"] for row in rows)
    eligible_rows = [row for row in rows if row["retrieval_eligible"]]

    def summarize(selected_rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        stages: dict[str, dict[str, float]] = {}
        for stage in ("bm25", "vector", "fused", "reranked"):
            metrics = [row["stage_metrics"][stage] for row in selected_rows]
            stages[stage] = {
                "recall": _mean([float(item["hit"]) for item in metrics]),
                "mrr": _mean([float(item["reciprocal_rank"]) for item in metrics]),
                "ndcg": _mean([float(item["ndcg"]) for item in metrics]),
                "mean_source_coverage": _mean(
                    [float(item["source_coverage"]) for item in metrics]
                ),
            }
        return stages

    return {
        "complete": complete,
        "case_count": len(rows),
        "retrieval_eligible_case_count": len(eligible_rows),
        "reported_cost_usd": sum(float(row["reported_cost_usd"]) for row in rows),
        # Keep the legacy all-case view so intentional no-retrieval routes remain visible.
        "stages": summarize(rows),
        "route_eligible_stages": summarize(eligible_rows),
    }


def select_retrieval_candidate(summaries: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Require a material Recall@5 or MRR@5 gain without coverage loss."""

    current = summaries["current"]
    if not current["complete"]:
        return "current", "current configuration did not complete; no change is safe"
    current_rerank = current.get("route_eligible_stages", current["stages"])["reranked"]
    eligible: list[tuple[float, float, float, str]] = []
    for name, summary in summaries.items():
        if name == "current" or not summary["complete"]:
            continue
        rerank = summary.get("route_eligible_stages", summary["stages"])["reranked"]
        recall_gain = rerank["recall"] >= current_rerank["recall"] + 0.02
        mrr_gain = (
            rerank["recall"] >= current_rerank["recall"]
            and rerank["mrr"] >= current_rerank["mrr"] + 0.03
        )
        if (
            rerank["recall"] >= 0.96
            and (recall_gain or mrr_gain)
            and rerank["mean_source_coverage"] >= current_rerank["mean_source_coverage"]
            and rerank["mrr"] >= current_rerank["mrr"] - 0.02
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
        return "current", "no candidate cleared the locked Recall@5 or MRR@5 gain rule"
    selected = max(eligible)[-1]
    return selected, (
        "candidate cleared 96% route-eligible Recall@5, a material Recall@5 or MRR@5 "
        "gain, and source-coverage rules"
    )


def _candidate_row(
    case: BenchmarkCase,
    *,
    plan: QueryPlan,
    bundle: RetrievalBundle,
    chunks_by_id: dict[str, Any],
) -> dict[str, Any]:
    rankings = {
        "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
        "vector": [hit.chunk_id for hit in bundle.vector_hits],
        "fused": [hit.chunk_id for hit in bundle.fused_hits],
        "reranked": [hit.chunk_id for hit in bundle.reranked_hits[:5]],
    }
    return {
        "id": case.id,
        "retrieval_eligible": bool(plan.retrieval_requests),
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
        "reported_cost_usd": _usage_cost(bundle.provider_usage),
    }


async def run_retrieval_comparison(
    config: FireLensConfig,
    *,
    dataset_path: Path,
    output_path: Path,
    relevance_addendum_path: Path | None = None,
    max_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Compare only development cases; sealed holdout labels are never opened here."""

    dataset = load_benchmark(dataset_path)
    relevance_addendum = None
    if relevance_addendum_path is not None:
        relevance_addendum = load_relevance_addendum(
            relevance_addendum_path, dataset_path=dataset_path
        )
        dataset = apply_relevance_addendum(dataset, relevance_addendum)
    cases: list[BenchmarkCase] = [
        case
        for case in dataset.cases
        if case.split == "development" and case.acceptable_evidence
    ]
    summaries: dict[str, dict[str, Any]] = {}
    details: dict[str, list[dict[str, Any]]] = {}
    total_cost = 0.0
    saved: dict[
        str,
        tuple[QueryRequest, QueryPlan, PlanningDecision | None, RetrievalBundle],
    ] = {}

    baseline_runtime = load_runtime(config.model_copy(update=CURRENT_CONFIGURATION))
    try:
        if baseline_runtime.service is None:
            raise RuntimeError(f"Runtime is not ready for current: {baseline_runtime.problems}")
        chunks_by_id = baseline_runtime.chunks_by_id
        current_rows: list[dict[str, Any]] = []
        for case in cases:
            if max_cost_usd is not None and total_cost >= max_cost_usd:
                break
            request = QueryRequest(question=case.question)
            execution = await baseline_runtime.service.execute_search(request)
            baseline_plan = execution.public_response.plan
            baseline_bundle = execution.observation.retrieval
            saved[case.id] = (
                request,
                baseline_plan,
                (
                    execution.observation.planning.decision
                    if execution.observation.planning is not None
                    else None
                ),
                baseline_bundle,
            )
            row = _candidate_row(
                case,
                plan=baseline_plan,
                bundle=baseline_bundle,
                chunks_by_id=chunks_by_id,
            )
            total_cost += float(row["reported_cost_usd"])
            current_rows.append(row)
    finally:
        await baseline_runtime.aclose()
    summaries["current"] = _candidate_summary(current_rows)
    details["current"] = current_rows

    for candidate_name, candidate in RETRIEVAL_CANDIDATES.items():
        if candidate_name == "current":
            continue
        rows: list[dict[str, Any]] = []
        runtime = load_runtime(config.model_copy(update=candidate["configuration"]))
        try:
            if runtime.service is None:
                raise RuntimeError(
                    f"Runtime is not ready for {candidate_name}: {runtime.problems}"
                )
            chunks_by_id = runtime.chunks_by_id
            for case in cases:
                if max_cost_usd is not None and total_cost >= max_cost_usd:
                    break
                request, baseline_plan, decision, baseline_bundle = saved[case.id]
                if decision is None:
                    plan = baseline_plan
                    bundle = baseline_bundle
                else:
                    plan = apply_planning_decision(
                        plan_query(request),
                        decision,
                        preserve_original_question=bool(
                            candidate["preserve_original_question"]
                        ),
                        rerank_with_original_question=bool(
                            candidate["rerank_with_original_question"]
                        ),
                    )
                    bundle = (
                        await runtime.service.retrieval.search(plan)
                        if plan.route == QueryRoute.RELATED and plan.retrieval_requests
                        else RetrievalBundle()
                    )
                row = _candidate_row(
                    case,
                    plan=plan,
                    bundle=bundle,
                    chunks_by_id=chunks_by_id,
                )
                total_cost += float(row["reported_cost_usd"])
                rows.append(row)
        finally:
            await runtime.aclose()
        summaries[candidate_name] = _candidate_summary(rows)
        details[candidate_name] = rows

    selected, reason = select_retrieval_candidate(summaries)
    report = {
        "report_version": "firelens_retrieval_comparison.v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": file_sha256(dataset_path),
        "relevance_addendum_sha256": (
            file_sha256(relevance_addendum_path)
            if relevance_addendum_path is not None
            else None
        ),
        "relevance_review_status": (
            relevance_addendum.review_status if relevance_addendum is not None else None
        ),
        "split": "development",
        "holdout_opened": False,
        "case_count_per_complete_candidate": len(cases),
        "cost_budget_usd": max_cost_usd,
        "reported_cost_usd": total_cost,
        "planner_decisions_reused_across_candidates": True,
        "candidates": {
            name: {**RETRIEVAL_CANDIDATES[name], **summary}
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
