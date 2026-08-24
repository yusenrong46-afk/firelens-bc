from firelens.answering.intent import plan_query
from firelens.answering.request_facets import contents_request_facet, requests_contents
from firelens.answering.service import StaticRAGService
from firelens.contracts import QueryRequest


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


def test_long_non_contents_guidance_preserves_the_focused_question_aspect() -> None:
    question = (
        "Lorem ipsum filler line. " * 40
        + "What's the difference between an evacuation alert and an evacuation order?"
    )

    plan = StaticRAGService._reviewed_guidance_plan(plan_query(QueryRequest(question=question)))

    assert plan.required_aspects == [
        "What's the difference between an evacuation alert and an evacuation order?"
    ]
