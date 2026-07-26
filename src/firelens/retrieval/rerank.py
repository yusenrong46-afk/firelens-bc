"""Validate provider indices and map rerank results to immutable local hits."""

from __future__ import annotations

from collections.abc import Sequence

from firelens.contracts import RetrievalHit, RerankResponse
from firelens.errors import ProviderError, ProviderErrorKind


def apply_rerank(
    hits: Sequence[RetrievalHit], response: RerankResponse
) -> list[RetrievalHit]:
    seen: set[int] = set()
    reranked: list[RetrievalHit] = []
    for rank, result in enumerate(response.results, start=1):
        if result.index in seen or result.index >= len(hits):
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "Reranker returned invalid candidate indices.",
            )
        seen.add(result.index)
        reranked.append(
            hits[result.index].model_copy(
                update={
                    "rerank_rank": rank,
                    "rerank_score": result.relevance_score,
                }
            )
        )
    return reranked

