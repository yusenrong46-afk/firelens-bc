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
from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    prefers_general_background,
    static_guidance_fragment,
)
from firelens.answering.intent_automaton import (
    ClauseIntentKind,
    RecordOperation,
    TemporalScope,
    parse_request_intent,
)
from firelens.answering.intent_refresh import is_live_refresh_request
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.static_guidance_subject import (
    StaticGuidanceSubject,
    static_guidance_retrieval_query,
    static_guidance_subject,
)
from firelens.contracts import (
    AnswerSectionKind,
    AskResponse,
    ClaimSupport,
    CoarseResolvedLocation,
    ConversationTurn,
    EvidenceStatus,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
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
from firelens.publication.fallback import explanation_authority

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


@pytest.mark.parametrize(
    ("question", "expected_subject", "expected_query"),
    (
        (
            "Give general kit guidance.",
            StaticGuidanceSubject.EMERGENCY_KIT,
            "emergency kit contents checklist",
        ),
        (
            "Regarding an emergency kit, what about pets?",
            StaticGuidanceSubject.PET_GRAB_AND_GO,
            "pets emergency kit grab-and-go bag food water leashes carriers",
        ),
        ("Put a bag in the trunk before work.", None, None),
        ("How should I pack a backpack for travel?", None, None),
        ("What about pets during the wildfire season?", None, None),
    ),
)
def test_static_guidance_subject_is_bounded_to_kit_context(
    question: str,
    expected_subject: StaticGuidanceSubject | None,
    expected_query: str | None,
) -> None:
    assert static_guidance_subject(question) == expected_subject
    assert static_guidance_retrieval_query(question) == expected_query


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
    "question",
    (
        "What is the most common mistake to make when wildfire is coming?",
        "What are the most common mistakes people make before a wildfire?",
    ),
)
def test_general_wildfire_discussion_does_not_become_a_live_record_lookup(
    question: str,
) -> None:
    parsed = parse_request_intent(question)

    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert all(clause.kind != ClauseIntentKind.LIVE_RECORDS for clause in parsed.clauses)
    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.geography == AgentGeography.NONE
    assert plan.tool_calls == ()


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


def test_refresh_wildfire_data_is_a_current_snapshot_not_a_historical_claim() -> None:
    question = "Refresh the wildfire data and tell me whether anything changed."
    parsed = parse_request_intent(question)

    assert parsed.has_live_records
    assert parsed.clauses[0].operation == RecordOperation.LIST
    assert is_live_refresh_request(question)
    plan = plan_agent_request(QueryRequest(question=question))
    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.PROVINCE_WIDE


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


def test_province_active_roster_avoids_unrequested_perimeter_geometry() -> None:
    question = "Are there active wildfires in BC currently?"

    assert parse_request_intent(question).live_layers == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )
    assert live_layers_for_question(question) == (LiveResultKind.INCIDENT,)


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


def test_what_is_an_evacuation_alert_is_reviewed_guidance_not_live_alerts() -> None:
    question = "What's an evacuation alert?"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert live_layers_for_question(question) == ()
    assert plan.mode == AgentRequestMode.STATIC


def test_tell_me_about_an_explicit_named_fire_is_a_live_incident_lookup() -> None:
    question = "Tell me about Bald Range Fire"
    parsed = parse_request_intent(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert live_layers_for_question(question) == (LiveResultKind.INCIDENT,)
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.route == QueryRoute.LIVE
    assert parsed.has_live_records or live_layers_for_question(question)


def test_explicit_live_record_ranking_binds_the_stated_community() -> None:
    question = "Can you list the 3 live records closest to Kelowna?"
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.clauses[0].operation == RecordOperation.LOCATE
    assert parsed.live_location_candidates == ("Kelowna",)
    assert location is not None and location.label == "Kelowna"
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label == "Kelowna"
    assert plan.tool_calls[0].as_arguments() == {"place_label": "Kelowna"}


def test_current_status_of_an_explicit_named_fire_filters_the_live_roster() -> None:
    question = "What is the current status of the Bald Range Fire?"

    assert extracted_located_fire_name(question) == "Bald Range"
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )
    assert extracted_located_fire_name("What is the status of this fire?") is None


def test_explicit_status_fire_typo_remains_a_narrow_named_incident_lookup() -> None:
    assert extracted_located_fire_name("whts status bald range fire") == "bald range"
    assert extracted_located_fire_name("whts status wildfire smoke") is None


def test_closest_fire_size_shorthand_binds_its_stated_place() -> None:
    location = coarse_location_from_question("how big closest fire kamloops")

    assert location is not None
    assert location.label == "kamloops"
    assert location.radius_km == 50


def test_guidance_where_questions_are_not_named_fire_lookups() -> None:
    assert extracted_located_fire_name("Where is wildfire prevention taught in B.C.?") is None
    assert extracted_located_fire_name("Tell me about wildfire smoke in plain English") is None
    assert extracted_located_fire_name("Tell me about Northern B.C. wildfire history.") is None
    assert extracted_located_fire_name("Tell me about Bald Range") is None
    assert extracted_located_fire_name("Tell me about Bald Range Fire") == "Bald Range"
    assert extracted_located_fire_name("Tell me about K12345") == "K12345"


def test_bare_tell_me_about_subject_never_authorizes_live_incident_lookup() -> None:
    plan = plan_agent_request(QueryRequest(question="Tell me about Bald Range"))

    assert live_layers_for_question("Tell me about Bald Range") == ()
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.route != QueryRoute.LIVE


def test_audience_and_location_free_questions_do_not_invent_live_scope() -> None:
    question = "What belongs in a grab-and-go bag?"
    parsed = parse_request_intent(question)

    assert parsed.has_reviewed_guidance
    assert not parsed.has_live_records
    assert parsed.live_location_candidates == ()
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question) == ()


def test_exclusionary_bag_followup_stays_general_without_inheriting_review_authority() -> None:
    request = QueryRequest(
        question="what are something that's not needed for the bag",
        history=[
            ConversationTurn(role="user", content="What belongs in a grab-and-go bag?"),
            ConversationTurn(role="assistant", content="Pack water and food."),
        ],
    )

    public_plan = plan_query(request)
    agent_plan = plan_agent_request(request)

    assert public_plan.route == QueryRoute.TANGENT
    assert agent_plan.mode == AgentRequestMode.STATIC
    assert agent_plan.route == QueryRoute.TANGENT
    assert agent_plan.tool_calls == ()
    assert agent_plan.live_layers == ()
    assert agent_plan.location_label is None


def test_explicit_exclusionary_grab_and_go_question_stays_general_background() -> None:
    request = QueryRequest(
        question="what are some things that are not needed for a grab-and-go bag?"
    )

    public_plan = plan_query(request)
    agent_plan = plan_agent_request(request)

    assert prefers_general_background(request)
    assert public_plan.route == QueryRoute.TANGENT
    assert agent_plan.mode == AgentRequestMode.STATIC
    assert agent_plan.tool_calls == ()


@pytest.mark.parametrize(
    "question",
    (
        "What caused the 2023 BC wildfire season?",
        "Why was the 2023 wildfire season so severe?",
        "Tell me the history of wildfire in BC.",
    ),
)
def test_broad_noncurrent_wildfire_history_stays_general_background(question: str) -> None:
    request = QueryRequest(question=question)
    parsed = parse_request_intent(question)

    assert parsed.temporal_scope == TemporalScope.NONCURRENT
    assert prefers_general_background(request)
    assert plan_query(request).route == QueryRoute.TANGENT
    assert plan_agent_request(request).mode == AgentRequestMode.STATIC


@pytest.mark.parametrize(
    "query_request",
    (
        QueryRequest(
            question="According to the PreparedBC guide, what is not needed for a grab-and-go bag?"
        ),
        QueryRequest(question="What does SRC-01 say about wildfire history?"),
        QueryRequest(question="Tell me the history of Mountain Fire."),
        QueryRequest(question="What caused the current wildfire season?"),
        QueryRequest(
            question="How large is it?", context={"selected_live_result_id": "incident:1"}
        ),
    ),
)
def test_source_current_named_and_deictic_requests_do_not_use_general_background(
    query_request: QueryRequest,
) -> None:
    assert not prefers_general_background(query_request)


def test_named_individual_fire_question_uses_live_record_boundary() -> None:
    request = QueryRequest(question="What caused Mountain Fire?")

    assert not prefers_general_background(request)
    assert plan_query(request).route == QueryRoute.LIVE
    assert plan_agent_request(request).mode == AgentRequestMode.TERMINAL


def test_agency_name_is_not_misread_as_a_named_fire_record() -> None:
    request = QueryRequest(question="What does BC Wildfire Service do?")

    assert plan_query(request).route != QueryRoute.LIVE


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
