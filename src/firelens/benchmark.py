"""Versioned benchmark loading, execution, metrics, and review packets.

The V1 and V1.1 datasets intentionally have separate schemas.  Keeping them
separate makes the frozen V1 contract stable while allowing V1.1 to measure
conversation, planning, and the two public evidence modes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from firelens.benchmark_contracts import (
    BenchmarkCase as BenchmarkCase,
)
from firelens.benchmark_contracts import (
    BenchmarkDataset as BenchmarkDataset,
)
from firelens.benchmark_contracts import (
    ConversationBenchmarkCase as ConversationBenchmarkCase,
)
from firelens.benchmark_contracts import (
    ConversationBenchmarkDataset as ConversationBenchmarkDataset,
)
from firelens.benchmark_contracts import (
    ExpectedEvidenceStatus as ExpectedEvidenceStatus,
)
from firelens.benchmark_contracts import (
    GoldEvidence as GoldEvidence,
)
from firelens.benchmark_contracts import (
    PaidProviderStage as PaidProviderStage,
)
from firelens.benchmark_contracts import (
    RelevanceAddendum as RelevanceAddendum,
)
from firelens.benchmark_contracts import (
    RelevanceJudgment as RelevanceJudgment,
)
from firelens.benchmark_contracts import (
    apply_relevance_addendum as apply_relevance_addendum,
)
from firelens.benchmark_contracts import (
    file_sha256 as file_sha256,
)
from firelens.benchmark_contracts import (
    load_benchmark as load_benchmark,
)
from firelens.benchmark_contracts import (
    load_conversation_benchmark as load_conversation_benchmark,
)
from firelens.benchmark_contracts import (
    load_relevance_addendum as load_relevance_addendum,
)
from firelens.benchmark_retrieval import (
    run_benchmark as run_benchmark,
)
from firelens.benchmark_retrieval import (
    write_review_packet as write_review_packet,
)
from firelens.benchmark_support import (
    benchmark_runtime_configuration as benchmark_runtime_configuration,
)
from firelens.benchmark_support import (
    benchmark_runtime_identity as _benchmark_runtime_identity,
)
from firelens.benchmark_support import (
    execution_provider_data as _benchmark_execution_provider_data,
)
from firelens.benchmark_support import (
    mean as _benchmark_mean,
)
from firelens.benchmark_support import (
    percentile as _benchmark_percentile,
)
from firelens.benchmark_support import (
    ranking_metrics as _benchmark_ranking_metrics,
)
from firelens.benchmark_support import (
    stage_rankings as _benchmark_stage_rankings,
)
from firelens.benchmark_support import (
    usage_cost as _benchmark_usage_cost,
)
from firelens.benchmark_support import (
    usage_total as _benchmark_usage_total,
)
from firelens.contracts import (
    AskResponse,
    EvidenceStatus,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
)
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer

benchmark_runtime_identity = _benchmark_runtime_identity
_execution_provider_data = _benchmark_execution_provider_data
_mean = _benchmark_mean
_percentile = _benchmark_percentile
_ranking_metrics = _benchmark_ranking_metrics
_stage_rankings = _benchmark_stage_rankings
_usage_cost = _benchmark_usage_cost
_usage_total = _benchmark_usage_total


def _binary_precision_recall(
    rows: Sequence[dict[str, Any]],
    *,
    expected_key: str,
    actual_key: str,
) -> dict[str, float]:
    true_positive = sum(bool(row[expected_key]) and bool(row[actual_key]) for row in rows)
    predicted_positive = sum(bool(row[actual_key]) for row in rows)
    expected_positive = sum(bool(row[expected_key]) for row in rows)
    return {
        "precision": true_positive / predicted_positive if predicted_positive else 0.0,
        "recall": true_positive / expected_positive if expected_positive else 0.0,
    }


def _actual_evidence_statuses(response: AskResponse) -> list[str]:
    return sorted({claim.evidence_status.value for claim in response.claims})


def _evidence_status_correct(response: AskResponse, expected: ExpectedEvidenceStatus) -> bool:
    statuses = _actual_evidence_statuses(response)
    if expected == "none":
        return not statuses and not response.evidence
    return statuses == [expected]


def _traceability_failure_count(response: AskResponse) -> int:
    """Count verified claims that fail deterministic local citation checks.

    This is intentionally narrower than semantic support.  Owner review remains
    responsible for deciding whether an exact quote actually entails a claim.
    """

    evidence = {item.evidence_id: item for item in response.evidence}
    failures = 0
    for claim in response.claims:
        if claim.evidence_status != EvidenceStatus.VERIFIED_CORPUS:
            continue
        if not claim.supports or any(
            support.evidence_id not in evidence
            or support.quote not in evidence[support.evidence_id].primary_text
            for support in claim.supports
        ):
            failures += 1
    return failures


def _required_limitations(
    response: AskResponse, required: Sequence[str]
) -> tuple[bool, list[str]]:
    visible = " ".join([response.answer or "", *response.limitations]).casefold()
    missing = [item for item in required if item.casefold() not in visible]
    return not missing, missing


async def run_conversation_benchmark(
    runtime: Runtime,
    *,
    dataset_path: Path,
    output_path: Path,
    review_packet_path: Path,
    splits: set[str] | None = None,
    max_cost_usd: float | None = None,
    execution_mode: Literal["offline_fake", "live_provider"] = "live_provider",
) -> dict[str, Any]:
    """Execute the V1.1 addendum using direct typed observations."""

    if runtime.service is None:
        raise RuntimeError("FireLens runtime is not ready")
    dataset = load_conversation_benchmark(dataset_path)
    selected = [case for case in dataset.cases if not splits or case.split in splits]
    chunks_by_id = runtime.chunks_by_id
    rows: list[dict[str, Any]] = []
    reported_cost_usd = 0.0
    budget_exceeded = False

    for case in selected:
        if max_cost_usd is not None and reported_cost_usd >= max_cost_usd:
            budget_exceeded = True
            break
        request = QueryRequest(question=case.question, history=case.history)
        started = perf_counter()
        execution = await runtime.service.execute_ask(request)
        response = execution.response
        latency_ms = (perf_counter() - started) * 1_000

        actual_route = execution.plan.route
        actual_relation = execution.plan.relation
        rankings = _stage_rankings(execution)
        stage_metrics = {
            stage: _ranking_metrics(rankings.get(stage, []), case, chunks_by_id)
            for stage in ("bm25", "vector", "fused", "reranked")
            if case.acceptable_evidence
        }
        (
            actual_stages,
            provider_usage,
            provider_attempts,
            provider_models,
        ) = _execution_provider_data(execution)
        limitations_correct, missing_limitations = _required_limitations(
            response, case.required_limitations
        )
        evidence_status_correct = _evidence_status_correct(
            response, case.expected_evidence_status
        )
        traceability_failures = _traceability_failure_count(response)
        claim_support_floor_failure = int(
            response.validation is not None and not response.validation.claim_support_valid
        )
        background_leaks = (
            len(response.evidence) + sum(len(claim.supports) for claim in response.claims)
            if response.response_mode == ResponseMode.BACKGROUND
            else 0
        )
        literal_forbidden_hits = [
            phrase
            for phrase in case.forbidden_claims
            if response.answer and phrase.casefold() in response.answer.casefold()
        ]
        route_correct = actual_route == case.expected_route or (
            case.expected_route == QueryRoute.LIVE
            and actual_route == QueryRoute.PROHIBITED
            and execution.plan.boundary_reason == ReasonCode.POLICY_MANIPULATION
        )
        relation_correct = actual_relation == case.expected_planning_relation
        status_correct = response.status.value == case.expected_status
        response_mode_correct = response.response_mode == case.expected_response_mode
        reranked_hit = bool(stage_metrics.get("reranked", {}).get("hit"))
        followup_resolved = case.category != "contextual_followup" or (
            route_correct
            and relation_correct
            and status_correct
            and response_mode_correct
            and evidence_status_correct
            and reranked_hit
        )
        row = {
            "id": case.id,
            "split": case.split,
            "category": case.category,
            "risk_level": case.risk_level,
            "question": case.question,
            "history": [turn.model_dump(mode="json") for turn in case.history],
            "expected_route": case.expected_route.value,
            "actual_route": actual_route.value,
            "route_correct": route_correct,
            "expected_planning_relation": (
                case.expected_planning_relation.value
                if case.expected_planning_relation is not None
                else None
            ),
            "actual_planning_relation": (
                actual_relation.value if actual_relation is not None else None
            ),
            "planning_relation_correct": relation_correct,
            "expected_status": case.expected_status,
            "actual_status": response.status.value,
            "status_correct": status_correct,
            "expected_response_mode": case.expected_response_mode.value,
            "actual_response_mode": response.response_mode.value,
            "response_mode_correct": response_mode_correct,
            "expected_evidence_status": case.expected_evidence_status,
            "actual_evidence_statuses": _actual_evidence_statuses(response),
            "evidence_status_correct": evidence_status_correct,
            "expected_paid_provider_stages": case.expected_paid_provider_stages,
            "actual_paid_provider_stages": actual_stages,
            "paid_call_boundary_correct": actual_stages == case.expected_paid_provider_stages,
            "provider_usage": provider_usage,
            "provider_attempts": provider_attempts,
            "provider_models": provider_models,
            "latency_ms": latency_ms,
            "stage_metrics": stage_metrics,
            "followup_resolved": followup_resolved,
            "required_concepts": case.required_concepts,
            "forbidden_claims": case.forbidden_claims,
            "required_limitations": case.required_limitations,
            "required_limitations_correct": limitations_correct,
            "missing_required_limitations": missing_limitations,
            "literal_forbidden_phrase_hits": literal_forbidden_hits,
            "background_citation_leak_count": background_leaks,
            "automated_traceability_failure_count": traceability_failures,
            "claim_support_floor_failure_count": claim_support_floor_failure,
            "semantic_adjudication": "pending_owner_review",
            "reason_code": (
                response.reason_code.value if response.reason_code is not None else None
            ),
            "error_kind": response.error_kind,
            "answer": response.answer,
            "claims": [claim.model_dump(mode="json") for claim in response.claims],
            "evidence": [item.model_dump(mode="json") for item in response.evidence],
            "limitations": response.limitations,
            "suggested_questions": response.suggested_questions,
            "validation": (
                response.validation.model_dump(mode="json") if response.validation else None
            ),
        }
        rows.append(row)
        reported_cost_usd += _usage_cost(provider_usage)

    safety = [row for row in rows if row["risk_level"] == "high"]
    capability = [row for row in rows if row["category"] == "capability"]
    planned = [row for row in rows if row["expected_planning_relation"] is not None]
    followups = [row for row in rows if row["category"] == "contextual_followup"]
    evidence_mode_rows = [
        row
        for row in rows
        if row["expected_evidence_status"]
        in {EvidenceStatus.VERIFIED_CORPUS.value, EvidenceStatus.GENERAL_BACKGROUND.value}
    ]
    grounded = [
        row for row in rows if row["expected_response_mode"] == ResponseMode.GROUNDED.value
    ]
    limitation_rows = [row for row in rows if row["required_limitations"]]
    stage_summary: dict[str, dict[str, float]] = {}
    for stage in ("bm25", "vector", "fused", "reranked"):
        stage_rows = [
            row["stage_metrics"][stage] for row in grounded if stage in row["stage_metrics"]
        ]
        stage_summary[stage] = {
            "recall": _mean([float(item["hit"]) for item in stage_rows]),
            "mrr": _mean([float(item["reciprocal_rank"]) for item in stage_rows]),
            "ndcg": _mean([float(item["ndcg"]) for item in stage_rows]),
            "mean_source_coverage": _mean(
                [float(item["source_coverage"]) for item in stage_rows]
            ),
        }

    latency_values = [float(row["latency_ms"]) for row in rows]
    report = {
        "report_version": "firelens_conversation_benchmark_report.v1_1",
        "generated_at": datetime.now(UTC).isoformat(),
        "execution_mode": execution_mode,
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
            "retrieval_text_strategy": runtime.config.retrieval_text_strategy.value,
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
        "metric_definitions": {
            "capability_accuracy": "Case-level route, status, and response-mode match.",
            "followup_resolution_accuracy": (
                "Contextual follow-up route, relation, status, response mode, evidence "
                "status, and reranker evidence hit all match."
            ),
            "adjacent_background_precision_recall": (
                "Positive means the planner chose adjacent and the response used background mode."
            ),
            "required_limitation_accuracy": (
                "Exact case-insensitive visibility match on cases that require a limitation."
            ),
            "paid_call_boundary_accuracy": (
                "Exact provider-stage sequence match. Offline mode counts deterministic fake "
                "stage boundaries, not paid cost."
            ),
            "unsupported_verified_claim_count": (
                "Reserved for owner semantic review; automated checks report only exact local "
                "traceability failures."
            ),
        },
        "metrics": {
            "route_accuracy": _mean([float(row["route_correct"]) for row in rows]),
            "status_accuracy": _mean([float(row["status_correct"]) for row in rows]),
            "response_mode_accuracy": _mean(
                [float(row["response_mode_correct"]) for row in rows]
            ),
            "deterministic_safety_route_accuracy": _mean(
                [float(row["route_correct"]) for row in safety]
            ),
            "capability_accuracy": _mean(
                [
                    float(
                        row["route_correct"]
                        and row["status_correct"]
                        and row["response_mode_correct"]
                    )
                    for row in capability
                ]
            ),
            "planner_relation_accuracy": _mean(
                [float(row["planning_relation_correct"]) for row in planned]
            ),
            "tangent": _binary_precision_recall(
                [
                    {
                        "expected": row["expected_route"] == QueryRoute.TANGENT.value,
                        "actual": row["actual_route"] == QueryRoute.TANGENT.value
                        and row["actual_response_mode"] == ResponseMode.SCOPE_REDIRECT.value,
                    }
                    for row in rows
                ],
                expected_key="expected",
                actual_key="actual",
            ),
            "adjacent_background": _binary_precision_recall(
                [
                    {
                        "expected": row["expected_planning_relation"]
                        == QueryRelation.ADJACENT.value
                        and row["expected_response_mode"] == ResponseMode.BACKGROUND.value,
                        "actual": row["actual_planning_relation"]
                        == QueryRelation.ADJACENT.value
                        and row["actual_response_mode"] == ResponseMode.BACKGROUND.value,
                    }
                    for row in rows
                ],
                expected_key="expected",
                actual_key="actual",
            ),
            "followup_resolution_accuracy": _mean(
                [float(row["followup_resolved"]) for row in followups]
            ),
            "grounded_background_evidence_status_accuracy": _mean(
                [float(row["evidence_status_correct"]) for row in evidence_mode_rows]
            ),
            "background_citation_leak_count": sum(
                int(row["background_citation_leak_count"]) for row in rows
            ),
            "required_limitation_accuracy": _mean(
                [float(row["required_limitations_correct"]) for row in limitation_rows]
            ),
            "paid_call_boundary_accuracy": _mean(
                [float(row["paid_call_boundary_correct"]) for row in rows]
            ),
            "retrieval": stage_summary,
            "unsupported_verified_claim_count": None,
            "unsupported_verified_claim_count_scored": False,
            "automated_traceability_failure_count": sum(
                int(row["automated_traceability_failure_count"]) for row in rows
            ),
            "claim_support_floor_failure_count": sum(
                int(row["claim_support_floor_failure_count"]) for row in rows
            ),
            "provider_failure_rate": _mean(
                [float(row["actual_status"] == ResponseStatus.ERROR.value) for row in rows]
            ),
            "literal_forbidden_phrase_hit_count": sum(
                len(row["literal_forbidden_phrase_hits"]) for row in rows
            ),
            "latency_ms_p50": _percentile(latency_values, 0.50),
            "latency_ms_p95": _percentile(latency_values, 0.95),
            "reported_cost_usd": reported_cost_usd,
            "provider_tokens": {
                field_name: sum(_usage_total(row["provider_usage"], field_name) for row in rows)
                for field_name in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "semantic_correctness_scored": False,
            "by_split": {
                split: {
                    "case_count": len(split_rows),
                    "route_accuracy": _mean(
                        [float(row["route_correct"]) for row in split_rows]
                    ),
                    "status_accuracy": _mean(
                        [float(row["status_correct"]) for row in split_rows]
                    ),
                    "response_mode_accuracy": _mean(
                        [float(row["response_mode_correct"]) for row in split_rows]
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
    write_conversation_review_packet(dataset, rows, review_packet_path)
    return report


def write_conversation_review_packet(
    dataset: ConversationBenchmarkDataset,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    """Write the human semantic approval surface for V1.1."""

    by_id = {case.id: case for case in dataset.cases}
    with atomic_text_writer(path) as stream:
        stream.write("# FireLens V1.1 conversation semantic review packet\n\n")
        stream.write(
            "Automated checks establish routing, mode separation, citation identity, and exact "
            "quotes. They do not establish semantic entailment. The owner must review each "
            "selected case.\n\n"
        )
        for row in rows:
            case = by_id[row["id"]]
            stream.write(f"## {case.id}: {case.question}\n\n")
            if case.history:
                stream.write("### Bounded history\n\n")
                for turn in case.history:
                    stream.write(f"- **{turn.role}:** {turn.content}\n")
                stream.write("\n")
            stream.write(f"- Split/category: `{case.split}` / `{case.category}`\n")
            stream.write(
                "- Expected route/relation: "
                f"`{case.expected_route.value}` / "
                f"`{case.expected_planning_relation.value if case.expected_planning_relation else 'none'}`\n"
            )
            stream.write(
                "- Actual route/relation: "
                f"`{row['actual_route']}` / `{row['actual_planning_relation'] or 'none'}`\n"
            )
            stream.write(
                "- Expected status/mode/evidence: "
                f"`{case.expected_status}` / `{case.expected_response_mode.value}` / "
                f"`{case.expected_evidence_status}`\n"
            )
            stream.write(
                "- Actual status/mode/evidence: "
                f"`{row['actual_status']}` / `{row['actual_response_mode']}` / "
                f"`{', '.join(row['actual_evidence_statuses']) or 'none'}`\n"
            )
            stream.write(
                "- Expected provider stages: "
                f"{', '.join(case.expected_paid_provider_stages) or 'none'}\n"
            )
            stream.write(
                "- Actual provider stages: "
                f"{', '.join(row['actual_paid_provider_stages']) or 'none'}\n"
            )
            stream.write(
                f"- Required concepts: {', '.join(case.required_concepts) or 'none'}\n"
            )
            stream.write(f"- Forbidden claims: {', '.join(case.forbidden_claims) or 'none'}\n")
            stream.write(
                f"- Required limitations: {', '.join(case.required_limitations) or 'none'}\n"
            )
            stream.write(f"- Answer: {row['answer'] or '(none)'}\n\n")

            evidence_by_id = {item["evidence_id"]: item for item in row["evidence"]}
            for claim in row["claims"]:
                stream.write(
                    f"### {claim['claim_id']} [{claim['evidence_status']}]: {claim['text']}\n\n"
                )
                if claim["evidence_status"] == EvidenceStatus.VERIFIED_CORPUS.value:
                    for support in claim["supports"]:
                        item = evidence_by_id.get(support["evidence_id"])
                        stream.write(
                            f"- Exact quote `{support['evidence_id']}`: “{support['quote']}”\n"
                        )
                        if item is not None:
                            stream.write(
                                f"- Local source: {item['title']} ({item.get('locator') or 'no locator'})\n"
                            )
                            stream.write(f"- Primary passage: “{item['primary_text']}”\n")
                else:
                    stream.write(
                        "- Required visible limitation: "
                        f"{', '.join(row['limitations']) or '(missing)'}\n"
                    )
                stream.write("- [ ] supported  [ ] unsupported  [ ] unclear\n\n")

            stream.write("### Owner case decision\n\n")
            stream.write("- [ ] required concepts present\n")
            stream.write("- [ ] forbidden claims absent\n")
            stream.write("- [ ] required limitations present\n")
            stream.write("- [ ] approve  [ ] reject  [ ] needs discussion\n\n")
            stream.write("Owner notes: \n\n---\n\n")
