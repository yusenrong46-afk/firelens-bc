"""The thin orchestration service for search, abstention, generation, and validation."""

from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from uuid import uuid4

from firelens.answering.context import build_evidence_packet, decide_support
from firelens.answering.generate import draft_schema, generation_messages
from firelens.answering.intent import plan_query
from firelens.answering.validate import validate_draft
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    DraftClaim,
    PublicSource,
    QueryRequest,
    ResponseStatus,
    RetrievalBundle,
    SearchResponse,
    SupportStatus,
)
from firelens.errors import ProviderError
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.traces import TraceRecorder


class StaticRAGService:
    def __init__(
        self,
        chunks: Sequence[ChunkRecord],
        *,
        corpus_version: str,
        retrieval: RetrievalPipeline,
        provider: AIProvider,
        config: FireLensConfig,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.chunks = tuple(chunks)
        self.corpus_version = corpus_version
        self.retrieval = retrieval
        self.provider = provider
        self.config = config
        self.trace_recorder = trace_recorder or TraceRecorder(
            config.trace_dir, include_content=config.trace_content
        )

    def _record_ask(
        self,
        request: QueryRequest,
        response: AskResponse,
        *,
        route: str,
        **details: object,
    ) -> AskResponse:
        self.trace_recorder.record(
            response.trace_id,
            question=request.question,
            payload={
                "operation": "ask",
                "route": route,
                "status": response.status.value,
                "reason_code": response.reason_code,
                "error_kind": response.error_kind,
                **details,
            },
        )
        return response

    async def search(self, request: QueryRequest, *, trace_id: str | None = None) -> SearchResponse:
        active_trace_id = trace_id or uuid4().hex
        plan = plan_query(request)
        if not plan.retrieval_requests:
            bundle = RetrievalBundle()
            packet = None
        else:
            bundle = await self.retrieval.search(plan)
            packet = build_evidence_packet(
                plan.normalized_question,
                bundle.reranked_hits,
                self.chunks,
                corpus_version=self.corpus_version,
                config=self.config,
            )
        support = decide_support(plan, packet, bundle)
        response = SearchResponse(
            trace_id=active_trace_id,
            plan=plan,
            retrieval=bundle,
            evidence=[] if packet is None else packet.items,
            support=support,
        )
        self.trace_recorder.record(
            active_trace_id,
            question=request.question,
            payload={
                "operation": "search",
                "route": plan.route.value,
                "support": support.status.value,
                "stage_counts": {
                    "bm25": len(bundle.bm25_hits),
                    "vector": len(bundle.vector_hits),
                    "fused": len(bundle.fused_hits),
                    "reranked": len(bundle.reranked_hits),
                    "evidence": len(response.evidence),
                },
                "stage_rankings": {
                    "bm25": [hit.chunk_id for hit in bundle.bm25_hits],
                    "vector": [hit.chunk_id for hit in bundle.vector_hits],
                    "fused": [hit.chunk_id for hit in bundle.fused_hits],
                    "reranked": [hit.chunk_id for hit in bundle.reranked_hits],
                    "evidence": [item.evidence_id for item in response.evidence],
                },
                "versions": {
                    "corpus": self.corpus_version,
                    "embedding_model": self.config.embedding_model,
                    "rerank_model": self.config.rerank_model,
                    "generation_model": self.config.generation_model,
                },
                "timings_ms": bundle.timings_ms,
                "errors": bundle.errors,
            },
        )
        return response

    async def ask(self, request: QueryRequest) -> AskResponse:
        trace_id = uuid4().hex
        search = await self.search(request, trace_id=trace_id)
        if not search.retrieval.complete and search.plan.retrieval_requests:
            response = AskResponse(
                status=ResponseStatus.ERROR,
                trace_id=trace_id,
                reason_code="retrieval_unavailable",
                error_kind=search.retrieval.errors[0] if search.retrieval.errors else "unknown",
                limitations=search.plan.limitations,
            )
            return self._record_ask(
                request, response, route=search.plan.route.value
            )
        if search.support.status != SupportStatus.ANSWERABLE:
            response = AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=trace_id,
                answer=search.support.explanation,
                limitations=search.plan.limitations,
                reason_code=search.support.reason_code,
            )
            return self._record_ask(
                request, response, route=search.plan.route.value
            )

        packet = build_evidence_packet(
            search.plan.normalized_question,
            search.retrieval.reranked_hits,
            self.chunks,
            corpus_version=self.corpus_version,
            config=self.config,
        )
        started = perf_counter()
        try:
            generated = await self.provider.generate(
                generation_messages(packet), output_schema=draft_schema()
            )
        except ProviderError as exc:
            response = AskResponse(
                status=ResponseStatus.ERROR,
                trace_id=trace_id,
                reason_code="generation_unavailable",
                error_kind=exc.kind.value,
                limitations=packet.limitations,
            )
            return self._record_ask(
                request, response, route=search.plan.route.value
            )
        validation = validate_draft(generated.draft, packet)
        generation_ms = (perf_counter() - started) * 1_000
        if not validation.accepted:
            response = AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=trace_id,
                answer="The generated answer did not pass FireLens validation.",
                limitations=packet.limitations,
                reason_code="draft_validation_failed",
                validation=validation,
            )
            return self._record_ask(
                request,
                response,
                route=search.plan.route.value,
                model=generated.model,
                generation_ms=generation_ms,
                validation=validation.model_dump(mode="json"),
            )
        if generated.draft.answer_type == "abstention":
            response = AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=trace_id,
                answer=generated.draft.answer,
                limitations=generated.draft.limitations,
                reason_code="model_abstained",
                validation=validation,
            )
            return self._record_ask(
                request,
                response,
                route=search.plan.route.value,
                model=generated.model,
                generation_ms=generation_ms,
                validation=validation.model_dump(mode="json"),
            )

        quote_candidates = {
            candidate.quote_id: candidate for candidate in packet.quote_candidates
        }
        public_claims = [
            DraftClaim(
                text=claim.text,
                evidence_ids=list(
                    dict.fromkeys(
                        quote_candidates[quote_id].evidence_id
                        for quote_id in claim.evidence_quote_ids
                    )
                ),
                evidence_quotes=[
                    quote_candidates[quote_id].text
                    for quote_id in claim.evidence_quote_ids
                ],
            )
            for claim in generated.draft.claims
        ]
        cited_ids = {
            evidence_id
            for claim in public_claims
            for evidence_id in claim.evidence_ids
        }
        sources = [
            PublicSource(
                evidence_id=item.evidence_id,
                title=item.title,
                publisher=item.publisher,
                canonical_url=item.canonical_url,
                locator=item.locator,
            )
            for item in packet.items
            if item.evidence_id in cited_ids
        ]
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            answer=" ".join(claim.text.strip() for claim in public_claims),
            claims=public_claims,
            sources=sources,
            limitations=generated.draft.limitations,
            validation=validation,
        )
        return self._record_ask(
            request,
            response,
            route=search.plan.route.value,
            model=generated.model,
            generation_ms=generation_ms,
            validation=validation.model_dump(mode="json"),
            cited_evidence_ids=sorted(cited_ids),
        )
