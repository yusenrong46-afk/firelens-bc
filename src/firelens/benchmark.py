"""Versioned benchmark loading, execution, metrics, and review packets.

The V1 and V1.1 datasets intentionally have separate schemas.  Keeping them
separate makes the frozen V1 contract stable while allowing V1.1 to measure
conversation, planning, and the two public evidence modes.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.answering.service import AskExecution
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    ConversationTurn,
    EvidenceStatus,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
)
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
    adjudication_status: Literal["automated_draft", "owner_approved"] = "automated_draft"
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


class RelevanceJudgment(BenchmarkModel):
    case_id: str = Field(pattern=r"^V1-[A-Z]+-[0-9]{3}$")
    rationale: str = Field(min_length=20, max_length=1_000)
    added_evidence: list[GoldEvidence] = Field(min_length=1)


class RelevanceAddendum(BenchmarkModel):
    addendum_version: Literal["firelens_relevance_addendum.v1"]
    base_dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_status: Literal["automated_evidence_audited", "owner_approved"]
    judgments: list[RelevanceJudgment] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> RelevanceAddendum:
        case_ids = [item.case_id for item in self.judgments]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("relevance addendum case IDs must be unique")
        return self


PaidProviderStage = Literal[
    "planner",
    "embeddings",
    "reranker",
    "grounded_generation",
    "background_generation",
]
ExpectedEvidenceStatus = Literal["verified_corpus", "general_background", "none"]


class ConversationBenchmarkCase(BenchmarkModel):
    """One strictly labelled V1.1 conversation case."""

    id: str = Field(pattern=r"^V1\.1-(DEV|HOLD|RED)-[0-9]{3}$")
    split: Literal["development", "holdout", "red_team"]
    category: Literal[
        "capability",
        "contextual_followup",
        "adjacent_background",
        "tangent",
        "mixed_adversarial",
    ]
    risk_level: Literal["ordinary", "high"]
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)
    expected_route: QueryRoute
    expected_planning_relation: QueryRelation | None
    expected_status: Literal["answer", "abstention"]
    expected_response_mode: ResponseMode
    acceptable_evidence: list[GoldEvidence] = Field(default_factory=list)
    expected_evidence_status: ExpectedEvidenceStatus
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_limitations: list[str] = Field(default_factory=list)
    expected_paid_provider_stages: list[PaidProviderStage] = Field(default_factory=list)
    adjudication_status: Literal["automated_draft", "owner_approved"] = "automated_draft"
    reviewer_notes: str = ""

    @model_validator(mode="after")
    def validate_expected_path(self) -> ConversationBenchmarkCase:
        answer_modes = {
            ResponseMode.CAPABILITY,
            ResponseMode.GROUNDED,
            ResponseMode.BACKGROUND,
            ResponseMode.SCOPE_REDIRECT,
        }
        if (self.expected_status == "answer") != (self.expected_response_mode in answer_modes):
            raise ValueError("expected status and response mode describe different outcomes")

        relation_routes = {QueryRoute.RELATED, QueryRoute.TANGENT}
        if (self.expected_planning_relation is None) != (
            self.expected_route not in relation_routes
        ):
            raise ValueError("planning relation must be present exactly for planned routes")
        if self.expected_route == QueryRoute.TANGENT and (
            self.expected_planning_relation != QueryRelation.TANGENT
        ):
            raise ValueError("tangent routes require a tangent planning relation")
        if (
            self.expected_route == QueryRoute.RELATED
            and self.expected_planning_relation
            not in {
                QueryRelation.GROUNDED_CANDIDATE,
                QueryRelation.ADJACENT,
            }
        ):
            raise ValueError("related routes require a grounded or adjacent relation")

        expected_evidence_by_mode: dict[ResponseMode, ExpectedEvidenceStatus] = {
            ResponseMode.GROUNDED: "verified_corpus",
            ResponseMode.BACKGROUND: "general_background",
            ResponseMode.CAPABILITY: "none",
            ResponseMode.SCOPE_REDIRECT: "none",
            ResponseMode.ABSTENTION: "none",
        }
        if (
            self.expected_evidence_status
            != expected_evidence_by_mode[self.expected_response_mode]
        ):
            raise ValueError("expected evidence status does not match response mode")
        if (self.expected_response_mode == ResponseMode.GROUNDED) != bool(
            self.acceptable_evidence
        ):
            raise ValueError("only grounded cases may require acceptable corpus evidence")

        paid_path: dict[ResponseMode, list[PaidProviderStage]] = {
            ResponseMode.CAPABILITY: [],
            ResponseMode.ABSTENTION: [],
            ResponseMode.SCOPE_REDIRECT: ["planner"],
            ResponseMode.GROUNDED: [
                "planner",
                "embeddings",
                "reranker",
                "grounded_generation",
            ],
            ResponseMode.BACKGROUND: [
                "planner",
                "embeddings",
                "reranker",
                "background_generation",
            ],
        }
        if self.expected_paid_provider_stages != paid_path[self.expected_response_mode]:
            raise ValueError("expected provider stages do not match the expected path")
        return self


class ConversationBenchmarkDataset(BenchmarkModel):
    dataset_version: str
    frozen_at: str
    cases: list[ConversationBenchmarkCase]

    @model_validator(mode="after")
    def unique_case_ids(self) -> ConversationBenchmarkDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("conversation benchmark case IDs must be unique")
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


def load_relevance_addendum(path: Path, *, dataset_path: Path) -> RelevanceAddendum:
    addendum = RelevanceAddendum.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if addendum.base_dataset_sha256 != file_sha256(dataset_path):
        raise ValueError("relevance addendum does not match the locked benchmark hash")
    return addendum


def apply_relevance_addendum(
    dataset: BenchmarkDataset, addendum: RelevanceAddendum
) -> BenchmarkDataset:
    cases_by_id = {case.id: case for case in dataset.cases}
    unknown = {item.case_id for item in addendum.judgments} - cases_by_id.keys()
    if unknown:
        raise ValueError(f"relevance addendum contains unknown cases: {sorted(unknown)}")

    additions = {item.case_id: item.added_evidence for item in addendum.judgments}
    updated_cases = []
    for case in dataset.cases:
        evidence = [*case.acceptable_evidence, *additions.get(case.id, [])]
        identities = [item.model_dump_json() for item in evidence]
        if len(identities) != len(set(identities)):
            raise ValueError(f"relevance addendum duplicates evidence for {case.id}")
        updated_cases.append(case.model_copy(update={"acceptable_evidence": evidence}))
    return dataset.model_copy(update={"cases": updated_cases})


def load_conversation_benchmark(
    path: Path, *, require_release_shape: bool = True
) -> ConversationBenchmarkDataset:
    """Load the V1.1 addendum without weakening the frozen V1 schema."""

    dataset = ConversationBenchmarkDataset.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if require_release_shape:
        splits = Counter(case.split for case in dataset.cases)
        categories = Counter(case.category for case in dataset.cases)
        expected_splits = {"development": 30, "holdout": 10, "red_team": 10}
        expected_categories = {
            "capability": 10,
            "contextual_followup": 10,
            "adjacent_background": 10,
            "tangent": 10,
            "mixed_adversarial": 10,
        }
        if len(dataset.cases) != 50 or dict(splits) != expected_splits:
            raise ValueError(
                "V1.1 conversation benchmark must contain exactly "
                f"{expected_splits}; got {dict(splits)}"
            )
        if dict(categories) != expected_categories:
            raise ValueError(
                "V1.1 conversation benchmark must contain exactly "
                f"{expected_categories}; got {dict(categories)}"
            )
        if any(
            (case.split == "red_team") != (case.risk_level == "high") for case in dataset.cases
        ):
            raise ValueError("V1.1 red-team cases must be high risk and only those cases")
    return dataset


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "require_zdr": config.require_zdr,
    }


def _current_commit(config: FireLensConfig) -> str | None:
    """Prefer the measured checkout commit, falling back to deployment metadata."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return config.build_commit
    commit = completed.stdout.strip()
    return commit or config.build_commit


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


def _ranking_metrics(
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


def _stage_rankings(execution: AskExecution) -> dict[str, list[str]]:
    bundle = execution.retrieval
    return {
        "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
        "vector": [hit.chunk_id for hit in bundle.vector_hits],
        "fused": [hit.chunk_id for hit in bundle.fused_hits],
        "reranked": [hit.chunk_id for hit in bundle.reranked_hits],
    }


def _execution_provider_data(
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

    # Every related/tangent final route passed through the planner. A failed
    # planner has no response metadata, but the attempted boundary is still known.
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
        _, observed_usage, observed_attempts, _ = _execution_provider_data(execution)
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
        rankings = _stage_rankings(execution)
        stage_metrics = {
            stage: _ranking_metrics(rankings.get(stage, []), case, chunks_by_id)
            for stage in ("bm25", "vector", "fused", "reranked")
            if case.acceptable_evidence
        }
        route = execution.plan.route.value
        status = response.status.value
        expected_status = case.expected_status
        validation_accepted = bool(response.validation and response.validation.accepted)
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
            "claim_support_floor_validity_rate": _mean(
                [
                    float(row["validation"]["claim_support_valid"])
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
