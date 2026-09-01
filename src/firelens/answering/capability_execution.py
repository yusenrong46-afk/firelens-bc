"""Internal projection from validated capabilities to bounded static execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from firelens.answering.typed_records import load_inventory
from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    QueryPlan,
    QueryRelation,
    RetrievalBundle,
    RetrievalHit,
    RetrievalRequest,
    TemporalClass,
)
from firelens.guidance_capabilities import CapabilityBinding
from firelens.ingestion.chunking import ChunkRecord


def capability_query_plan(plan: QueryPlan, binding: CapabilityBinding) -> QueryPlan:
    """Use only registry-owned queries, aspects, and authority classes."""

    if binding.source_mode != "corpus":
        return plan
    authorities = frozenset(
        AuthorityClass(value) for value in binding.required_authority_classes
    )
    requests = [
        RetrievalRequest(
            query=query,
            required_authorities=authorities,
            purpose=f"capability_{number}",
        )
        for number, query in enumerate(binding.retrieval_queries, start=1)
    ]
    return plan.model_copy(
        update={
            "route": plan.route,
            "relation": QueryRelation.GROUNDED_CANDIDATE,
            "normalized_question": binding.retrieval_queries[0],
            "retrieval_requests": requests,
            "required_aspects": [aspect.text for aspect in binding.aspects],
        }
    )


def _bound_hit(chunk: ChunkRecord, rank: int, queries: Sequence[str]) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk.chunk_id,
        parent_record_id=chunk.parent_record_id,
        source_id=chunk.source_id,
        title=chunk.title,
        publisher=chunk.publisher,
        canonical_url=chunk.canonical_url,
        page_number=chunk.page_number,
        section_title=chunk.section_title,
        locator=chunk.locator,
        temporal_class=TemporalClass(chunk.temporal_class),
        authority_class=AuthorityClass(chunk.authority_class),
        document_sha256=chunk.document_sha256,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        review_provenance=chunk.review_provenance,
        matched_queries=tuple(queries),
        rrf_rank=rank,
        rrf_score=1.0 / rank,
        rerank_rank=rank,
        rerank_score=1.0,
    )


def bind_retrieval_bundle(
    bundle: RetrievalBundle,
    binding: CapabilityBinding,
    chunks_by_id: Mapping[str, ChunkRecord],
) -> tuple[RetrievalBundle, tuple[RetrievalHit, ...]]:
    """Project retrieval onto prevalidated chunks without inventing evidence."""

    if binding.source_mode != "corpus":
        return bundle, tuple(bundle.reranked_hits)
    hits = tuple(
        _bound_hit(chunks_by_id[chunk_id], rank, binding.retrieval_queries)
        for rank, chunk_id in enumerate(binding.chunk_ids, start=1)
    )
    rankings = dict(bundle.rankings)
    rankings["capability_bound"] = [hit.chunk_id for hit in hits]
    return (
        bundle.model_copy(
            update={
                "fused_hits": list(hits),
                "reranked_hits": list(hits),
                "rankings": rankings,
            }
        ),
        hits,
    )


def bind_quote_candidates(packet: EvidencePacket, binding: CapabilityBinding) -> EvidencePacket:
    """Keep only registry-bound exact quotations for quote-ready capabilities."""

    evidence_by_id = {item.evidence_id: item for item in packet.items}
    records = {
        record.claim_id: record
        for record in load_inventory().records
        if record.claim_id in binding.typed_claim_ids
    }
    candidates = [
        candidate
        for candidate in packet.quote_candidates
        if any(
            candidate.evidence_id in evidence_by_id
            and set(evidence_by_id[candidate.evidence_id].primary_chunk_ids).intersection(
                record.source_span_ids
            )
            and _atomic_overlap(candidate.text, record.source_span_text)
            for record in records.values()
        )
    ]
    for quote in binding.exact_quote_texts:
        item = next((row for row in packet.items if quote in row.primary_text), None)
        if item is None:
            raise ValueError(f"{binding.id} quote is absent from its bound evidence packet")
        candidates.append(
            EvidenceQuoteCandidate(
                quote_id=f"{item.evidence_id}Q{len(candidates) + 1}",
                evidence_id=item.evidence_id,
                text=quote,
            )
        )
    return packet.model_copy(update={"quote_candidates": candidates, "conflicts": []})


def _atomic_overlap(left: str, right: str) -> bool:
    normalized_left = " ".join(left.split()).casefold()
    normalized_right = " ".join(right.split()).casefold()
    return min(len(normalized_left), len(normalized_right)) >= 24 and (
        normalized_left in normalized_right or normalized_right in normalized_left
    )
