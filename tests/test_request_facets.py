from pathlib import Path

from firelens.answering.context import _select_evidence_hits
from firelens.answering.intent import plan_query
from firelens.answering.request_facets import contents_request_facet, requests_contents
from firelens.answering.service import StaticRAGService
from firelens.contracts import QueryRequest
from firelens.publication.comparison_targets import ALERT_ORDER_ATOMIC_TARGETS
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.vector import retrieval_hit_from_chunk


def test_contents_facet_derives_container_focused_retrieval_query() -> None:
    facet = contents_request_facet(
        "What basic items should I put in a wildfire grab-and-go bag?"
    )

    assert facet is not None
    assert facet.container == "wildfire grab-and-go bag"
    assert facet.retrieval_query == "wildfire grab-and-go bag contents checklist"


def test_contents_facet_is_generic_for_emergency_kits() -> None:
    belongs = contents_request_facet("What belongs inside an emergency kit?")
    includes = contents_request_facet("What can a household emergency kit include?")

    assert belongs is not None
    assert belongs.retrieval_query == "emergency kit contents checklist"
    assert includes is not None
    assert includes.retrieval_query == "household emergency kit contents checklist"


def test_contents_facet_covers_natural_contents_phrasings() -> None:
    cases = {
        "What should be in an emergency kit?": "emergency kit contents checklist",
        "What do I need in a grab-and-go bag?": "grab-and-go bag contents checklist",
        "List items for a wildfire grab-and-go bag.": (
            "wildfire grab-and-go bag contents checklist"
        ),
        "Name the supplies inside an evacuation supply box.": (
            "evacuation supply box contents checklist"
        ),
    }

    for question, expected in cases.items():
        facet = contents_request_facet(question)
        assert facet is not None, question
        assert facet.retrieval_query == expected
        assert requests_contents(question) is True


def test_build_question_is_not_a_contents_request() -> None:
    question = "Should I build a grab-and-go bag?"

    assert contents_request_facet(question) is None
    assert requests_contents(question) is False


def test_long_contents_question_uses_bounded_container_as_its_required_aspect() -> None:
    question = (
        "Background context that must not become the retrieval target. " * 10
        + "What basic items should I put in a wildfire grab-and-go bag?"
    )

    plan = StaticRAGService._reviewed_guidance_plan(plan_query(QueryRequest(question=question)))

    assert plan.required_aspects == ["wildfire grab-and-go bag contents checklist"]
    assert plan.retrieval_requests[0].query == ("wildfire grab-and-go bag contents checklist")


def test_alert_order_comparison_retrieves_both_atomic_meanings() -> None:
    question = "What is the difference between an evacuation alert and an evacuation order?"
    plan = StaticRAGService._reviewed_guidance_plan(plan_query(QueryRequest(question=question)))
    queries = [request.query for request in plan.retrieval_requests]

    assert plan.required_aspects == [
        "evacuation alert meaning",
        "evacuation order meaning",
    ]
    assert "evacuation alert meaning" in queries
    assert "evacuation order meaning" in queries


def test_long_non_contents_guidance_retrieves_alert_and_order_meanings() -> None:
    question = (
        "Lorem ipsum filler line. " * 40
        + "What's the difference between an evacuation alert and an evacuation order?"
    )

    plan = StaticRAGService._reviewed_guidance_plan(plan_query(QueryRequest(question=question)))
    queries = [request.query for request in plan.retrieval_requests]

    assert plan.required_aspects == [
        "evacuation alert meaning",
        "evacuation order meaning",
    ]
    assert "evacuation alert meaning" in queries
    assert "evacuation order meaning" in queries


_ALERT_CHUNK = "preparedbc_wildfire_guide:page:10:chunk:4"
_ORDER_CHUNK = "preparedbc_wildfire_guide:page:11:chunk:2"


def test_atomic_aspect_reservation_keeps_fused_hit_dropped_by_rerank() -> None:
    by_id = {
        chunk.chunk_id: chunk
        for chunk in load_chunk_records(
            Path(__file__).resolve().parents[1]
            / "data/processed/firelens_static_corpus.chunks.jsonl"
        )
    }
    alert = retrieval_hit_from_chunk(by_id[_ALERT_CHUNK])
    order = retrieval_hit_from_chunk(by_id[_ORDER_CHUNK])
    fillers = [
        retrieval_hit_from_chunk(by_id[chunk_id])
        for chunk_id in (
            "preparedbc_wildfire_guide:page:12:chunk:1",
            "preparedbc_wildfire_guide:page:7:chunk:1",
            "preparedbc_wildfire_guide:page:11:chunk:3",
            "preparedbc_wildfire_guide:page:10:chunk:3",
        )
    ]
    reranked = [*fillers, order]
    fused = [alert, *reranked]
    selected = _select_evidence_hits(
        "What is the difference between an evacuation alert and an evacuation order?",
        reranked,
        limit=5,
        selection_aspects=ALERT_ORDER_ATOMIC_TARGETS,
        coverage_hits=fused,
    )
    ids = {hit.chunk_id for hit in selected}

    assert len(selected) <= 5
    assert _ALERT_CHUNK in ids
    assert _ORDER_CHUNK in ids
    assert _ALERT_CHUNK not in {hit.chunk_id for hit in reranked}


def test_atomic_aspect_reservation_does_not_invent_unretrieved_alert() -> None:
    by_id = {
        chunk.chunk_id: chunk
        for chunk in load_chunk_records(
            Path(__file__).resolve().parents[1]
            / "data/processed/firelens_static_corpus.chunks.jsonl"
        )
    }
    order = retrieval_hit_from_chunk(by_id[_ORDER_CHUNK])
    selected = _select_evidence_hits(
        "What is the difference between an evacuation alert and an evacuation order?",
        [order],
        limit=5,
        selection_aspects=ALERT_ORDER_ATOMIC_TARGETS,
        coverage_hits=[order],
    )

    assert {hit.chunk_id for hit in selected} == {_ORDER_CHUNK}
