"""Execution and review-packet rendering for the frozen V1 retrieval benchmark."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from firelens.benchmark_contracts import (
    BenchmarkDataset,
    file_sha256,
    load_benchmark,
)
from firelens.benchmark_support import (
    benchmark_runtime_identity,
    execution_provider_data,
    mean,
    percentile,
    precision_recall,
    ranking_metrics,
    stage_rankings,
    usage_cost,
    usage_total,
)
from firelens.contracts import QueryRequest, QueryRoute, ReasonCode, ResponseStatus
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer


async def run_benchmark(
    runtime: Runtime,
    *,
    dataset_path: Path,
    output_path: Path,
    review_packet_path: Path,
    splits: set[str] | None = None,
    max_cost_usd: float | None = None,
) -> dict[str, Any]:
    if runtime.service is None:
        raise RuntimeError("FireLens runtime is not ready")
    dataset = load_benchmark(dataset_path)
    selected = [case for case in dataset.cases if not splits or case.split in splits]
    rows: list[dict[str, Any]] = []
    chunks_by_id = runtime.chunks_by_id
    reported_cost_usd = 0.0
    budget_exceeded = False
    for case in selected:
        if max_cost_usd is not None and reported_cost_usd >= max_cost_usd:
            budget_exceeded = True
            break
        started = perf_counter()
        execution = await runtime.service.execute_ask(QueryRequest(question=case.question))
        response = execution.response
        latency_ms = (perf_counter() - started) * 1_000
        _, observed_usage, observed_attempts, _ = execution_provider_data(execution)
        provider_usage = {
            "retrieval": {
                "planning": observed_usage.get("planner", []),
                "embedding": observed_usage.get("embeddings", []),
                "rerank": observed_usage.get("reranker", []),
            },
            "generation": observed_usage.get("grounded_generation", []),
        }
        provider_attempts = {
            "retrieval": {
                "planning": observed_attempts.get("planner", []),
                "embedding": observed_attempts.get("embeddings", []),
                "rerank": observed_attempts.get("reranker", []),
            },
            "generation": observed_attempts.get("grounded_generation", []),
        }
        rankings = stage_rankings(execution)
        stage_metrics = {
            stage: ranking_metrics(rankings.get(stage, []), case, chunks_by_id)
            for stage in ("bm25", "vector", "fused", "reranked")
            if case.acceptable_evidence
        }
        route = execution.plan.route.value
        status = response.status.value
        literal_forbidden_hits = [
            phrase
            for phrase in case.forbidden_claims
            if response.answer and phrase.casefold() in response.answer.casefold()
        ]
        route_correct = route == case.expected_route.value or (
            case.expected_route == QueryRoute.LIVE
            and execution.plan.route == QueryRoute.PROHIBITED
            and execution.plan.boundary_reason == ReasonCode.POLICY_MANIPULATION
        )
        rows.append(
            {
                "id": case.id,
                "split": case.split,
                "category": case.category,
                "risk_level": case.risk_level,
                "question": case.question,
                "expected_route": case.expected_route.value,
                "actual_route": route,
                "route_correct": route_correct,
                "expected_status": case.expected_status,
                "actual_status": status,
                "status_correct": status == case.expected_status,
                "reason_code": response.reason_code,
                "latency_ms": latency_ms,
                "stage_metrics": stage_metrics,
                "validation_accepted": bool(
                    response.validation and response.validation.accepted
                ),
                "validation": (
                    response.validation.model_dump(mode="json") if response.validation else None
                ),
                "required_concepts": case.required_concepts,
                "forbidden_claims": case.forbidden_claims,
                "required_limitations": case.required_limitations,
                "semantic_adjudication": "pending_owner_review",
                "literal_forbidden_phrase_hits": literal_forbidden_hits,
                "answer": response.answer,
                "claims": [claim.model_dump(mode="json") for claim in response.claims],
                "evidence": [item.model_dump(mode="json") for item in response.evidence],
                "provider_usage": provider_usage,
                "provider_attempts": provider_attempts,
            }
        )
        reported_cost_usd += usage_cost(provider_usage)

    answerable = [row for row in rows if row["expected_status"] == "answer"]
    safety = [row for row in rows if row["risk_level"] == "high"]
    latencies = [float(row["latency_ms"]) for row in rows]
    answer_latencies = [
        float(row["latency_ms"]) for row in rows if row["actual_status"] == "answer"
    ]
    stage_summary: dict[str, dict[str, float]] = {}
    for stage in ("bm25", "vector", "fused", "reranked"):
        metrics = [
            row["stage_metrics"][stage] for row in answerable if stage in row["stage_metrics"]
        ]
        stage_summary[stage] = {
            "recall": mean([float(item["hit"]) for item in metrics]),
            "mrr": mean([float(item["reciprocal_rank"]) for item in metrics]),
            "ndcg": mean([float(item["ndcg"]) for item in metrics]),
            "mean_source_coverage": mean([float(item["source_coverage"]) for item in metrics]),
        }

    report = {
        "report_version": "firelens_benchmark_report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": file_sha256(dataset_path),
        **benchmark_runtime_identity(runtime),
        "corpus_version": runtime.corpus_version,
        "models": {
            "embedding": runtime.config.embedding_model,
            "rerank": runtime.config.rerank_model,
            "generation": runtime.config.generation_model,
        },
        "configuration": {
            "bm25_top_k": runtime.config.bm25_top_k,
            "vector_top_k": runtime.config.vector_top_k,
            "fused_top_k": runtime.config.fused_top_k,
            "rrf_k": runtime.config.rrf_k,
            "rerank_top_k": runtime.config.rerank_top_k,
        },
        "case_count": len(rows),
        "selected_case_count": len(selected),
        "complete": len(rows) == len(selected),
        "cost_budget_usd": max_cost_usd,
        "cost_budget_exceeded": budget_exceeded,
        "metrics": {
            "route_accuracy": mean([float(row["route_correct"]) for row in rows]),
            "status_accuracy": mean([float(row["status_correct"]) for row in rows]),
            "safety_route_accuracy": mean([float(row["route_correct"]) for row in safety]),
            "safety_status_accuracy": mean([float(row["status_correct"]) for row in safety]),
            "route_precision_recall": {
                route.value: precision_recall(
                    rows,
                    expected_key="expected_route",
                    actual_key="actual_route",
                    positive=route.value,
                )
                for route in QueryRoute
            },
            "abstention": precision_recall(
                rows,
                expected_key="expected_status",
                actual_key="actual_status",
                positive="abstention",
            ),
            "accepted_answer_validation_rate": mean(
                [
                    float(row["validation_accepted"])
                    for row in rows
                    if row["actual_status"] == "answer"
                ]
            ),
            "provider_error_rate": mean(
                [float(row["actual_status"] == ResponseStatus.ERROR.value) for row in rows]
            ),
            "latency_ms_p50": percentile(latencies, 0.50),
            "latency_ms_p95": percentile(latencies, 0.95),
            "answer_latency_ms_p50": percentile(answer_latencies, 0.50),
            "answer_latency_ms_p95": percentile(answer_latencies, 0.95),
            "reported_cost_usd": reported_cost_usd,
            "provider_tokens": {
                field: sum(usage_total(row["provider_usage"], field) for row in rows)
                for field in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "citation_id_validity_rate": mean(
                [
                    float(row["validation"]["citation_ids_valid"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "exact_quote_validity_rate": mean(
                [
                    float(row["validation"]["quotes_exact"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "claim_support_floor_validity_rate": mean(
                [
                    float(row["validation"]["claim_support_valid"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "policy_validation_rate": mean(
                [
                    float(row["validation"]["policy_valid"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "validation_rejection_rate": mean(
                [float(row["reason_code"] == "draft_validation_failed") for row in rows]
            ),
            "literal_forbidden_phrase_hit_count": sum(
                len(row["literal_forbidden_phrase_hits"]) for row in rows
            ),
            "semantic_correctness_scored": False,
            "required_claim_coverage_scored": False,
            "unsupported_claim_count_scored": False,
            "stages": stage_summary,
            "by_split": {
                split: {
                    "case_count": len(split_rows),
                    "route_accuracy": mean([float(row["route_correct"]) for row in split_rows]),
                    "status_accuracy": mean(
                        [float(row["status_correct"]) for row in split_rows]
                    ),
                }
                for split in ("development", "holdout", "red_team")
                if (split_rows := [row for row in rows if row["split"] == split])
            },
        },
        "cases": rows,
    }
    with atomic_text_writer(output_path) as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_review_packet(dataset, rows, review_packet_path)
    return report


def write_review_packet(
    dataset: BenchmarkDataset,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    by_id = {case.id: case for case in dataset.cases}
    with atomic_text_writer(path) as stream:
        stream.write("# FireLens V1 semantic review packet\n\n")
        stream.write("Every claim must be judged against its displayed quote. ")
        stream.write("Automated validation is not semantic approval.\n\n")
        for row in rows:
            case = by_id[row["id"]]
            stream.write(f"## {case.id}: {case.question}\n\n")
            stream.write(f"- Split/category: `{case.split}` / `{case.category}`\n")
            stream.write(
                f"- Expected: `{case.expected_route.value}` / `{case.expected_status}`\n"
            )
            stream.write(
                f"- Required concepts: {', '.join(case.required_concepts) or 'none'}\n"
            )
            stream.write(f"- Forbidden claims: {', '.join(case.forbidden_claims) or 'none'}\n")
            stream.write(f"- Actual status: `{row['actual_status']}`\n")
            stream.write(f"- Answer: {row['answer'] or '(none)'}\n\n")
            for claim in row["claims"]:
                stream.write(f"### {claim['claim_id']}: {claim['text']}\n\n")
                for support in claim["supports"]:
                    stream.write(f"- `{support['evidence_id']}`: “{support['quote']}”\n")
                stream.write("- [ ] supported  [ ] unsupported  [ ] unclear\n\n")
            stream.write("Owner notes: \n\n---\n\n")
