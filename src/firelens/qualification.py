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
    benchmark_runtime_identity,
    file_sha256,
    load_benchmark,
)
from firelens.contracts import QueryRequest
from firelens.retrieval_review import validate_retrieval_owner_review
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer


def _holdout_sha256(cases: list[dict[str, Any]]) -> str:
    encoded = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _validate_sealed_manifest(manifest: dict[str, Any]) -> None:
    checks = (
        (
            manifest.get("configuration_frozen_before_dataset") is True,
            "sealed retrieval manifest must freeze configuration first",
        ),
        (
            manifest.get("baseline_policy") == "required_after_only",
            "sealed retrieval manifest must be required-after-only",
        ),
        (
            manifest.get("owner_review_required_before_ranking") is True,
            "sealed retrieval manifest must require owner review",
        ),
        (
            manifest.get("required_repetitions") == 3,
            "sealed retrieval manifest must require exactly 3 repetitions",
        ),
    )
    for passed, message in checks:
        if not passed:
            raise ValueError(message)


def _validated_qualification_inputs(
    dataset_path: Path, manifest_path: Path
) -> tuple[dict[str, Any], list[Any], bool, str]:
    dataset = load_benchmark(dataset_path, require_release_shape=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_version") != raw.get("dataset_version"):
        raise ValueError("V1 qualification manifest dataset version does not match")
    if manifest.get("dataset_sha256") != file_sha256(dataset_path):
        raise ValueError("V1 qualification manifest does not match the benchmark dataset")
    payloads = [case for case in raw["cases"] if case.get("split") == "holdout"]
    if manifest.get("holdout_case_count") != len(payloads):
        raise ValueError("V1 qualification manifest holdout count does not match")
    holdout_sha256 = _holdout_sha256(payloads)
    if manifest.get("holdout_sha256") != holdout_sha256:
        raise ValueError("V1 holdout hash does not match the frozen manifest")
    cases = [
        case for case in dataset.cases if case.split == "holdout" and case.acceptable_evidence
    ]
    declared = manifest.get("answerable_holdout_case_count")
    if declared is not None and declared != len(cases):
        raise ValueError("V1 qualification manifest answerable holdout count does not match")
    is_sealed = manifest.get("evaluation_role") == "sealed_release_qualification"
    if is_sealed:
        _validate_sealed_manifest(manifest)
    return manifest, cases, is_sealed, holdout_sha256


async def _run_retrieval_repetition(
    runtime: Runtime,
    cases: list[Any],
    *,
    max_cost_usd: float | None,
    spent: float,
) -> tuple[list[dict[str, Any]], float, bool]:
    rows: list[dict[str, Any]] = []
    cost_total = 0.0
    exceeded = False
    assert runtime.service is not None
    for case in cases:
        if max_cost_usd is not None and spent + cost_total >= max_cost_usd:
            return rows, cost_total, True
        started = perf_counter()
        response = await runtime.service.search(QueryRequest(question=case.question))
        bundle = response.retrieval
        ranking = [hit.chunk_id for hit in bundle.reranked_hits[:5]]
        cost = _usage_cost(bundle.provider_usage)
        cost_total += cost
        exceeded = exceeded or (max_cost_usd is not None and spent + cost_total > max_cost_usd)
        rows.append(
            {
                "id": case.id,
                "complete": bundle.complete,
                "retrieval_eligible": bool(response.plan.retrieval_requests),
                "reranked_chunk_ids": ranking,
                "metrics": _ranking_metrics(ranking, case, runtime.chunks_by_id),
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
    return rows, cost_total, exceeded


def _repetition_report(
    repetition: int, rows: list[dict[str, Any]], case_count: int
) -> dict[str, Any]:
    return {
        "repetition": repetition,
        "complete": len(rows) == case_count and all(row["complete"] for row in rows),
        "case_count": len(rows),
        "recall_at_5": _mean([float(row["metrics"]["hit"]) for row in rows]),
        "mrr_at_5": _mean([float(row["metrics"]["reciprocal_rank"]) for row in rows]),
        "ndcg_at_5": _mean([float(row["metrics"]["ndcg"]) for row in rows]),
        "mean_source_coverage": _mean(
            [float(row["metrics"]["source_coverage"]) for row in rows]
        ),
        "p95_latency_ms": (
            sorted(float(row["latency_ms"]) for row in rows)[max(0, int(0.95 * len(rows)) - 1)]
            if rows
            else 0.0
        ),
        "rows": rows,
    }


def _qualification_limitations(
    *, is_sealed: bool, owner_approved: bool, gate_compatible: bool, case_count: int
) -> list[str]:
    limitations = (
        []
        if is_sealed
        else ["This dataset is permanent regression data and cannot qualify a release."]
    )
    if not owner_approved:
        limitations.append(
            "The sealed retrieval labels do not have a complete hash-bound owner approval."
        )
    if not gate_compatible:
        limitations.append(
            f"The frozen holdout contains {case_count} retrieval-answerable cases, so it cannot prove the requested 46/47 gate."
        )
    return limitations


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
    manifest, cases, is_sealed, holdout_sha256 = _validated_qualification_inputs(
        dataset_path, dataset_manifest_path
    )
    owner_review = (
        validate_retrieval_owner_review(dataset_path, owner_review_path)
        if owner_review_path is not None and owner_review_path.exists()
        else None
    )
    owner_approved = bool(owner_review and owner_review["qualified"])
    if is_sealed and repetitions != 3:
        raise ValueError("sealed retrieval qualification requires exactly 3 repetitions")
    if is_sealed and not owner_approved:
        raise PermissionError(
            "sealed retrieval ranking requires a complete hash-bound owner review"
        )
    reports: list[dict[str, Any]] = []
    spent = 0.0
    budget_exceeded = False
    for repetition in range(1, repetitions + 1):
        rows, cost, exceeded = await _run_retrieval_repetition(
            runtime, cases, max_cost_usd=max_cost_usd, spent=spent
        )
        spent += cost
        budget_exceeded = budget_exceeded or exceeded
        reports.append(_repetition_report(repetition, rows, len(cases)))
    rankings_match = bool(reports) and all(
        [row["reranked_chunk_ids"] for row in report["rows"]]
        == [row["reranked_chunk_ids"] for row in reports[0]["rows"]]
        for report in reports[1:]
    )
    gate_compatible = is_sealed and len(cases) == 47
    report = {
        "report_version": "firelens_frozen_retrieval_qualification.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        **benchmark_runtime_identity(runtime),
        "dataset_sha256": file_sha256(dataset_path),
        "dataset_manifest_sha256": file_sha256(dataset_manifest_path),
        "evaluation_role": manifest.get("evaluation_role"),
        "baseline_policy": manifest.get("baseline_policy"),
        "sealed_qualification_eligible": is_sealed,
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
        "reported_cost_usd": spent,
        "repeated_rankings_match": rankings_match,
        "requested_46_of_47_gate_compatible": gate_compatible,
        "qualified": bool(
            is_sealed
            and owner_approved
            and gate_compatible
            and not budget_exceeded
            and all(item["complete"] for item in reports)
            and all(item["recall_at_5"] >= 46 / 47 for item in reports)
        ),
        "qualification_limitations": _qualification_limitations(
            is_sealed=is_sealed,
            owner_approved=owner_approved,
            gate_compatible=gate_compatible,
            case_count=len(cases),
        ),
        "repetition_reports": reports,
    }
    with atomic_text_writer(output_path) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return report
