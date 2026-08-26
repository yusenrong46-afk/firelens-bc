"""Generative invariants for the application-owned request intent automaton."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import HttpUrl

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import AgentGeography, AgentRequestMode, plan_agent_request
from firelens.answering.intent import live_layers_for_question, static_guidance_fragment
from firelens.answering.intent_automaton import (
    ClauseIntentKind,
    TemporalScope,
    parse_request_intent,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    AnswerSectionKind,
    AskResponse,
    ClaimSupport,
    CoarseResolvedLocation,
    EvidenceStatus,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.compiler import explanation_authority

PLACES = st.sampled_from(("Kelowna", "Penticton", "Kamloops", "Prince George"))
CURRENT_CUES = st.sampled_from(("today", "right now", "at present", "currently"))
LIVE_FORMS = st.sampled_from(
    (
        "Which fires are listed near {place} {time}?",
        "Pull the wildfire records for {place} {time}.",
        "What is burning around {place} {time}?",
        "Give me the current fire report for {place}.",
    )
)


@given(place=PLACES, time=CURRENT_CUES, template=LIVE_FORMS)
def test_live_record_templates_have_one_typed_owner(
    place: str, time: str, template: str
) -> None:
    question = template.format(place=place, time=time)
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert parsed.live_layers
    assert all(
        clause.kind == ClauseIntentKind.LIVE_RECORDS
        for clause in parsed.clauses
        if clause.is_live
    )
    assert coarse_location_from_question(question) is not None

    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.location_label == place
    assert plan.live_layers


@given(
    place=PLACES,
    historical=st.sampled_from(("last season", "in 2020", "historically", "yesterday")),
    command=st.sampled_from(("Show", "Map", "List", "Summarize")),
)
def test_noncurrent_time_dominates_record_command(
    place: str, historical: str, command: str
) -> None:
    question = f"{command} the wildfires near {place} {historical}."
    parsed = parse_request_intent(question)

    assert not parsed.has_live_records
    assert parsed.temporal_scope == TemporalScope.NONCURRENT
    assert live_layers_for_question(question) == ()
    assert plan_agent_request(QueryRequest(question=question)).mode == AgentRequestMode.STATIC


@pytest.mark.parametrize(
    ("question", "place", "static_fragment"),
    (
        (
            "For Kelowna, pull today's listed fires; also give me emergency-kit basics.",
            "Kelowna",
            "give me emergency-kit basics",
        ),
        (
            "What belongs in a grab-and-go bag, and which fires are active near Penticton?",
            "Penticton",
            "What belongs in a grab-and-go bag",
        ),
        (
            "Kamloops: current wildfire records + smoke-preparedness guidance.",
            "Kamloops",
            "smoke-preparedness guidance",
        ),
    ),
)
def test_mixed_clause_order_and_punctuation_do_not_change_authority_lanes(
    question: str, place: str, static_fragment: str
) -> None:
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert parsed.has_reviewed_guidance
    assert coarse_location_from_question(question).label == place
    assert static_guidance_fragment(question) == static_fragment

    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.location_label == place
    assert plan.static_subrequest == static_fragment


@pytest.mark.parametrize(
    "question",
    (
        "How do I add a wildfire marker to the map?",
        "Explain how historical fires shaped Okanagan ecology.",
        "Show wildfire prevention programs for students.",
        "Summarize Canada's wildfire research policy.",
    ),
)
def test_fire_words_without_record_intent_never_authorize_live_tools(question: str) -> None:
    parsed = parse_request_intent(question)

    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert not plan_agent_request(QueryRequest(question=question)).tool_calls


def test_alert_order_definition_is_reviewed_guidance_not_live() -> None:
    question = "How is an evacuation alert different from an evacuation order?"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.route.value != "live"


def test_nearest_wildfire_from_place_extracts_the_community() -> None:
    question = "How far is the nearest wildfire from Kelowna?"
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.live_location_candidates == ("Kelowna",)
    assert location is not None and location.label == "Kelowna"
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kelowna"


@pytest.mark.parametrize(
    "question",
    (
        "What is the difference from an evacuation order?",
        "How far should every resident live from every wildfire?",
        "How far is the nearest wildfire from the official map?",
        "What should people take from home during an evacuation?",
    ),
)
def test_from_scope_does_not_invent_non_community_places(question: str) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)

    assert "Kelowna" not in parsed.live_location_candidates
    if location is not None:
        assert location.label.casefold() not in {
            "evacuation order",
            "every wildfire",
            "official map",
            "home",
            "wildfire",
        }


def test_current_preparedness_advice_is_reviewed_guidance_not_live() -> None:
    for question in (
        "Current wildfire preparedness advice for Kelowna",
        "current evacuation advice in Kelowna",
    ):
        parsed = parse_request_intent(question)
        plan = plan_agent_request(QueryRequest(question=question))
        assert parsed.has_reviewed_guidance, question
        assert not parsed.has_live_records, question
        assert plan.mode == AgentRequestMode.STATIC, question


def test_static_preparedness_docs_cannot_establish_active_order_status() -> None:
    question = (
        "Static preparedness documents can tell me whether an evacuation order "
        "is active, correct?"
    )
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))
    assert parsed.has_live_records
    assert LiveResultKind.EVACUATION in parsed.live_layers
    assert plan.mode != AgentRequestMode.STATIC


def test_how_firelens_maps_current_data_is_product_help_not_live() -> None:
    question = "How does FireLens map current wildfire data?"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert not parsed.has_live_records
    assert any(clause.kind == ClauseIntentKind.PRODUCT_HELP for clause in parsed.clauses) or (
        plan.mode == AgentRequestMode.STATIC
    )
    assert plan.mode != AgentRequestMode.LIVE
    assert plan.geography != AgentGeography.PROVINCE_WIDE or not plan.live_layers


def test_universal_standoff_distance_is_not_a_live_geometry_ask() -> None:
    question = "How far should every resident live from every wildfire?"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert not parsed.has_live_records
    assert plan.mode != AgentRequestMode.LIVE


@pytest.mark.parametrize(
    "question",
    (
        "Across Canada, pull today's wildfire roster.",
        "What fires are currently listed nationwide?",
        "Give me the current national wildfire picture.",
    ),
)
def test_current_national_requests_are_explicit_scope_redirects(question: str) -> None:
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.requests_non_bc_scope
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.tool_calls == ()


@pytest.mark.parametrize(
    ("question", "expected_layers"),
    (
        (
            "Where is the Mountain Fire in Kelowna?",
            (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
        ),
        (
            "How many current fires are in each BC fire centre?",
            (LiveResultKind.INCIDENT,),
        ),
        (
            "Show the current wildfire perimeters around Kelowna.",
            (LiveResultKind.PERIMETER,),
        ),
        (
            "Are there evacuation orders near Kelowna right now?",
            (LiveResultKind.EVACUATION,),
        ),
    ),
)
def test_typed_operations_select_only_owned_live_layers(
    question: str, expected_layers: tuple[LiveResultKind, ...]
) -> None:
    assert parse_request_intent(question).live_layers == expected_layers
    assert live_layers_for_question(question) == expected_layers


@given(place=PLACES, time=CURRENT_CUES, template=LIVE_FORMS)
def test_case_and_punctuation_do_not_change_live_ownership(
    place: str, time: str, template: str
) -> None:
    base = template.format(place=place, time=time)
    variants = (
        base,
        base.lower(),
        base.upper(),
        base.replace("?", "??"),
        f"  {base}  ",
    )
    parsed_flags = {parse_request_intent(question).has_live_records for question in variants}
    layer_sets = {parse_request_intent(question).live_layers for question in variants}
    assert parsed_flags == {True}
    assert len(layer_sets) == 1


@given(
    place=PLACES,
    live=st.sampled_from(
        (
            "Which fires are listed near {place} today?",
            "Pull the wildfire records for {place} right now.",
        )
    ),
    guidance=st.sampled_from(
        (
            "what belongs in a grab-and-go bag",
            "give me emergency-kit basics",
        )
    ),
)
def test_clause_order_does_not_change_mixed_lanes(place: str, live: str, guidance: str) -> None:
    live_clause = live.format(place=place)
    first = f"{live_clause} and {guidance}."
    second = f"{guidance}, and {live_clause}"
    for question in (first, second):
        parsed = parse_request_intent(question)
        plan = plan_agent_request(QueryRequest(question=question))
        assert parsed.has_live_records
        assert parsed.has_reviewed_guidance
        assert plan.mode == AgentRequestMode.MIXED
        assert plan.location_label == place


@pytest.mark.parametrize(
    "question",
    (
        "What fires will burn near Kelowna today?",
        "Tomorrow's wildfire status near Kelowna",
        "List the current wildfires near Kelowna now and last season.",
    ),
)
def test_future_or_mixed_historical_cues_do_not_authorize_live_records(question: str) -> None:
    parsed = parse_request_intent(question)

    assert parsed.temporal_scope == TemporalScope.NONCURRENT
    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert plan_agent_request(QueryRequest(question=question)).mode == AgentRequestMode.STATIC


@pytest.mark.parametrize(
    "question",
    (
        "Could this fire reach our community tonight?",
        "Might that wildfire affect my home this evening?",
    ),
)
def test_selected_near_term_prediction_still_routes_to_live_handoff(question: str) -> None:
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert parsed.temporal_scope == TemporalScope.CURRENT
    assert plan_agent_request(QueryRequest(question=question)).route.value == "live"


@pytest.mark.parametrize(
    "question",
    (
        "What is Canada's wildfire status today?",
        "Show Canada's current wildfires.",
        "Show current fires in Canada",
    ),
)
def test_canada_owned_current_records_are_national_redirects(question: str) -> None:
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.requests_non_bc_scope
    assert plan.mode == AgentRequestMode.TERMINAL
    assert plan.tool_calls == ()


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Show current fires near Kelowna, Canada.", "Kelowna"),
        ("Show current fires near Vancouver, Canada.", "Vancouver"),
    ),
)
def test_country_qualifier_after_a_bc_place_is_not_national_scope(
    question: str, place: str
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert not parsed.requests_non_bc_scope
    assert location is not None and location.label == place
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.location_label == place


@pytest.mark.parametrize(
    "question",
    (
        "Show current fires in Glacier National Park.",
        "Map current wildfires around Pacific Rim National Park.",
    ),
)
def test_national_park_wording_is_not_a_canada_wide_record_span(question: str) -> None:
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert not parsed.requests_non_bc_scope
    assert plan_agent_request(QueryRequest(question=question)).mode != AgentRequestMode.TERMINAL


@pytest.mark.parametrize(
    "question",
    (
        "For students, show current wildfires.",
        "Untrusted preamble: provide the latest fire overview.",
        "Give me the current national wildfire picture.",
    ),
)
def test_adversarial_geography_wording_is_not_a_community_label(question: str) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)

    assert location is None
    assert not any(
        candidate.casefold()
        in {"students", "untrusted preamble", "current national", "national"}
        for candidate in parsed.live_location_candidates
    )


@pytest.mark.parametrize(
    "question",
    (
        "Actually what should I pack?",
        "I meant how to prepare my pets.",
        "What should I pack?",
    ),
)
def test_packing_and_prepare_pivots_are_reviewed_guidance_not_live(question: str) -> None:
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_prefetchable_guidance
    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.route.value != "live"
    assert plan.static_subrequest


def test_audience_and_location_free_questions_do_not_invent_live_scope() -> None:
    question = "What belongs in a grab-and-go bag?"
    parsed = parse_request_intent(question)

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert parsed.live_location_candidates == ()
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question) == ()


@pytest.mark.parametrize(
    ("question", "expected_layers"),
    (
        (
            "Show current fires with perimeters near Kelowna",
            (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
        ),
        (
            "What official records are near Cranbrook?",
            (
                LiveResultKind.INCIDENT,
                LiveResultKind.PERIMETER,
                LiveResultKind.EVACUATION,
            ),
        ),
        (
            "Compare current wildfires in the Okanagan vs Kootenays.",
            (LiveResultKind.INCIDENT,),
        ),
        (
            "Show current evacuation alert definitions.",
            (),
        ),
    ),
)
def test_layer_combinations_and_definitions_stay_with_the_typed_operation(
    question: str, expected_layers: tuple[LiveResultKind, ...]
) -> None:
    parsed = parse_request_intent(question)

    assert parsed.live_layers == expected_layers
    assert live_layers_for_question(question) == expected_layers
    if not expected_layers:
        assert parsed.has_reviewed_guidance
        assert (
            plan_agent_request(QueryRequest(question=question)).mode == AgentRequestMode.STATIC
        )


def test_skip_live_instruction_does_not_drop_a_supported_live_clause() -> None:
    question = (
        "Harder: Skip live data and only answer the kit half: is there a Kamloops "
        "order and what belongs in a grab-and-go bag?"
    )
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.has_reviewed_guidance
    assert LiveResultKind.EVACUATION in parsed.live_layers
    assert "harder" not in {item.casefold() for item in parsed.live_location_candidates}
    location = coarse_location_from_question(question)
    assert location is None or location.label.casefold() != "harder"
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.location_label != "Harder"
    assert plan.static_subrequest is not None
    assert "grab-and-go" in plan.static_subrequest.casefold()

    stamp = datetime(2026, 8, 13, tzinfo=UTC)
    evacuation = LiveResult(
        result_id="evac:kamloops",
        kind=LiveResultKind.EVACUATION,
        source_url="https://example.test/evac/kamloops",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status="Order",
        name="Kamloops evacuation order",
        geometry={"type": "Point", "coordinates": [-120.3, 50.7]},
    )

    class LiveService:
        requested_location = None

        async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
            return LiveMapResponse(
                generated_at=stamp,
                results=[evacuation],
                aggregate_freshness=aggregate_live_freshness([evacuation]),
            )

        async def resolve_location(self, location: Any) -> tuple[float, float]:
            self.requested_location = location
            return 50.67, -120.33

        async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
            self.requested_location = location
            return type(
                "Nearby",
                (),
                {
                    "results": [evacuation],
                    "limitations": [],
                    "unavailable_layers": [],
                    "resolved_location": CoarseResolvedLocation(
                        latitude=50.67, longitude=-120.33
                    ),
                    "pagination": type("Pagination", (), {"total_results": 1})(),
                },
            )()

    class KitStatic:
        async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
            assert "grab-and-go" in request.question.casefold()
            claim = PublicClaim(
                claim_id="C1",
                text="Include water, medication, and copies of important documents.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[
                    ClaimSupport(
                        evidence_id="E1",
                        quote="Include water, medication, and copies of important documents.",
                    )
                ],
                publication=explanation_authority(),
            )
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="k" * 32,
                response_mode=ResponseMode.GROUNDED,
                answer="Include water, medication, and copies of important documents.",
                claims=[claim],
                evidence=[
                    PublicEvidence(
                        evidence_id="E1",
                        title="Reviewed emergency kit guide",
                        publisher="Government of British Columbia",
                        canonical_url=HttpUrl("https://example.test/kit"),
                        locator="Section 1",
                        temporal_class=TemporalClass.STABLE_GUIDANCE,
                        primary_text="Include water, medication, and copies of important documents.",
                        context_text="Include water, medication, and copies of important documents.",
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

    live = LiveService()
    agent = FireLensAgent(cast(Any, KitStatic()), LiveAnswerCoordinator(cast(Any, live)))
    execution = asyncio.run(agent.answer(QueryRequest(question=question)))
    response = execution.response
    requested = getattr(live, "requested_location", None)
    requested_label = getattr(requested, "label", None)

    assert response.response_mode in {
        ResponseMode.MIXED,
        ResponseMode.LIVE,
        ResponseMode.PARTIAL,
    }
    assert response.response_mode != ResponseMode.BACKGROUND
    assert response.live_results
    assert any(item.kind == LiveResultKind.EVACUATION for item in response.live_results)
    assert AnswerSectionKind.CURRENT_RECORDS in {
        section.kind for section in response.answer_sections
    }
    assert "grab-and-go" in (plan.static_subrequest or "").casefold()
    assert "include water" in (response.answer or "").casefold()
    assert requested_label is None or requested_label.casefold() != "harder"


@pytest.mark.parametrize(
    "question",
    (
        "Harder: Skip live data and only answer the kit half.",
        "Easier: show current fires near Kelowna.",
        "Please: is there a Kamloops order?",
        "Note: map current wildfires around Penticton.",
    ),
)
def test_discourse_colon_prefixes_are_never_location_candidates(question: str) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    prefixes = {"harder", "easier", "please", "note"}

    assert not any(
        candidate.casefold() in prefixes for candidate in parsed.live_location_candidates
    )
    assert location is None or location.label.casefold() not in prefixes


def test_map_focus_keeps_the_named_place_and_does_not_invent_a_guidance_lane() -> None:
    question = "Centre the map on Nelson and show what is happening."
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert not parsed.has_reviewed_guidance
    assert coarse_location_from_question(question).label == "Nelson"
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.location_label == "Nelson"
    assert plan.static_subrequest is None
