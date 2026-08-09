"""Development and sealed retrieval qualification recomputation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from firelens.benchmark import (
    _mean,
    _ranking_metrics,
    apply_relevance_addendum,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.evaluation.common import (
    ROOT,
)
from firelens.evaluation.common import (
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)
from firelens.evaluation.common import (
    strict_number as _strict_number,
)
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval_experiment import _candidate_summary


def _required_ranking_metric(row: dict[str, float | int | None], key: str) -> float:
    value = row[key]
    if value is None:
        raise ValueError(f"sealed retrieval ranking metric {key} is unavailable")
    return float(value)


def _ranking_context(
    dataset_path: Path,
    *,
    split: str,
    relevance_addendum_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = load_benchmark(dataset_path, require_release_shape=False)
    if relevance_addendum_path is not None:
        dataset = apply_relevance_addendum(
            dataset,
            load_relevance_addendum(
                relevance_addendum_path,
                dataset_path=dataset_path,
            ),
        )
    cases = {
        case.id: case
        for case in dataset.cases
        if case.split == split and case.acceptable_evidence
    }
    config = FireLensConfig.from_env(ROOT)
    chunks = {chunk.chunk_id: chunk for chunk in load_chunk_records(config.corpus_path)}
    return cases, chunks


def _recomputed_development_candidate(report: dict[str, Any]) -> dict[str, Any]:
    details = report.get("details")
    rows = details.get("current") if isinstance(details, dict) else None
    if not isinstance(rows, list):
        raise ValueError("development retrieval report has no current case-level rankings")
    cases, chunks = _ranking_context(
        ROOT / "data/evaluation/benchmark_v1.yaml",
        split="development",
        relevance_addendum_path=(
            ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml"
        ),
    )
    frozen_roster = list(cases)
    if report.get("development_case_roster") != frozen_roster:
        raise ValueError("development retrieval roster differs from the frozen dataset")
    observed_ids = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
    if len(rows) != len(cases) or len(observed_ids) != len(rows):
        raise ValueError("development retrieval case-level rankings are incomplete")
    if len(set(observed_ids)) != len(observed_ids) or observed_ids != frozen_roster:
        raise ValueError("development retrieval case IDs differ from the frozen dataset")
    normalized_rows: list[dict[str, Any]] = []
    expected_stages = {"bm25", "vector", "fused", "reranked"}
    for row in rows:
        case_id = str(row["id"])
        rankings = row.get("rankings")
        if not isinstance(rankings, dict) or set(rankings) != expected_stages:
            raise ValueError(f"development retrieval {case_id} has incomplete ranking IDs")
        recomputed_metrics: dict[str, Any] = {}
        for stage in sorted(expected_stages):
            chunk_ids = rankings[stage]
            if not isinstance(chunk_ids, list) or not all(
                isinstance(chunk_id, str) and chunk_id for chunk_id in chunk_ids
            ):
                raise ValueError(
                    f"development retrieval {case_id} has invalid {stage} ranking IDs"
                )
            if len(chunk_ids) != len(set(chunk_ids)):
                raise ValueError(f"development retrieval {case_id} repeats {stage} ranking IDs")
            if set(chunk_ids).difference(chunks):
                raise ValueError(
                    f"development retrieval {case_id} has unknown {stage} ranking IDs"
                )
            if stage == "reranked" and len(chunk_ids) > 5:
                raise ValueError("development reranked evidence exceeds frozen top five")
            recomputed_metrics[stage] = _ranking_metrics(chunk_ids, cases[case_id], chunks)
        if row.get("stage_metrics") != recomputed_metrics:
            raise ValueError(f"development retrieval {case_id} metrics differ from ranking IDs")
        _strict_bool(row, "retrieval_eligible", f"development retrieval {case_id}")
        _strict_bool(row, "complete", f"development retrieval {case_id}")
        _strict_number(
            row,
            "reported_cost_usd",
            f"development retrieval {case_id}",
            minimum=0,
        )
        normalized_rows.append({**row, "stage_metrics": recomputed_metrics})
    return _candidate_summary(normalized_rows)


def _development_retrieval(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"status": "not_run"}
    if report.get("report_version") != "firelens_retrieval_comparison.v2":
        raise ValueError("development retrieval report uses an unsupported report_version")
    if report.get("split") != "development" or report.get("holdout_opened") is not False:
        raise ValueError("development retrieval report must not open a holdout")
    candidates = report.get("candidates") or {}
    active = candidates.get("current")
    if (
        not isinstance(active, dict)
        or _strict_bool(active, "complete", "development retrieval current candidate")
        is not True
    ):
        raise ValueError("development retrieval report has no complete current candidate")
    case_count = _strict_int(
        active, "case_count", "development retrieval current candidate", minimum=0
    )
    if case_count != 50:
        raise ValueError("development retrieval report must use the fixed 50-case denominator")
    recomputed = _recomputed_development_candidate(report)
    for key in (
        "complete",
        "case_count",
        "retrieval_eligible_case_count",
        "reported_cost_usd",
        "stages",
        "route_eligible_stages",
    ):
        if active.get(key) != recomputed.get(key):
            raise ValueError(
                f"development retrieval current {key} differs from case-level rankings"
            )
    stages = active.get("stages") or {}
    reranked = stages.get("reranked")
    if not isinstance(reranked, dict):
        raise ValueError("development retrieval report has no reranked metrics")
    recall = _strict_number(reranked, "recall", "development retrieval", minimum=0, maximum=1)
    mrr = _strict_number(reranked, "mrr", "development retrieval", minimum=0, maximum=1)
    ndcg = _strict_number(reranked, "ndcg", "development retrieval", minimum=0, maximum=1)
    source_coverage = _strict_number(
        reranked,
        "mean_source_coverage",
        "development retrieval",
        minimum=0,
        maximum=1,
    )
    reported_cost = _strict_number(
        active,
        "reported_cost_usd",
        "development retrieval current candidate",
        minimum=0,
    )
    return {
        "status": "complete",
        "commit": report.get("commit"),
        "corpus_sha256": report.get("corpus_sha256"),
        "vector_matrix_sha256": report.get("vector_matrix_sha256"),
        "document_context_sha256": report.get("document_context_sha256"),
        "repairs_sha256": report.get("repairs_sha256"),
        "dataset_sha256": report.get("dataset_sha256"),
        "relevance_addendum_sha256": report.get("relevance_addendum_sha256"),
        "configuration": active.get("configuration") or report.get("active_configuration"),
        "case_count": case_count,
        "recall_at_5": recall,
        "mrr_at_5": mrr,
        "ndcg_at_5": ndcg,
        "mean_source_coverage": source_coverage,
        "reported_cost_usd": reported_cost,
    }


def _retrieval_qualification(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"status": "not_run"}
    if report.get("report_version") != "firelens_frozen_retrieval_qualification.v1":
        raise ValueError("sealed retrieval report uses an unsupported report_version")
    if (
        report.get("evaluation_role") != "sealed_release_qualification"
        or report.get("baseline_policy") != "required_after_only"
    ):
        raise ValueError("sealed retrieval report lacks explicit sealed-role metadata")
    if report.get("split") != "holdout":
        raise ValueError("sealed retrieval report must use the holdout split")
    if _strict_bool(report, "tuning_allowed", "sealed retrieval report"):
        raise ValueError("sealed retrieval report cannot allow tuning")
    if _strict_bool(report, "relevance_addendum_used", "sealed retrieval report"):
        raise ValueError("sealed retrieval report cannot use a relevance addendum")
    repetitions = report.get("repetition_reports") or []
    if not isinstance(repetitions, list):
        raise ValueError("sealed retrieval repetition_reports must be a list")
    declared_repetitions = _strict_int(
        report, "repetitions", "sealed retrieval report", minimum=0
    )
    if len(repetitions) != 3 or declared_repetitions != 3:
        raise ValueError("sealed retrieval report must contain exactly three repetitions")
    if (
        _strict_int(report, "case_count_per_repetition", "sealed retrieval report", minimum=0)
        != 47
    ):
        raise ValueError("sealed retrieval report must bind the 47-case denominator")
    cases, chunks = _ranking_context(
        ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
        split="holdout",
    )
    if len(cases) != 47:
        raise ValueError("frozen sealed retrieval dataset no longer has 47 answerable cases")
    recalls: list[float] = []
    ranking_sequences: list[list[list[str]]] = []
    recomputed_total_cost = 0.0
    for expected_repetition, item in enumerate(repetitions, start=1):
        if not isinstance(item, dict):
            raise ValueError("sealed retrieval repetition must be an object")
        if (
            _strict_int(item, "repetition", "sealed retrieval repetition", minimum=1)
            != expected_repetition
        ):
            raise ValueError("sealed retrieval repetitions must be ordered one through three")
        if _strict_int(item, "case_count", "sealed retrieval repetition", minimum=0) != 47:
            raise ValueError("sealed retrieval repetition must contain exactly 47 cases")
        rows = item.get("rows")
        if not isinstance(rows, list) or len(rows) != 47:
            raise ValueError("sealed retrieval repetition lacks 47 case-level rankings")
        observed_ids = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
        if len(observed_ids) != 47 or len(set(observed_ids)) != 47:
            raise ValueError("sealed retrieval repetition has invalid case IDs")
        if set(observed_ids) != set(cases):
            raise ValueError("sealed retrieval case IDs differ from the frozen dataset")
        row_metrics: list[dict[str, float | int | None]] = []
        repetition_rankings: list[list[str]] = []
        rows_complete = True
        for row in rows:
            case_id = str(row["id"])
            ranking = row.get("reranked_chunk_ids")
            if not isinstance(ranking, list) or not all(
                isinstance(chunk_id, str) and chunk_id for chunk_id in ranking
            ):
                raise ValueError(f"sealed retrieval {case_id} has invalid ranking IDs")
            if len(ranking) != len(set(ranking)):
                raise ValueError(f"sealed retrieval {case_id} repeats ranking IDs")
            if set(ranking).difference(chunks):
                raise ValueError(f"sealed retrieval {case_id} has unknown ranking IDs")
            if len(ranking) > 5:
                raise ValueError("sealed retrieval evidence exceeds frozen top five")
            recomputed = _ranking_metrics(ranking, cases[case_id], chunks)
            if row.get("metrics") != recomputed:
                raise ValueError(f"sealed retrieval {case_id} metrics differ from ranking IDs")
            rows_complete = rows_complete and _strict_bool(
                row, "complete", f"sealed retrieval {case_id}"
            )
            recomputed_total_cost += _strict_number(
                row,
                "reported_cost_usd",
                f"sealed retrieval {case_id}",
                minimum=0,
            )
            row_metrics.append(recomputed)
            repetition_rankings.append(ranking)
        computed_aggregates = {
            "recall_at_5": _mean(
                [_required_ranking_metric(value, "hit") for value in row_metrics]
            ),
            "mrr_at_5": _mean(
                [_required_ranking_metric(value, "reciprocal_rank") for value in row_metrics]
            ),
            "ndcg_at_5": _mean(
                [_required_ranking_metric(value, "ndcg") for value in row_metrics]
            ),
            "mean_source_coverage": _mean(
                [_required_ranking_metric(value, "source_coverage") for value in row_metrics]
            ),
        }
        if _strict_bool(item, "complete", "sealed retrieval repetition") != rows_complete:
            raise ValueError("sealed retrieval repetition completeness differs from its rows")
        if not rows_complete:
            raise ValueError("sealed retrieval report contains an incomplete repetition")
        for key, expected in computed_aggregates.items():
            declared = _strict_number(
                item,
                key,
                "sealed retrieval repetition",
                minimum=0,
                maximum=1,
            )
            if not math.isclose(declared, expected, rel_tol=0, abs_tol=1e-12):
                raise ValueError(
                    f"sealed retrieval repetition {key} differs from case-level rankings"
                )
        recalls.append(computed_aggregates["recall_at_5"])
        ranking_sequences.append(repetition_rankings)
    repeated_rankings_match = all(
        ranking == ranking_sequences[0] for ranking in ranking_sequences[1:]
    )
    if (
        _strict_bool(report, "repeated_rankings_match", "sealed retrieval report")
        != repeated_rankings_match
    ):
        raise ValueError("sealed retrieval repeated-ranking flag disagrees with its rows")
    qualified = _strict_bool(report, "qualified", "sealed retrieval report")
    owner_approved = _strict_bool(report, "owner_approved", "sealed retrieval report")
    if not owner_approved:
        raise ValueError("sealed retrieval ranking lacks required owner approval")
    if _strict_bool(report, "cost_budget_exceeded", "sealed retrieval report"):
        raise ValueError("sealed retrieval report exceeded its cost budget")
    cost_budget = _strict_number(
        report, "cost_budget_usd", "sealed retrieval report", minimum=0.000001
    )
    reported_cost = _strict_number(
        report, "reported_cost_usd", "sealed retrieval report", minimum=0
    )
    if not math.isclose(reported_cost, recomputed_total_cost, rel_tol=0, abs_tol=1e-12):
        raise ValueError("sealed retrieval cost differs from its case-level rows")
    if reported_cost > cost_budget:
        raise ValueError("sealed retrieval report cost exceeds its declared budget")
    expected_qualified = all(recall >= 46 / 47 for recall in recalls)
    if qualified != expected_qualified:
        raise ValueError("sealed retrieval qualification flag disagrees with its results")
    return {
        "status": "complete",
        "commit": report.get("commit"),
        "corpus_sha256": report.get("corpus_sha256"),
        "vector_matrix_sha256": report.get("vector_matrix_sha256"),
        "configuration_sha256": report.get("configuration_sha256"),
        "document_context_sha256": report.get("document_context_sha256"),
        "repairs_sha256": report.get("repairs_sha256"),
        "dataset_sha256": report.get("dataset_sha256"),
        "dataset_manifest_sha256": report.get("dataset_manifest_sha256"),
        "qualified": qualified,
        "owner_approved": owner_approved,
        "min_recall_at_5": min(recalls) if recalls else None,
        "mean_recall_at_5": sum(recalls) / len(recalls) if recalls else None,
        "reported_cost_usd": reported_cost,
        "repetitions": len(repetitions),
    }
