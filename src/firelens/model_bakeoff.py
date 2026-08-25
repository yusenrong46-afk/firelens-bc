"""Identical-evidence generation-model bake-off with human review required."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from firelens.answering.context import build_evidence_packet
from firelens.answering.generate import draft_schema, generation_messages
from firelens.answering.validate import validate_draft
from firelens.benchmark import _mean, _percentile, _usage_cost, file_sha256, load_benchmark
from firelens.config import FireLensConfig
from firelens.contracts import GroundedDraft, QueryRequest, SupportStatus
from firelens.errors import ProviderError
from firelens.providers.openrouter import OpenRouterProvider
from firelens.runtime import load_runtime
from firelens.storage import atomic_text_writer

DEFAULT_GENERATION_CANDIDATES = (
    "google/gemini-3.5-flash-lite",
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash-lite",
)

# OpenRouter reports exact cost only after a request completes. Reserve these
# bounded per-operation envelopes before dispatch so a bake-off cannot knowingly
# start a call with insufficient budget. An observed charge above its envelope is
# still recorded as a failed budget, never reported as a complete bake-off.
RETRIEVAL_CASE_COST_RESERVE_USD = 0.05
GENERATION_CALL_COST_RESERVE_USD = 0.05


def _balanced_cases(dataset_path: Path, limit: int) -> list[Any]:
    dataset = load_benchmark(dataset_path)
    pools: dict[str, list[Any]] = defaultdict(list)
    for case in dataset.cases:
        if case.split == "development" and case.acceptable_evidence:
            pools[case.category].append(case)
    selected: list[Any] = []
    categories = sorted(pools)
    while len(selected) < limit and any(pools.values()):
        for category in categories:
            if pools[category] and len(selected) < limit:
                selected.append(pools[category].pop(0))
    return selected


async def run_model_bakeoff(
    config: FireLensConfig,
    *,
    dataset_path: Path,
    output_path: Path,
    review_packet_path: Path,
    models: tuple[str, ...] = DEFAULT_GENERATION_CANDIDATES,
    case_limit: int = 12,
    max_cost_usd: float = 0.50,
    retrieval_case_cost_reserve_usd: float = RETRIEVAL_CASE_COST_RESERVE_USD,
    generation_call_cost_reserve_usd: float = GENERATION_CALL_COST_RESERVE_USD,
) -> dict[str, Any]:
    if max_cost_usd <= 0:
        raise ValueError("model bake-off cost budget must be positive")
    if retrieval_case_cost_reserve_usd < 0 or generation_call_cost_reserve_usd < 0:
        raise ValueError("model bake-off cost reservations cannot be negative")
    runtime = load_runtime(config)
    providers: dict[str, OpenRouterProvider] = {}
    try:
        if runtime.service is None or runtime.corpus_version is None:
            raise RuntimeError(f"FireLens runtime is not ready: {runtime.problems}")
        cases = _balanced_cases(dataset_path, case_limit)
        packets: list[tuple[Any, Any]] = []
        retrieval_cost = 0.0
        budget_reservation_exhausted = False
        cost_budget_exceeded = False
        for case in cases:
            if (
                retrieval_cost
                + generation_call_cost_reserve_usd
                + retrieval_case_cost_reserve_usd
                > max_cost_usd
            ):
                budget_reservation_exhausted = True
                break
            search = await runtime.service.search(QueryRequest(question=case.question))
            if search.support.status != SupportStatus.ANSWERABLE:
                continue
            retrieval_cost += _usage_cost(search.retrieval.provider_usage)
            if retrieval_cost > max_cost_usd:
                cost_budget_exceeded = True
                break
            packets.append(
                (
                    case,
                    build_evidence_packet(
                        search.plan.normalized_question,
                        search.retrieval.reranked_hits,
                        runtime.chunks,
                        corpus_version=runtime.corpus_version,
                        config=config,
                    ),
                )
            )

        rows: list[dict[str, Any]] = []
        generation_cost = 0.0
        for model in models:
            provider = OpenRouterProvider(config.model_copy(update={"generation_model": model}))
            providers[model] = provider
            for case, packet in packets:
                if (
                    retrieval_cost + generation_cost + generation_call_cost_reserve_usd
                    > max_cost_usd
                ):
                    budget_reservation_exhausted = True
                    break
                started = perf_counter()
                try:
                    generated = await provider.generate_grounded(
                        generation_messages(packet, original_question=case.question),
                        output_schema=draft_schema(packet),
                    )
                    latency_ms = (perf_counter() - started) * 1_000
                    if not isinstance(generated.draft, GroundedDraft):
                        raise RuntimeError("generation candidate returned a non-grounded draft")
                    validation = validate_draft(generated.draft, packet)
                    cost = _usage_cost(generated.usage)
                    generation_cost += cost
                    if retrieval_cost + generation_cost > max_cost_usd:
                        cost_budget_exceeded = True
                    rows.append(
                        {
                            "case_id": case.id,
                            "category": case.category,
                            "question": case.question,
                            "model": model,
                            "provider_model": generated.model,
                            "answer_type": generated.draft.answer_type,
                            "answer": " ".join(claim.text for claim in generated.draft.claims),
                            "claims": [
                                claim.model_dump(mode="json")
                                for claim in generated.draft.claims
                            ],
                            "validation": validation.model_dump(mode="json"),
                            "provider_error": None,
                            "latency_ms": latency_ms,
                            "reported_cost_usd": cost,
                            "semantic_adjudication": "pending_owner_review",
                        }
                    )
                    if cost_budget_exceeded:
                        break
                except ProviderError as exc:
                    rows.append(
                        {
                            "case_id": case.id,
                            "category": case.category,
                            "question": case.question,
                            "model": model,
                            "provider_model": None,
                            "answer_type": None,
                            "answer": None,
                            "claims": [],
                            "validation": None,
                            "provider_error": exc.kind.value,
                            "latency_ms": (perf_counter() - started) * 1_000,
                            "reported_cost_usd": 0.0,
                            "semantic_adjudication": "pending_owner_review",
                        }
                    )

        summaries: dict[str, dict[str, Any]] = {}
        for model in models:
            model_rows = [row for row in rows if row["model"] == model]
            latencies = [float(row["latency_ms"]) for row in model_rows]
            summaries[model] = {
                "case_count": len(model_rows),
                "provider_error_rate": _mean(
                    [float(row["provider_error"] is not None) for row in model_rows]
                ),
                "structural_acceptance_rate": _mean(
                    [
                        float(row["validation"] is not None and row["validation"]["accepted"])
                        for row in model_rows
                    ]
                ),
                "guidance_rate": _mean(
                    [float(row["answer_type"] == "guidance") for row in model_rows]
                ),
                "latency_ms_p50": _percentile(latencies, 0.50),
                "latency_ms_p95": _percentile(latencies, 0.95),
                "reported_cost_usd": sum(float(row["reported_cost_usd"]) for row in model_rows),
                "semantic_quality_scored": False,
            }

        complete = (
            bool(packets)
            and bool(models)
            and not (budget_reservation_exhausted or cost_budget_exceeded)
            and all(summary["case_count"] == len(packets) for summary in summaries.values())
        )
        report = {
            "report_version": "firelens_generation_bakeoff.v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset_sha256": file_sha256(dataset_path),
            "split": "development",
            "holdout_opened": False,
            "identical_evidence_packets": True,
            "packet_count": len(packets),
            "models": list(models),
            "complete": complete,
            "reported_cost_usd": retrieval_cost + generation_cost,
            "cost_budget_usd": max_cost_usd,
            "retrieval_case_cost_reserve_usd": retrieval_case_cost_reserve_usd,
            "generation_call_cost_reserve_usd": generation_call_cost_reserve_usd,
            "cost_budget_exceeded": cost_budget_exceeded,
            "budget_reservation_exhausted": budget_reservation_exhausted,
            "retrieval_cost_usd": retrieval_cost,
            "generation_cost_usd": generation_cost,
            "summaries": summaries,
            "selected": config.generation_model,
            "selection_status": "default_retained_pending_owner_semantic_review",
            "rows": rows,
        }
        with atomic_text_writer(output_path) as stream:
            stream.write(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
        _write_review_packet(rows, packets, review_packet_path)
        return report
    finally:
        for provider in providers.values():
            await provider.aclose()
        await runtime.aclose()


def _write_review_packet(
    rows: list[dict[str, Any]], packets: list[tuple[Any, Any]], path: Path
) -> None:
    packet_by_case = {case.id: packet for case, packet in packets}
    with atomic_text_writer(path) as stream:
        stream.write("# FireLens V1 generation-model review\n\n")
        stream.write("All models received the same local evidence packet for each case. ")
        stream.write(
            "No model may win until the owner reviews semantic support and completeness.\n\n"
        )
        for row in rows:
            stream.write(f"## {row['case_id']} — `{row['model']}`\n\n")
            stream.write(f"Question: {row['question']}\n\n")
            stream.write(f"Answer: {row['answer'] or '(provider error)'}\n\n")
            packet = packet_by_case[row["case_id"]]
            quote_by_id = {
                candidate.quote_id: candidate for candidate in packet.quote_candidates
            }
            for claim in row["claims"]:
                stream.write(f"- Claim: {claim['text']}\n")
                for quote_id in claim["evidence_quote_ids"]:
                    candidate = quote_by_id.get(quote_id)
                    if candidate is not None:
                        stream.write(f"  - `{quote_id}`: “{candidate.text}”\n")
            stream.write("- [ ] supported  [ ] complete  [ ] safe\n\n---\n\n")
