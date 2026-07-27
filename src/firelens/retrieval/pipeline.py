"""Inspectable multi-query BM25 + dense + RRF + rerank pipeline."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from time import perf_counter

from firelens.config import FireLensConfig
from firelens.contracts import QueryPlan, RetrievalBundle, RetrievalHit
from firelens.errors import IndexValidationError, ProviderError, ProviderErrorKind
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.retrieval.bm25 import BM25Index
from firelens.retrieval.hybrid import bm25_hit, reciprocal_rank_fusion
from firelens.retrieval.rerank import apply_rerank
from firelens.retrieval.text import render_retrieval_text
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
        retrieval_texts = [
            render_retrieval_text(chunk, config.retrieval_text_strategy) for chunk in chunks
        ]
        self.bm25 = BM25Index(chunks, retrieval_texts=retrieval_texts)
        self.vector_index = vector_index
        self.provider = provider
        self.config = config
        self._query_embedding_cache: OrderedDict[str, list[float]] = OrderedDict()

    def _query_cache_key(self, query: str) -> str:
        normalized_hash = hashlib.sha256(
            " ".join(query.casefold().split()).encode("utf-8")
        ).hexdigest()
        return ":".join(
            (
                self.config.embedding_model,
                self.config.retrieval_text_strategy.value,
                normalized_hash,
            )
        )

    def _cache_vector(self, key: str, vector: list[float]) -> None:
        limit = self.config.query_embedding_cache_size
        if limit == 0:
            return
        self._query_embedding_cache[key] = vector
        self._query_embedding_cache.move_to_end(key)
        while len(self._query_embedding_cache) > limit:
            self._query_embedding_cache.popitem(last=False)

    async def _embed_queries(
        self, queries: Sequence[str]
    ) -> tuple[list[list[float]], dict[str, object], int]:
        vectors: list[list[float] | None] = [None] * len(queries)
        missing_indices: list[int] = []
        keys = [self._query_cache_key(query) for query in queries]
        for index, key in enumerate(keys):
            cached = self._query_embedding_cache.get(key)
            if cached is None:
                missing_indices.append(index)
            else:
                self._query_embedding_cache.move_to_end(key)
                vectors[index] = cached

        usage: dict[str, object] = {"cache_hits": len(queries) - len(missing_indices)}
        attempts = 0
        if missing_indices:
            response = await self.provider.embed([queries[index] for index in missing_indices])
            if len(response.vectors) != len(missing_indices):
                raise ValueError("query embedding count mismatch")
            usage.update(response.usage)
            attempts = response.attempts
            for index, vector in zip(missing_indices, response.vectors, strict=True):
                values = [float(value) for value in vector]
                vectors[index] = values
                self._cache_vector(keys[index], values)
        if any(vector is None for vector in vectors):
            raise ValueError("query embedding batch was incomplete")
        return [vector for vector in vectors if vector is not None], usage, attempts

    @staticmethod
    def _unique_stage_hits(rankings: Sequence[Sequence[RetrievalHit]]) -> list[RetrievalHit]:
        by_id: dict[str, RetrievalHit] = {}
        order: list[str] = []
        for ranking in rankings:
            for hit in ranking:
                existing = by_id.get(hit.chunk_id)
                if existing is None:
                    by_id[hit.chunk_id] = hit
                    order.append(hit.chunk_id)
                    continue
                by_id[hit.chunk_id] = existing.model_copy(
                    update={
                        "matched_queries": tuple(
                            dict.fromkeys((*existing.matched_queries, *hit.matched_queries))
                        ),
                        "bm25_positions": tuple(
                            dict.fromkeys((*existing.bm25_positions, *hit.bm25_positions))
                        ),
                        "vector_positions": tuple(
                            dict.fromkeys((*existing.vector_positions, *hit.vector_positions))
                        ),
                    }
                )
        return [by_id[chunk_id] for chunk_id in order]

    async def search(self, plan: QueryPlan) -> RetrievalBundle:
        if not plan.retrieval_requests:
            return RetrievalBundle(complete=False, errors=["no_retrieval_request"])
        queries = [request.query for request in plan.retrieval_requests]
        timings: dict[str, float] = {}
        provider_usage: dict[str, dict] = {}
        provider_attempts: dict[str, int] = {}
        provider_models: dict[str, str] = {}
        stage_rankings: dict[str, list[str]] = {}

        started = perf_counter()
        bm25_rankings: list[list[RetrievalHit]] = []
        for query_number, query in enumerate(queries, start=1):
            ranking: list[RetrievalHit] = []
            for result in self.bm25.search(query, top_k=self.config.bm25_top_k):
                chunk = self.by_id[result.chunk_id]
                ranking.append(
                    bm25_hit(
                        result,
                        authority_class=chunk.authority_class,
                        temporal_class=chunk.temporal_class,
                        document_sha256=chunk.document_sha256,
                        chunk_index=chunk.chunk_index,
                    ).model_copy(
                        update={
                            "matched_queries": (query,),
                            "bm25_positions": (result.rank,),
                        }
                    )
                )
            bm25_rankings.append(ranking)
            stage_rankings[f"bm25:{query_number}"] = [hit.chunk_id for hit in ranking]
        timings["bm25"] = (perf_counter() - started) * 1_000
        bm25_hits = self._unique_stage_hits(bm25_rankings)

        try:
            started = perf_counter()
            embedded, embedding_usage, embedding_attempts = await self._embed_queries(queries)
            vector_rankings: list[list[RetrievalHit]] = []
            for query_number, (query, vector) in enumerate(
                zip(queries, embedded, strict=True), start=1
            ):
                ranking = [
                    hit.model_copy(
                        update={
                            "matched_queries": (query,),
                            "vector_positions": (hit.vector_rank,)
                            if hit.vector_rank is not None
                            else (),
                        }
                    )
                    for hit in self.vector_index.search(vector, top_k=self.config.vector_top_k)
                ]
                vector_rankings.append(ranking)
                stage_rankings[f"vector:{query_number}"] = [hit.chunk_id for hit in ranking]
            provider_usage["embedding"] = embedding_usage
            provider_attempts["embedding"] = embedding_attempts
            provider_models["embedding"] = self.config.embedding_model
            timings["vector"] = (perf_counter() - started) * 1_000
        except ProviderError as exc:
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                rankings=stage_rankings,
                complete=False,
                errors=[exc.kind.value],
                timings_ms=timings,
                provider_usage=provider_usage,
                provider_attempts=provider_attempts,
                provider_models=provider_models,
            )
        except (IndexValidationError, ValueError):
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                rankings=stage_rankings,
                complete=False,
                errors=[ProviderErrorKind.INVALID_RESPONSE.value],
                timings_ms=timings,
                provider_usage=provider_usage,
                provider_attempts=provider_attempts,
                provider_models=provider_models,
            )

        vector_hits = self._unique_stage_hits(vector_rankings)
        started = perf_counter()
        fused_hits = reciprocal_rank_fusion(
            *bm25_rankings,
            *vector_rankings,
            rrf_k=self.config.rrf_k,
            top_k=self.config.fused_top_k,
        )
        timings["fusion"] = (perf_counter() - started) * 1_000
        stage_rankings["fused"] = [hit.chunk_id for hit in fused_hits]
        if not fused_hits:
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                fused_hits=[],
                reranked_hits=[],
                rankings=stage_rankings,
                timings_ms=timings,
                provider_usage=provider_usage,
                provider_attempts=provider_attempts,
                provider_models=provider_models,
            )

        try:
            started = perf_counter()
            response = await self.provider.rerank(
                plan.normalized_question,
                [
                    render_retrieval_text(
                        self.by_id[hit.chunk_id], self.config.retrieval_text_strategy
                    )
                    for hit in fused_hits
                ],
                top_n=min(self.config.rerank_top_k, len(fused_hits)),
            )
            reranked_hits = apply_rerank(fused_hits, response)
            provider_usage["rerank"] = response.usage
            provider_attempts["rerank"] = response.attempts
            provider_models["rerank"] = response.model
            timings["rerank"] = (perf_counter() - started) * 1_000
            stage_rankings["reranked"] = [hit.chunk_id for hit in reranked_hits]
        except ProviderError as exc:
            return RetrievalBundle(
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                fused_hits=fused_hits,
                rankings=stage_rankings,
                complete=False,
                errors=[exc.kind.value],
                timings_ms=timings,
                provider_usage=provider_usage,
                provider_attempts=provider_attempts,
                provider_models=provider_models,
            )

        return RetrievalBundle(
            bm25_hits=bm25_hits,
            vector_hits=vector_hits,
            fused_hits=fused_hits,
            reranked_hits=reranked_hits,
            rankings=stage_rankings,
            timings_ms=timings,
            provider_usage=provider_usage,
            provider_attempts=provider_attempts,
            provider_models=provider_models,
        )
