"""Bounded second-cycle retrieval assessment. Default path remains baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from firelens.answering.context import (
    EvidenceIndex,
    _aspect_supported,
    build_evidence_packet,
    decide_support,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    EvidencePacket,
    QueryPlan,
    RetrievalBundle,
    RetrievalHit,
    RetrievalRequest,
    SupportDecision,
)
from firelens.ingestion.chunking import ChunkRecord

RetrievalStrategy = Literal["baseline", "adaptive_v1"]
MAX_CYCLES = 2
MAX_QUERIES = 6


class RetrievalSearcher(Protocol):
    async def search(self, plan: QueryPlan) -> RetrievalBundle: ...


@dataclass(frozen=True)
class RetrievalAttempt:
    cycle: int
    query: str
    aspect_id: str | None
    hit_ids: tuple[str, ...]


@dataclass
class AdaptiveRetrievalOutcome:
    bundle: RetrievalBundle
    packet: EvidencePacket
    support: SupportDecision
    cycles: int = 1
    queries: list[str] = field(default_factory=list)
    attempts: list[RetrievalAttempt] = field(default_factory=list)
    refined: bool = False


def normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def missing_supported_aspects(plan: QueryPlan, packet: EvidencePacket) -> list[str]:
    missing: list[str] = []
    for aspect in plan.required_aspects:
        if not _aspect_supported(aspect, packet):
            missing.append(aspect)
    return missing


def merge_hits(*groups: list[RetrievalHit]) -> list[RetrievalHit]:
    merged: list[RetrievalHit] = []
    seen: set[str] = set()
    for group in groups:
        for hit in group:
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            merged.append(hit)
    return merged


def second_cycle_plan(
    plan: QueryPlan, missing_aspects: list[str], used: set[str]
) -> QueryPlan | None:
    queries: list[RetrievalRequest] = []
    for aspect in missing_aspects:
        key = normalize_query(aspect)
        if not key or key in used:
            continue
        queries.append(RetrievalRequest(query=aspect))
        if len(used) + len(queries) >= MAX_QUERIES:
            break
    if not queries:
        return None
    return plan.model_copy(
        update={
            "retrieval_requests": queries,
            "required_aspects": [request.query for request in queries],
        }
    )


async def refine_if_needed(
    *,
    plan: QueryPlan,
    request_queries: tuple[str, ...],
    first_bundle: RetrievalBundle,
    first_packet: EvidencePacket,
    chunks: tuple[ChunkRecord, ...],
    corpus_version: str,
    config: FireLensConfig,
    searcher: RetrievalSearcher,
    evidence_index: EvidenceIndex | None = None,
) -> AdaptiveRetrievalOutcome:
    """Run at most one targeted second cycle when required aspects are missing."""

    used = {normalize_query(request.query) for request in plan.retrieval_requests}
    used.add(normalize_query(plan.normalized_question))
    attempts = [
        RetrievalAttempt(
            cycle=1,
            query=request.query,
            aspect_id=request.query,
            hit_ids=tuple(hit.chunk_id for hit in first_bundle.reranked_hits),
        )
        for request in plan.retrieval_requests
    ]
    support = decide_support(plan, first_packet, first_bundle)
    outcome = AdaptiveRetrievalOutcome(
        bundle=first_bundle,
        packet=first_packet,
        support=support,
        cycles=1,
        queries=[request.query for request in plan.retrieval_requests],
        attempts=attempts,
    )
    if config.retrieval_strategy != "adaptive_v1":
        return outcome
    missing = missing_supported_aspects(plan, first_packet)
    if not missing or len(used) >= MAX_QUERIES:
        return outcome
    follow = second_cycle_plan(plan, missing, used)
    if follow is None:
        return outcome
    second = await searcher.search(follow)
    merged_hits = merge_hits(first_bundle.reranked_hits, second.reranked_hits)[:8]
    packet = build_evidence_packet(
        plan.normalized_question,
        merged_hits,
        chunks,
        corpus_version=corpus_version,
        config=config,
        evidence_index=evidence_index,
        selection_aspects=tuple(dict.fromkeys([*plan.required_aspects, *request_queries])),
    )
    merged = first_bundle.model_copy(
        update={
            "reranked_hits": merged_hits,
            "fused_hits": merge_hits(first_bundle.fused_hits, second.fused_hits),
            "complete": first_bundle.complete and second.complete,
        }
    )
    outcome.bundle = merged
    outcome.packet = packet
    outcome.support = decide_support(plan, packet, merged)
    outcome.cycles = 2
    outcome.refined = True
    outcome.queries.extend(request.query for request in follow.retrieval_requests)
    outcome.attempts.append(
        RetrievalAttempt(
            cycle=2,
            query=" | ".join(request.query for request in follow.retrieval_requests),
            aspect_id=follow.required_aspects[0] if follow.required_aspects else None,
            hit_ids=tuple(hit.chunk_id for hit in second.reranked_hits),
        )
    )
    return outcome
