"""Versioned V1 benchmark loading, execution, metrics, and review packets."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.contracts import QueryRequest, QueryRoute, ResponseStatus
from firelens.ingestion.chunking import ChunkRecord
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldEvidence(BenchmarkModel):
    source_id: str
    pages: list[int] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class BenchmarkCase(BenchmarkModel):
    id: str = Field(pattern=r"^V1-[A-Z]+-[0-9]{3}$")
    split: Literal["development", "holdout", "red_team"]
    category: Literal[
        "single_source",
        "multi_source",
        "paraphrase_ambiguity",
        "insufficient_evidence",
        "false_premise",
        "live_status",
        "personalized_safety",
        "prompt_injection",
    ]
    risk_level: Literal["ordinary", "high"]
    question: str = Field(min_length=1, max_length=2_000)
    expected_route: QueryRoute
    expected_status: Literal["answer", "abstention"]
    acceptable_evidence: list[GoldEvidence] = Field(default_factory=list)
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_limitations: list[str] = Field(default_factory=list)
    adjudication_status: Literal["codex_draft", "owner_approved"] = "codex_draft"
    reviewer_notes: str = ""

    @model_validator(mode="after")
    def evidence_matches_expected_status(self) -> BenchmarkCase:
        if self.expected_status == "answer" and not self.acceptable_evidence:
            raise ValueError("answer cases require acceptable evidence")
        if self.expected_route != QueryRoute.STATIC and self.acceptable_evidence:
            raise ValueError("non-static routes cannot use static acceptable evidence")
        return self


class BenchmarkDataset(BenchmarkModel):
    dataset_version: str
    frozen_at: str
    cases: list[BenchmarkCase]

    @model_validator(mode="after")
    def unique_case_ids(self) -> BenchmarkDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case IDs must be unique")
        return self


def load_benchmark(path: Path, *, require_release_shape: bool = True) -> BenchmarkDataset:
    dataset = BenchmarkDataset.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if require_release_shape:
        splits = Counter(case.split for case in dataset.cases)
        expected = {"development": 60, "holdout": 20, "red_team": 20}
        if len(dataset.cases) != 100 or dict(splits) != expected:
            raise ValueError(
                f"V1 benchmark must contain exactly {expected}; got {dict(splits)}"
            )
    return dataset


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matches(chunk: ChunkRecord, evidence: GoldEvidence) -> bool:
    if chunk.source_id != evidence.source_id:
        return False
    if evidence.chunk_ids and chunk.chunk_id not in evidence.chunk_ids:
        return False
    return not evidence.pages or chunk.page_number in evidence.pages


def _ranking_metrics(
    chunk_ids: list[str],
    case: BenchmarkCase,
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
        "source_coverage": (
            len(hit_sources) / len(expected_sources) if expected_sources else 0.0
        ),
    }


def _mean(rows: list[float]) -> float:
    return sum(rows) / len(rows) if rows else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _precision_recall(
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


def _usage_total(value: object, field: str) -> int:
    if isinstance(value, dict):
        own = value.get(field)
        total = int(own) if isinstance(own, int) else 0
        return total + sum(
            _usage_total(child, field) for key, child in value.items() if key != field
        )
    if isinstance(value, list):
        return sum(_usage_total(item, field) for item in value)
    return 0


def _usage_cost(value: object) -> float:
    if isinstance(value, dict):
        own = value.get("cost")
        total = float(own) if isinstance(own, (int, float)) else 0.0
        return total + sum(_usage_cost(child) for key, child in value.items() if key != "cost")
    if isinstance(value, list):
        return sum(_usage_cost(item) for item in value)
    return 0.0


def _read_trace_events(runtime: Runtime, trace_id: str) -> list[dict[str, Any]]:
    path = runtime.config.trace_dir / f"{trace_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError(f"Trace {trace_id} has no valid event list")
    return events


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
        response = await runtime.service.ask(QueryRequest(question=case.question))
        latency_ms = (perf_counter() - started) * 1_000
        events = _read_trace_events(runtime, response.trace_id)
        search_event = next(event for event in events if event["operation"] == "search")
        ask_event = next(event for event in events if event["operation"] == "ask")
        provider_usage = {
            "retrieval": search_event.get("provider_usage", {}),
            "generation": ask_event.get("generation_usage", {}),
        }
        provider_attempts = {
            "retrieval": search_event.get("provider_attempts", {}),
            "generation": ask_event.get("generation_attempts"),
        }
        rankings = search_event.get("stage_rankings", {})
        stage_metrics = {
            stage: _ranking_metrics(rankings.get(stage, []), case, chunks_by_id)
            for stage in ("bm25", "vector", "fused", "reranked")
            if case.acceptable_evidence
        }
        route = search_event.get("route")
        status = response.status.value
        expected_status = case.expected_status
        validation_accepted = bool(response.validation and response.validation.accepted)
        literal_forbidden_hits = [
            phrase
            for phrase in case.forbidden_claims
            if response.answer and phrase.casefold() in response.answer.casefold()
        ]
        rows.append(
            {
                "id": case.id,
                "split": case.split,
                "category": case.category,
                "risk_level": case.risk_level,
                "question": case.question,
                "expected_route": case.expected_route.value,
                "actual_route": route,
                "route_correct": route == case.expected_route.value,
                "expected_status": expected_status,
                "actual_status": status,
                "status_correct": status == expected_status,
                "reason_code": response.reason_code,
                "latency_ms": latency_ms,
                "stage_metrics": stage_metrics,
                "validation_accepted": validation_accepted,
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
        reported_cost_usd += _usage_cost(provider_usage)

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
            "recall": _mean([float(item["hit"]) for item in metrics]),
            "mrr": _mean([float(item["reciprocal_rank"]) for item in metrics]),
            "ndcg": _mean([float(item["ndcg"]) for item in metrics]),
            "mean_source_coverage": _mean([float(item["source_coverage"]) for item in metrics]),
        }

    report = {
        "report_version": "firelens_benchmark_report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": file_sha256(dataset_path),
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
            "route_accuracy": _mean([float(row["route_correct"]) for row in rows]),
            "status_accuracy": _mean([float(row["status_correct"]) for row in rows]),
            "safety_route_accuracy": _mean([float(row["route_correct"]) for row in safety]),
            "safety_status_accuracy": _mean([float(row["status_correct"]) for row in safety]),
            "route_precision_recall": {
                route.value: _precision_recall(
                    rows,
                    expected_key="expected_route",
                    actual_key="actual_route",
                    positive=route.value,
                )
                for route in QueryRoute
            },
            "abstention": _precision_recall(
                rows,
                expected_key="expected_status",
                actual_key="actual_status",
                positive="abstention",
            ),
            "accepted_answer_validation_rate": _mean(
                [
                    float(row["validation_accepted"])
                    for row in rows
                    if row["actual_status"] == "answer"
                ]
            ),
            "provider_error_rate": _mean(
                [float(row["actual_status"] == ResponseStatus.ERROR.value) for row in rows]
            ),
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
            "answer_latency_ms_p50": _percentile(answer_latencies, 0.50),
            "answer_latency_ms_p95": _percentile(answer_latencies, 0.95),
            "reported_cost_usd": reported_cost_usd,
            "provider_tokens": {
                field: sum(_usage_total(row["provider_usage"], field) for row in rows)
                for field in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "citation_id_validity_rate": _mean(
                [
                    float(row["validation"]["citation_ids_valid"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "exact_quote_validity_rate": _mean(
                [
                    float(row["validation"]["quotes_exact"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "policy_validation_rate": _mean(
                [
                    float(row["validation"]["policy_valid"])
                    for row in rows
                    if row["validation"] is not None
                ]
            ),
            "validation_rejection_rate": _mean(
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
                    "route_accuracy": _mean(
                        [float(row["route_correct"]) for row in split_rows]
                    ),
                    "status_accuracy": _mean(
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
