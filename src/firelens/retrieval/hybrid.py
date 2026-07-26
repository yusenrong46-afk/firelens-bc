"""Rank-preserving conversion and Reciprocal Rank Fusion."""

from __future__ import annotations

from collections.abc import Sequence

from firelens.contracts import RetrievalHit
from firelens.retrieval.bm25 import RetrievalResult


def bm25_hit(
    result: RetrievalResult,
    *,
    authority_class: str,
    temporal_class: str,
    document_sha256: str,
    chunk_index: int,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=result.chunk_id,
        parent_record_id=result.parent_record_id,
        source_id=result.source_id,
        title=result.title,
        publisher=result.publisher,
        canonical_url=result.canonical_url,
        page_number=result.page_number,
        section_title=result.section_title,
        locator=result.locator,
        temporal_class=temporal_class,
        authority_class=authority_class,
        document_sha256=document_sha256,
        chunk_index=chunk_index,
        text=result.text,
        bm25_rank=result.rank,
        bm25_score=result.score,
    )


def reciprocal_rank_fusion(
    bm25_hits: Sequence[RetrievalHit],
    vector_hits: Sequence[RetrievalHit],
    *,
    rrf_k: int = 60,
    top_k: int = 20,
) -> list[RetrievalHit]:
    if rrf_k < 1 or top_k < 1:
        raise ValueError("RRF parameters must be positive.")
    hits: dict[str, RetrievalHit] = {}
    scores: dict[str, float] = {}

    for ranked in (bm25_hits, vector_hits):
        for position, hit in enumerate(ranked, start=1):
            existing = hits.get(hit.chunk_id)
            if existing is None:
                hits[hit.chunk_id] = hit
            else:
                hits[hit.chunk_id] = existing.model_copy(
                    update={
                        "bm25_rank": existing.bm25_rank or hit.bm25_rank,
                        "bm25_score": existing.bm25_score
                        if existing.bm25_score is not None
                        else hit.bm25_score,
                        "vector_rank": existing.vector_rank or hit.vector_rank,
                        "vector_score": existing.vector_score
                        if existing.vector_score is not None
                        else hit.vector_score,
                    }
                )
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (rrf_k + position)

    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        hits[chunk_id].model_copy(update={"rrf_rank": rank, "rrf_score": scores[chunk_id]})
        for rank, chunk_id in enumerate(ranked_ids, start=1)
    ]
