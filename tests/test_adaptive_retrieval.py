from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from rag_helpers import make_chunk, write_test_corpus

from firelens.answering.adaptive_retrieval import (
    merge_hits,
    missing_supported_aspects,
    normalize_query,
    refine_if_needed,
    second_cycle_plan,
)
from firelens.answering.context import build_evidence_packet
from firelens.contracts import QueryPlan, QueryRoute, RetrievalBundle, RetrievalRequest
from firelens.retrieval.vector import retrieval_hit_from_chunk


def _plan(*aspects: str) -> QueryPlan:
    return QueryPlan(
        original_question="kit and smoke",
        normalized_question="kit and smoke",
        route=QueryRoute.RELATED,
        retrieval_requests=[RetrievalRequest(query=aspects[0])],
        required_aspects=list(aspects),
    )


def test_normalize_and_merge_are_deterministic() -> None:
    first = make_chunk("a", "water kit")
    second = make_chunk("b", "smoke mask", parent="b")
    hits = [
        retrieval_hit_from_chunk(first, rerank_rank=1),
        retrieval_hit_from_chunk(second, rerank_rank=2),
        retrieval_hit_from_chunk(first, rerank_rank=3),
    ]

    assert normalize_query("  Kit   AND Smoke ") == "kit and smoke"
    assert [hit.chunk_id for hit in merge_hits(hits)] == ["a", "b"]


def test_second_cycle_skips_identical_queries() -> None:
    plan = _plan("water kit", "smoke mask")
    follow = second_cycle_plan(plan, ["water kit", "smoke mask"], {"water kit"})

    assert follow is not None
    assert [request.query for request in follow.retrieval_requests] == ["smoke mask"]


def test_adaptive_second_cycle_fills_missing_aspect() -> None:
    kit = make_chunk("a", "Include water in a grab-and-go bag.")
    smoke = make_chunk("b", "N95 masks reduce wildfire smoke exposure.", parent="b")
    with tempfile.TemporaryDirectory() as directory:
        config = write_test_corpus(Path(directory), [kit, smoke]).model_copy(
            update={"retrieval_strategy": "adaptive_v1"}
        )
        first_bundle = RetrievalBundle(
            reranked_hits=[retrieval_hit_from_chunk(kit, rerank_rank=1)]
        )
        first_packet = build_evidence_packet(
            "kit and smoke",
            first_bundle.reranked_hits,
            [kit, smoke],
            corpus_version="test-corpus.v1",
            config=config,
        )
        plan = _plan("water kit", "smoke mask")
        assert missing_supported_aspects(plan, first_packet) == ["smoke mask"]

        class SecondSearch:
            async def search(self, follow: QueryPlan) -> RetrievalBundle:
                assert follow.retrieval_requests[0].query == "smoke mask"
                return RetrievalBundle(
                    reranked_hits=[retrieval_hit_from_chunk(smoke, rerank_rank=1)]
                )

        outcome = asyncio.run(
            refine_if_needed(
                plan=plan,
                request_queries=("water kit",),
                first_bundle=first_bundle,
                first_packet=first_packet,
                chunks=(kit, smoke),
                corpus_version="test-corpus.v1",
                config=config,
                searcher=SecondSearch(),
            )
        )

        assert outcome.refined is True
        assert outcome.cycles == 2
        assert {hit.chunk_id for hit in outcome.bundle.reranked_hits} == {"a", "b"}


def test_baseline_strategy_does_not_issue_a_second_cycle() -> None:
    kit = make_chunk("a", "Include water in a grab-and-go bag.")
    with tempfile.TemporaryDirectory() as directory:
        config = write_test_corpus(Path(directory), [kit])
        bundle = RetrievalBundle(reranked_hits=[retrieval_hit_from_chunk(kit, rerank_rank=1)])
        packet = build_evidence_packet(
            "kit and smoke",
            bundle.reranked_hits,
            [kit],
            corpus_version="test-corpus.v1",
            config=config,
        )

        class Forbidden:
            async def search(self, plan: QueryPlan) -> RetrievalBundle:
                raise AssertionError(plan)

        outcome = asyncio.run(
            refine_if_needed(
                plan=_plan("water kit", "smoke mask"),
                request_queries=("water kit",),
                first_bundle=bundle,
                first_packet=packet,
                chunks=(kit,),
                corpus_version="test-corpus.v1",
                config=config,
                searcher=Forbidden(),
            )
        )

        assert outcome.refined is False
        assert outcome.cycles == 1
