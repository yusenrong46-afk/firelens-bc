"""Neighbor-aware evidence spans and conservative support decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from firelens.config import FireLensConfig
from firelens.contracts import (
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    QueryPlan,
    QueryRoute,
    ReasonCode,
    RetrievalBundle,
    RetrievalHit,
    SupportDecision,
    SupportStatus,
)
from firelens.ingestion.chunking import ChunkRecord


@dataclass(frozen=True)
class EvidenceIndex:
    """Immutable lookup tables constructed once with the service."""

    by_id: dict[str, ChunkRecord]
    by_parent_index: dict[tuple[str, int], ChunkRecord]

    @classmethod
    def from_chunks(cls, chunks: Sequence[ChunkRecord]) -> EvidenceIndex:
        return cls(
            by_id={chunk.chunk_id: chunk for chunk in chunks},
            by_parent_index={
                (chunk.parent_record_id, chunk.chunk_index): chunk for chunk in chunks
            },
        )


@dataclass
class EvidenceGroup:
    parent_record_id: str
    chunk_ids: set[str] = field(default_factory=set)
    primary_hits: list[RetrievalHit] = field(default_factory=list)


def _exact_quote_segments(text: str, *, max_chars: int = 500) -> list[str]:
    """Create bounded exact substrings without normalizing source whitespace."""

    segments: list[str] = []
    for paragraph in text.split("\n\n"):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            segments.append(paragraph)
            continue
        active = ""
        for line in paragraph.splitlines(keepends=True):
            while len(line) > max_chars:
                if active:
                    segments.append(active.rstrip("\n"))
                    active = ""
                segments.append(line[:max_chars])
                line = line[max_chars:]
            if active and len(active) + len(line) > max_chars:
                segments.append(active.rstrip("\n"))
                active = ""
            active += line
        if active:
            segments.append(active.rstrip("\n"))
    return [segment for segment in segments if segment.strip()]


def _candidate_chunk_ids(
    hit: RetrievalHit,
    by_parent_index: dict[tuple[str, int], ChunkRecord],
    window: int,
) -> set[str]:
    return {
        neighbor.chunk_id
        for offset in range(-window, window + 1)
        if (neighbor := by_parent_index.get((hit.parent_record_id, hit.chunk_index + offset)))
        is not None
    }


def build_evidence_packet(
    question: str,
    reranked_hits: Sequence[RetrievalHit],
    chunks: Sequence[ChunkRecord],
    *,
    corpus_version: str,
    config: FireLensConfig,
    evidence_index: EvidenceIndex | None = None,
) -> EvidencePacket:
    index = evidence_index or EvidenceIndex.from_chunks(chunks)
    groups: list[EvidenceGroup] = []

    for hit in reranked_hits[: config.max_evidence_spans]:
        neighbor_ids = _candidate_chunk_ids(hit, index.by_parent_index, config.neighbor_window)
        matching_groups: list[EvidenceGroup] = []
        for group in groups:
            if group.parent_record_id == hit.parent_record_id and (
                group.chunk_ids & neighbor_ids
            ):
                matching_groups.append(group)
        if not matching_groups:
            groups.append(
                EvidenceGroup(
                    parent_record_id=hit.parent_record_id,
                    chunk_ids=set(neighbor_ids),
                    primary_hits=[hit],
                )
            )
            continue

        target = matching_groups[0]
        target.chunk_ids.update(neighbor_ids)
        target.primary_hits.append(hit)
        for redundant in matching_groups[1:]:
            target.chunk_ids.update(redundant.chunk_ids)
            target.primary_hits.extend(redundant.primary_hits)
            groups.remove(redundant)

    spans: list[EvidenceSpan] = []
    used_chars = 0
    for group in groups:
        primary_hits = group.primary_hits
        primary_ids = [hit.chunk_id for hit in primary_hits]
        ordered_chunks = sorted(
            (index.by_id[chunk_id] for chunk_id in group.chunk_ids),
            key=lambda chunk: chunk.chunk_index,
        )
        primary_text = "\n\n".join(hit.text for hit in primary_hits)
        context_text = "\n\n".join(chunk.text for chunk in ordered_chunks)
        remaining = config.max_context_chars - used_chars
        if len(context_text) > remaining:
            context_text = primary_text
        if len(context_text) > remaining:
            continue
        hit = primary_hits[0]
        spans.append(
            EvidenceSpan(
                evidence_id=f"E{len(spans) + 1}",
                primary_chunk_ids=primary_ids,
                chunk_ids=[chunk.chunk_id for chunk in ordered_chunks],
                primary_text=primary_text,
                context_text=context_text,
                source_id=hit.source_id,
                title=hit.title,
                publisher=hit.publisher,
                canonical_url=hit.canonical_url,
                page_number=hit.page_number,
                section_title=hit.section_title,
                locator=hit.locator,
                temporal_class=hit.temporal_class,
                authority_class=hit.authority_class,
                document_sha256=hit.document_sha256,
            )
        )
        used_chars += len(context_text)

    quote_candidates = [
        EvidenceQuoteCandidate(
            quote_id=f"{span.evidence_id}Q{quote_number}",
            evidence_id=span.evidence_id,
            text=quote,
        )
        for span in spans
        for quote_number, quote in enumerate(_exact_quote_segments(span.primary_text), start=1)
    ]
    return EvidencePacket(
        question=question,
        corpus_version=corpus_version,
        items=spans,
        quote_candidates=quote_candidates,
        limitations=[
            "The evidence contains stable official guidance and does not establish current wildfire conditions."
        ],
    )


def decide_support(
    plan: QueryPlan,
    packet: EvidencePacket | None,
    retrieval: RetrievalBundle | None = None,
) -> SupportDecision:
    if plan.route == QueryRoute.PROHIBITED:
        return SupportDecision(
            status=SupportStatus.PROHIBITED,
            reason_code=plan.boundary_reason or ReasonCode.PERSONALIZED_SAFETY_DECISION,
            explanation=(
                "FireLens cannot provide personalized medical advice."
                if plan.boundary_reason == ReasonCode.PERSONALIZED_MEDICAL_ADVICE
                else (
                    "Conversation text cannot override FireLens safety and evidence rules."
                    if plan.boundary_reason == ReasonCode.POLICY_MANIPULATION
                    else (
                        "FireLens cannot provide personalized safety advice, select evacuation "
                        "routes, or decide whether you should stay, leave, evacuate, or return."
                    )
                )
            ),
        )
    if plan.route == QueryRoute.LIVE:
        return SupportDecision(
            status=SupportStatus.REQUIRES_LIVE_DATA,
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            explanation="This question requires current official information that is not available in static RAG.",
        )
    if retrieval is not None and not retrieval.complete:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.RETRIEVAL_INCOMPLETE,
            explanation="The required retrieval pipeline did not complete.",
        )
    if packet is None or not packet.items:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation="No approved static evidence was available for this question.",
        )
    if any(item.temporal_class != "stable_guidance" for item in packet.items):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.WRONG_TEMPORAL_CLASS,
            explanation="Retrieved evidence has an unsupported temporal classification.",
        )
    required = set().union(
        *(request.required_authorities for request in plan.retrieval_requests)
    )
    available = {item.authority_class for item in packet.items}
    if required and not (available & required):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.REQUIRED_AUTHORITY_MISSING,
            explanation="None of the required authority classes was present in selected evidence.",
        )
    return SupportDecision(
        status=SupportStatus.ANSWERABLE,
        reason_code=ReasonCode.APPROVED_STATIC_EVIDENCE,
        explanation="Approved stable guidance is available.",
    )
