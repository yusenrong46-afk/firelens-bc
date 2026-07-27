"""Rank-preserving conversion and Reciprocal Rank Fusion."""

from __future__ import annotations

from collections.abc import Sequence

from firelens.contracts import AuthorityClass, RetrievalHit, TemporalClass
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
        temporal_class=TemporalClass(temporal_class),
        authority_class=AuthorityClass(authority_class),
        document_sha256=document_sha256,
        chunk_index=chunk_index,
        text=result.text,
        bm25_rank=result.rank,
        bm25_score=result.score,
    )


def reciprocal_rank_fusion(
    *rankings: Sequence[RetrievalHit],
    rrf_k: int = 60,
    top_k: int = 20,
) -> list[RetrievalHit]:
    if rrf_k < 1 or top_k < 1:
        raise ValueError("RRF parameters must be positive.")
    hits: dict[str, RetrievalHit] = {}
    scores: dict[str, float] = {}

    if not rankings:
        return []

    for ranked in rankings:
        for position, hit in enumerate(ranked, start=1):
            existing = hits.get(hit.chunk_id)
            if existing is None:
                hits[hit.chunk_id] = hit
            else:
                matched_queries = tuple(
                    dict.fromkeys((*existing.matched_queries, *hit.matched_queries))
                )
                bm25_positions = tuple(
                    dict.fromkeys((*existing.bm25_positions, *hit.bm25_positions))
                )
                vector_positions = tuple(
                    dict.fromkeys((*existing.vector_positions, *hit.vector_positions))
                )
                bm25_ranks = [
                    rank for rank in (existing.bm25_rank, hit.bm25_rank) if rank is not None
                ]
                vector_ranks = [
                    rank for rank in (existing.vector_rank, hit.vector_rank) if rank is not None
                ]
                hits[hit.chunk_id] = existing.model_copy(
                    update={
                        "matched_queries": matched_queries,
                        "bm25_positions": bm25_positions,
                        "vector_positions": vector_positions,
                        "bm25_rank": min(bm25_ranks) if bm25_ranks else None,
                        "bm25_score": max(
                            score
                            for score in (existing.bm25_score, hit.bm25_score)
                            if score is not None
                        )
                        if existing.bm25_score is not None or hit.bm25_score is not None
                        else None,
                        "vector_rank": min(vector_ranks) if vector_ranks else None,
                        "vector_score": max(
                            score
                            for score in (existing.vector_score, hit.vector_score)
                            if score is not None
                        )
                        if existing.vector_score is not None or hit.vector_score is not None
                        else None,
                    }
                )
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (rrf_k + position)

    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        hits[chunk_id].model_copy(update={"rrf_rank": rank, "rrf_score": scores[chunk_id]})
        for rank, chunk_id in enumerate(ranked_ids, start=1)
    ]
