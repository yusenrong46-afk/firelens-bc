"""Inspectable BM25 + dense + RRF + rerank retrieval pipeline."""

from __future__ import annotations

from time import perf_counter
from typing import Sequence

from firelens.config import FireLensConfig
from firelens.contracts import QueryPlan, RetrievalBundle
from firelens.errors import IndexValidationError, ProviderError, ProviderErrorKind
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.retrieval.bm25 import BM25Index
from firelens.retrieval.hybrid import bm25_hit, reciprocal_rank_fusion
from firelens.retrieval.rerank import apply_rerank
from firelens.retrieval.vector import VectorIndex


class RetrievalPipeline:
    def __init__(
        self,
        chunks: Sequence[ChunkRecord],
        *,
        vector_index: VectorIndex,
        provider: AIProvider,
        config: FireLensConfig,
    ) -> None:
        self.chunks = tuple(chunks)
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.bm25 = BM25Index(chunks)
        self.vector_index = vector_index
        self.provider = provider
        self.config = config

    async def search(self, plan: QueryPlan) -> RetrievalBundle:
        if not plan.retrieval_requests:
            return RetrievalBundle(complete=False, errors=["no_retrieval_request"])
        query = plan.retrieval_requests[0].query
        timings: dict[str, float] = {}

        started = perf_counter()
        raw_bm25 = self.bm25.search(query, top_k=self.config.bm25_top_k)
        bm25_hits = []
        for result in raw_bm25:
            chunk = self.by_id[result.chunk_id]
            bm25_hits.append(
                bm25_hit(
                    result,
                    authority_class=chunk.authority_class,
                    temporal_class=chunk.temporal_class,
                    document_sha256=chunk.document_sha256,
                    chunk_index=chunk.chunk_index,
                )
            )
        timings["bm25"] = (perf_counter() - started) * 1_000

        try:
            started = perf_counter()
            embedded = await self.provider.embed([query])
            if len(embedded.vectors) != 1:
                raise ValueError("query embedding count mismatch")
            vector_hits = self.vector_index.search(
                embedded.vectors[0], top_k=self.config.vector_top_k
            )
            timings["vector"] = (perf_counter() - started) * 1_000
        except ProviderError as exc:
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                complete=False,
                errors=[exc.kind.value],
                timings_ms=timings,
            )
        except (IndexValidationError, ValueError):
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                complete=False,
                errors=[ProviderErrorKind.INVALID_RESPONSE.value],
                timings_ms=timings,
            )

        started = perf_counter()
        fused_hits = reciprocal_rank_fusion(
            bm25_hits,
            vector_hits,
            rrf_k=self.config.rrf_k,
            top_k=self.config.fused_top_k,
        )
        timings["fusion"] = (perf_counter() - started) * 1_000

        try:
            started = perf_counter()
            response = await self.provider.rerank(
                query,
                [hit.text for hit in fused_hits],
                top_n=min(self.config.rerank_top_k, len(fused_hits)),
            )
            reranked_hits = apply_rerank(fused_hits, response)
            timings["rerank"] = (perf_counter() - started) * 1_000
        except ProviderError as exc:
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                fused_hits=fused_hits,
                complete=False,
                errors=[exc.kind.value],
                timings_ms=timings,
            )

        return RetrievalBundle(
            bm25_hits=bm25_hits,
            vector_hits=vector_hits,
            fused_hits=fused_hits,
            reranked_hits=reranked_hits,
            timings_ms=timings,
        )
