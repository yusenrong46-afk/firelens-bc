"""Current-live and mixed paraphrases must own live scope or name the unresolved clause."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import HttpUrl

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import AgentGeography, AgentRequestMode, plan_agent_request
from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    static_guidance_fragment,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.request_grammar import parse_request_facets
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    AnswerSectionKind,
    AskResponse,
    ClaimSupport,
    EvidenceStatus,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    MapContext,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.compiler import background_authority, explanation_authority

CURRENT_LIVE = (
    "What's burning in Okanagan today?",
    "Give me the Kelowna wildfire situation",
    "Where are fires across the Okanagan?",
)
MIXED_LIVE = (
    "Give me the Kelowna wildfire situation and what belongs in an emergency kit",
    "What's burning in Okanagan today, and what belongs in an emergency kit?",
    "Where are fires across the Okanagan, plus what belongs in an emergency kit?",
)
CANONICAL_LIVE = "Where are the current wildfires in Kelowna?"
CANONICAL_MIXED = "Are there fires near Kelowna today, and what belongs in an emergency kit?"
CANONICAL_STATIC = "What belongs in an emergency kit?"
REQUIRED_MIXED_SCOPE_CASES = (
    "Current fires across British Columbia, plus smoke readiness guidance.",
    "Near Prince George, current fires plus wildfire smoke health guidance plus "
    "emergency kit advice.",
)


def _incident() -> LiveResult:
    timestamp = datetime(2026, 8, 15, tzinfo=UTC)
    return LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/incidents/7",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name="Mountain Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


class RecordingLive:
    def __init__(self) -> None:
        self.map_calls = 0
        self.nearby_calls = 0
        self.nearby_label: str | None = None
        results = [_incident()]
        self.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 15, tzinfo=UTC),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def map_results(self, *, layers: tuple[LiveResultKind, ...]) -> LiveMapResponse:
        del layers
        self.map_calls += 1
        return self.response

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.nearby_calls += 1
        self.nearby_label = getattr(location, "label", None)
        return type(
            "Nearby",
            (),
            {
                "results": self.response.results,
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": None,
            },
        )()

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        return 49.89, -119.49


class RecordingStatic:
    provider = None

    def __init__(self, response: AskResponse) -> None:
        self.response = response
        self.questions: list[str] = []

    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        self.questions.append(request.question)
        return self.response


def _background() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Pack water and copies of important documents.",
        evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
        publication=background_authority(),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="b" * 32,
        response_mode=ResponseMode.BACKGROUND,
        answer=claim.text,
        claims=[claim],
        limitations=[BACKGROUND_LIMITATION],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
    )


def _grounded() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Include water, food, and copies of documents in a grab-and-go bag.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Include water, food, and copies")],
        publication=explanation_authority(),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="g" * 32,
        response_mode=ResponseMode.GROUNDED,
        answer=claim.text,
        claims=[claim],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="PreparedBC guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/preparedbc"),
                locator="Section 1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Include water, food, and copies",
                context_text="Include water, food, and copies of documents.",
            )
        ],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
    )


def _named_token(question: str) -> str:
    lowered = question.casefold()
    return "kelowna" if "kelowna" in lowered else "okanagan"


def _public_text(response: AskResponse) -> str:
    return " ".join([response.answer or "", *response.limitations])


@pytest.mark.parametrize("question", CURRENT_LIVE)
def test_current_live_paraphrases_own_live_layers(question: str) -> None:
    plan = plan_query(QueryRequest(question=question))
    assert plan.route == QueryRoute.LIVE
    assert live_layers_for_question(question)


def test_canonical_named_place_and_static_controls() -> None:
    live = plan_query(QueryRequest(question=CANONICAL_LIVE))
    location = coarse_location_from_question(CANONICAL_LIVE)
    assert live.route == QueryRoute.LIVE
    assert live_layers_for_question(CANONICAL_LIVE)
    assert location is not None and location.label.casefold() == "kelowna"
    static = plan_query(QueryRequest(question=CANONICAL_STATIC))
    assert static.route == QueryRoute.RELATED
    assert live_layers_for_question(CANONICAL_STATIC) == ()


@pytest.mark.parametrize(
    "question",
    (
        "Show a map of fire-prone ecosystems.",
        "Give me fire safety education for students.",
    ),
)
def test_agent_plan_rejects_bare_fire_topic_commands_as_live_records(
    question: str,
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route != QueryRoute.LIVE
    assert plan.live_layers == ()
    assert plan.location_label is None
    assert plan.tool_calls == ()


@pytest.mark.parametrize(
    "question",
    (
        "Is there a safe distance from a wildfire?",
        "Can you explain current wildfire policy changes in British Columbia?",
        "Is there a standard separation people should keep from a wildfire?",
        "Could you summarize current wildfire legislation for homeowners?",
        "Where is wildfire prevention taught in B.C.?",
        "Are there lessons about wildfire ecology in schools?",
        "Show a comparison of wildfire policies.",
        "Research on current wildfires in British Columbia.",
    ),
)
def test_static_fire_topic_families_never_authorize_live_tools(question: str) -> None:
    """Static wildfire vocabulary cannot substitute for a live-record object."""

    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route != QueryRoute.LIVE
    assert plan.live_layers == ()
    assert plan.location_label is None
    assert plan.tool_calls == ()


@pytest.mark.parametrize(
    "question",
    (
        "Could you show current fires near Nelson?",
        "Are there any active fires around Quesnel?",
        "Is there a Pine Creek Fire near Merritt?",
        "What official fires are listed by BC Wildfire Service?",
        "Wildfire status for the Okanagan.",
        "Current fires across British Columbia.",
    ),
)
def test_positive_live_grammar_families_authorize_bounded_fire_tools(
    question: str,
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.LIVE
    assert plan.live_layers
    assert [call.name.value for call in plan.tool_calls] == ["list_official_fires"]


@pytest.mark.parametrize(
    "question",
    (
        "What is its present status?",
        "Put this fire on the map.",
        "Show the selected perimeter.",
        "And the perimeter?",
    ),
)
def test_selected_record_followups_cannot_widen_to_a_province_list(question: str) -> None:
    plan = plan_agent_request(
        QueryRequest(
            question=question,
            context=MapContext(selected_live_result_id="incident:boundary-17"),
        )
    )

    assert plan.mode == AgentRequestMode.SELECTED
    assert plan.geography == AgentGeography.SELECTED_RECORD
    assert [call.name.value for call in plan.tool_calls] == ["get_official_fire"]
    assert plan.tool_calls[0].as_arguments() == {"result_id": "incident:boundary-17"}


def test_agent_plan_does_not_promote_a_for_audience_to_geography() -> None:
    plan = plan_agent_request(QueryRequest(question="Show current wildfires for students."))

    assert plan.route == QueryRoute.LIVE
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.location_label is None
    assert all(dict(call.arguments).get("place_label") is None for call in plan.tool_calls)


@pytest.mark.parametrize("question", MIXED_LIVE)
def test_mixed_paraphrases_keep_a_live_owned_plan(question: str) -> None:
    plan = plan_query(QueryRequest(question=question))
    assert static_guidance_fragment(question)
    assert plan.route == QueryRoute.LIVE
    assert live_layers_for_question(question)


def test_canonical_mixed_plan_owns_live_layers_and_guidance() -> None:
    plan = plan_query(QueryRequest(question=CANONICAL_MIXED))
    location = coarse_location_from_question(CANONICAL_MIXED)
    assert plan.route == QueryRoute.LIVE
    assert live_layers_for_question(CANONICAL_MIXED)
    assert static_guidance_fragment(CANONICAL_MIXED)
    assert location is not None and location.label.casefold() == "kelowna"


@pytest.mark.parametrize("question", REQUIRED_MIXED_SCOPE_CASES)
def test_required_mixed_scope_cases_keep_live_and_reviewed_guidance(question: str) -> None:
    plan = plan_query(QueryRequest(question=question))
    facets = parse_request_facets(question)

    assert plan.route == QueryRoute.LIVE
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )
    assert facets.has_current_live_fire
    assert facets.non_live_clauses


def test_public_agent_keeps_accepted_background_with_live_records() -> None:
    question = MIXED_LIVE[0]
    live = RecordingLive()
    static = RecordingStatic(_background())
    response = asyncio.run(
        FireLensAgent(cast(Any, static), LiveAnswerCoordinator(cast(Any, live))).answer(
            QueryRequest(question=question)
        )
    ).response
    kinds = {section.kind for section in response.answer_sections}
    assert response.response_mode == ResponseMode.MIXED
    assert response.live_results and response.claims
    assert AnswerSectionKind.CURRENT_RECORDS in kinds
    assert AnswerSectionKind.GENERAL_BACKGROUND in kinds
    assert BACKGROUND_LIMITATION in response.limitations
    assert response.evidence == []
    assert live.nearby_calls == 1
    assert live.map_calls == 0
    assert (live.nearby_label or "").casefold() == "kelowna"
    assert static.questions == ["what belongs in an emergency kit"]


def test_public_agent_keeps_rejected_static_clause_visible_as_a_limitation() -> None:
    rejected = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="r" * 32,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer="No reviewed passage established that clause.",
        limitations=["No reviewed passage established that clause."],
        validation=ValidationReport(
            accepted=False,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=False,
            policy_valid=True,
        ),
    )
    static = RecordingStatic(rejected)
    response = asyncio.run(
        FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, RecordingLive())),
        ).answer(QueryRequest(question=CANONICAL_MIXED))
    ).response

    assert response.response_mode == ResponseMode.LIVE
    assert any("non-live clause" in item for item in response.limitations)
    assert static.questions == ["what belongs in an emergency kit"]


def test_mixed_answer_keeps_reviewed_claim_out_of_current_record_section() -> None:
    live = RecordingLive()
    static_response = _grounded()
    response = asyncio.run(
        FireLensAgent(
            cast(Any, RecordingStatic(static_response)),
            LiveAnswerCoordinator(cast(Any, live)),
        ).answer(QueryRequest(question=CANONICAL_MIXED))
    ).response
    current = next(
        section
        for section in response.answer_sections
        if section.kind == AnswerSectionKind.CURRENT_RECORDS
    )
    reviewed = next(
        section
        for section in response.answer_sections
        if section.kind == AnswerSectionKind.REVIEWED_GUIDANCE
    )

    assert reviewed.text == static_response.claims[0].text
    assert static_response.claims[0].text not in current.text


def test_canonical_mixed_keeps_both_halves_with_separate_authority() -> None:
    live = RecordingLive()
    response = asyncio.run(
        LiveAnswerCoordinator(cast(Any, live)).answer(
            QueryRequest(question=CANONICAL_MIXED), _grounded()
        )
    )
    kinds = {section.kind for section in response.answer_sections}
    assert response.response_mode == ResponseMode.MIXED
    assert response.live_results and response.claims
    assert AnswerSectionKind.CURRENT_RECORDS in kinds
    assert AnswerSectionKind.REVIEWED_GUIDANCE in kinds
    assert live.nearby_calls == 1
    assert (live.nearby_label or "").casefold() == "kelowna"


@pytest.mark.parametrize(
    ("question", "place", "static_subrequest"),
    (
        (
            "Show active fires near Nelson, plus a plain-language comparison of "
            "an evacuation alert and order.",
            "Nelson",
            "a plain-language comparison of an evacuation alert and order",
        ),
        (
            "Thompson wildfire situation and a basic evacuation packing checklist.",
            "Thompson",
            "a basic evacuation packing checklist",
        ),
    ),
)
def test_conversational_mixed_noun_phrases_create_two_bounded_execution_lanes(
    question: str, place: str, static_subrequest: str
) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == place
    assert plan.live_layers == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )
    assert plan.static_subrequest == static_subrequest
    assert len(plan.tool_calls) == 2
