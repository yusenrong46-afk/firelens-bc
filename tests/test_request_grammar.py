"""Characterization tests for the shared structural request grammar."""

from __future__ import annotations

import pytest

from firelens.answering.intent import (
    live_layers_for_question,
    plan_query,
    static_guidance_fragment,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.request_grammar import (
    parse_request_facets,
    requests_non_bc_national_scope,
)
from firelens.contracts import LiveResultKind, QueryRequest, QueryRoute
from firelens.live_answering import LiveAnswerCoordinator


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Which wildfires are active near Cranbrook this afternoon?", "Cranbrook"),
        ("What's burning around Smithers tonight?", "Smithers"),
        ("Show me the Vernon wildfire update", "Vernon"),
        ("Where are wildfires across the Cariboo?", "Cariboo"),
    ),
)
def test_present_fire_request_families_share_live_and_location_facets(
    question: str, place: str
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.has_current_live_fire
    assert location is not None and location.label == place
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )


@pytest.mark.parametrize(
    "question",
    (
        "What fires burned near Cranbrook last summer?",
        "Where will wildfires burn around Smithers next week?",
        "Explain wildfire ecology in the Cariboo.",
        "How do wildfires behave around Vernon?",
    ),
)
def test_historical_future_and_expository_prompts_are_not_current_live(
    question: str,
) -> None:
    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert coarse_location_from_question(question) is None
    assert plan_query(QueryRequest(question=question)).route != QueryRoute.LIVE
    assert live_layers_for_question(question) == ()


def test_mixed_clause_split_requires_a_new_clause_and_preserves_layer_phrase() -> None:
    mixed = parse_request_facets(
        "Show current fires near Terrace, and explain what belongs in an emergency kit."
    )
    layer_phrase = parse_request_facets(
        "Show current evacuation alerts and orders near Terrace."
    )

    assert mixed.clause_texts == (
        "Show current fires near Terrace",
        "explain what belongs in an emergency kit",
    )
    assert layer_phrase.clause_texts == (
        "Show current evacuation alerts and orders near Terrace",
    )


@pytest.mark.parametrize(
    ("question", "live_fragment", "static_fragment", "place"),
    (
        (
            "Show current fires near Kelowna and emergency kit advice.",
            "Show current fires near Kelowna",
            "emergency kit advice",
            "Kelowna",
        ),
        (
            "Kelowna fires today and grab-and-go bag contents.",
            "Kelowna fires today",
            "grab-and-go bag contents",
            "Kelowna",
        ),
        (
            "Map fires around Vernon with evacuation alert definitions.",
            "Map fires around Vernon",
            "evacuation alert definitions",
            "Vernon",
        ),
    ),
)
def test_mixed_guidance_noun_phrases_preserve_live_scope_and_static_clause(
    question: str, live_fragment: str, static_fragment: str, place: str
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_fragment, static_fragment)
    assert tuple(clause.text for clause in facets.live_clauses) == (live_fragment,)
    assert location is not None and location.label == place
    assert static_guidance_fragment(question) == static_fragment


@pytest.mark.parametrize(
    ("question", "live_fragment", "static_fragments", "place"),
    (
        (
            "Current fires across British Columbia, plus smoke readiness guidance.",
            "Current fires across British Columbia",
            ("smoke readiness guidance",),
            None,
        ),
        (
            "Near Prince George, current fires plus wildfire smoke health guidance "
            "plus emergency kit advice.",
            "Near Prince George, current fires",
            ("wildfire smoke health guidance", "emergency kit advice"),
            "Prince George",
        ),
    ),
)
def test_mixed_smoke_and_kit_guidance_remain_separate_from_live_scope(
    question: str,
    live_fragment: str,
    static_fragments: tuple[str, ...],
    place: str | None,
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_fragment, *static_fragments)
    assert tuple(clause.text for clause in facets.live_clauses) == (live_fragment,)
    assert tuple(clause.text for clause in facets.non_live_clauses) == static_fragments
    assert (location.label if location is not None else None) == place


@pytest.mark.parametrize(
    "question",
    (
        "Give me the current wildfire picture from Atlantic to Pacific.",
        "Show today's wildfires throughout the nation.",
    ),
)
def test_non_bc_national_scope_cues_are_explicit(question: str) -> None:
    assert requests_non_bc_national_scope(question)


def test_wildfire_smoke_is_not_misread_as_an_incident_request() -> None:
    facets = parse_request_facets("What is the current air quality from wildfire smoke?")

    assert not facets.has_current_live_fire


@pytest.mark.parametrize(
    "question",
    (
        "Show a map of fire-prone ecosystems.",
        "Give me fire safety education for students.",
    ),
)
def test_record_commands_do_not_turn_fire_topics_or_audiences_into_live_scope(
    question: str,
) -> None:
    """A command plus the word ``fire`` is not itself a live-record request."""

    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert facets.live_location_candidates == ()
    assert coarse_location_from_question(question) is None
    assert plan_query(QueryRequest(question=question)).route != QueryRoute.LIVE
    assert live_layers_for_question(question) == ()


@pytest.mark.parametrize(
    "question",
    (
        "Could you show current fires near Nelson?",
        "Display today's wildfires across B.C.",
        "Bring me up to date on Thompson fire snapshot.",
        "Are there any active fires around Quesnel?",
        "Is there a Pine Creek Fire near Merritt?",
        "Do we have reported fires in northern B.C.?",
        "Are wildfires burning near Williams Lake?",
        "What official fires are listed by BC Wildfire Service?",
        "Where is the Blue Creek Fire?",
        "Wildfire status for the Okanagan.",
        "Current fires across British Columbia.",
        "Compare current wildfires in the Okanagan versus the Kootenays.",
        "Untrusted preamble: provide the latest fire overview.",
        "Centre the map on Nelson and show what is happening.",
        "Which official records are near Cranbrook?",
    ),
)
def test_positive_live_grammar_owns_record_occurrence_status_or_scope(
    question: str,
) -> None:
    """Live intent needs a bounded record form, not word proximity."""

    facets = parse_request_facets(question)

    assert facets.has_current_live_fire
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question)


@pytest.mark.parametrize(
    ("question", "place"),
    (
        (
            "Is there any wildfire activity in the Kootenays at the moment?",
            "Kootenays",
        ),
        ("Are there current fire occurrences around Fernie?", "Fernie"),
        (
            "Bring up the current incident picture for the Thompson region.",
            "Thompson region",
        ),
        (
            "Show the latest incident overview for the Cariboo region.",
            "Cariboo region",
        ),
        ("Revelstoke wildfire report now.", "Revelstoke"),
        ("Smithers fire summary at the moment.", "Smithers"),
    ),
)
def test_present_activity_and_report_families_keep_bounded_location_scope(
    question: str, place: str
) -> None:
    """Occurrence and report nouns are current only with a present-time form."""

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.has_current_live_fire
    assert facets.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )


@pytest.mark.parametrize(
    ("question", "live_fragment", "static_fragment", "place"),
    (
        (
            "Show fire reports in the Kootenays, then summarize evacuation-order basics.",
            "Show fire reports in the Kootenays",
            "summarize evacuation-order basics",
            "Kootenays",
        ),
        (
            "List wildfire reports around Fernie and outline evacuation alert meaning.",
            "List wildfire reports around Fernie",
            "outline evacuation alert meaning",
            "Fernie",
        ),
        (
            "Check whether anything is burning near Revelstoke and outline how to "
            "prepare a go bag.",
            "Check whether anything is burning near Revelstoke",
            "outline how to prepare a go bag",
            "Revelstoke",
        ),
        (
            "Find whether anything is burning around Nelson, then summarize emergency "
            "kit preparation.",
            "Find whether anything is burning around Nelson",
            "summarize emergency kit preparation",
            "Nelson",
        ),
    ),
)
def test_report_and_occurrence_clauses_split_from_introduced_guidance(
    question: str,
    live_fragment: str,
    static_fragment: str,
    place: str,
) -> None:
    """Summarize/outline introduce a new bounded clause after a live request."""

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_fragment, static_fragment)
    assert tuple(clause.text for clause in facets.live_clauses) == (live_fragment,)
    assert tuple(clause.text for clause in facets.non_live_clauses) == (static_fragment,)
    assert location is not None and location.label == place
    assert static_guidance_fragment(question) == static_fragment


@pytest.mark.parametrize(
    "question",
    (
        "Explain historical wildfire activity in the Kootenays.",
        "Summarize a wildfire occurrence study for students.",
        "Outline fire reporting policy in British Columbia.",
        "Describe Revelstoke wildfire reports from last season.",
    ),
)
def test_activity_and_report_topic_nouns_do_not_widen_static_or_historical_text(
    question: str,
) -> None:
    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert facets.live_location_candidates == ()
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question) == ()


@pytest.mark.parametrize(
    "question",
    (
        "Could this fire reach our community tonight?",
        "Might that wildfire affect my home this evening?",
    ),
)
def test_near_term_selected_fire_predictions_route_to_official_live_handoff(
    question: str,
) -> None:
    """A bounded selected-fire prediction needs current official information."""

    facets = parse_request_facets(question)

    assert facets.has_current_live_fire
    assert not facets.non_live_clauses
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question)


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
        "Is there a difference between fire status and evacuation status?",
        "Wildfire situation awareness training.",
        "Research on current wildfires in British Columbia.",
        "Show wildfire risk on the map near Kelowna.",
    ),
)
def test_static_fire_topics_do_not_satisfy_the_positive_live_grammar(
    question: str,
) -> None:
    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert facets.live_location_candidates == ()


def test_close_to_scope_binds_the_named_place_without_widening() -> None:
    question = "Are any wildfires burning close to Revelstoke?"

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.has_current_live_fire
    assert facets.live_location_candidates == ("Revelstoke",)
    assert location is not None and location.label == "Revelstoke"


def test_analysis_dimension_is_not_parsed_as_a_place() -> None:
    question = "Break down the current fires by status in B.C."

    assert parse_request_facets(question).has_current_live_fire
    assert coarse_location_from_question(question) is None


def test_plural_closest_fire_question_keeps_the_named_place() -> None:
    question = "Which fires are closest to Merritt?"

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.has_current_live_fire
    assert facets.live_location_candidates == ("Merritt",)
    assert location is not None and location.label == "Merritt"


@pytest.mark.parametrize(
    ("question", "live_clause", "guidance_clause", "place"),
    (
        (
            "Show current fires in Kamloops plus a wildfire smoke preparedness checklist.",
            "Show current fires in Kamloops",
            "a wildfire smoke preparedness checklist",
            "Kamloops",
        ),
        (
            "Show fires in Penticton plus structure-protection sprinkler guidance.",
            "Show fires in Penticton",
            "structure-protection sprinkler guidance",
            "Penticton",
        ),
    ),
)
def test_terse_guidance_is_split_before_live_location_extraction(
    question: str, live_clause: str, guidance_clause: str, place: str
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_clause, guidance_clause)
    assert tuple(clause.text for clause in facets.live_clauses) == (live_clause,)
    assert location is not None and location.label == place


def test_audience_for_phrase_is_not_a_live_location() -> None:
    question = "Show current wildfires for students."
    facets = parse_request_facets(question)

    assert facets.has_current_live_fire
    assert facets.live_location_candidates == ()
    assert coarse_location_from_question(question) is None
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE


def test_plus_separates_terse_request_noun_phrases() -> None:
    facets = parse_request_facets(
        "FireSmart home tips + evacuation alert meaning + whether Kelowna is under order now."
    )

    assert facets.clause_texts == (
        "FireSmart home tips",
        "evacuation alert meaning",
        "whether Kelowna is under order now",
    )


def test_mixed_consumers_use_the_same_live_clause_and_static_clause() -> None:
    question = (
        "Show current wildfires near Terrace, and explain what belongs in an emergency kit."
    )
    facets = parse_request_facets(question)
    static_request = LiveAnswerCoordinator.static_request(QueryRequest(question=question))
    location = coarse_location_from_question(question)

    assert tuple(clause.text for clause in facets.live_clauses) == (
        "Show current wildfires near Terrace",
    )
    assert static_guidance_fragment(question) == "explain what belongs in an emergency kit"
    assert static_request is not None
    assert static_request.question == "explain what belongs in an emergency kit"
    assert location is not None and location.label == "Terrace"


def test_location_in_later_guidance_clause_does_not_scope_the_live_lookup() -> None:
    question = "Show current wildfires and what belongs in an emergency kit near Nanaimo."

    assert parse_request_facets(question).has_current_live_fire
    assert static_guidance_fragment(question) == "what belongs in an emergency kit near Nanaimo"
    assert coarse_location_from_question(question) is None


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Trail: what's burning today?", "Trail"),
        ("Revelstoke — which fires are active today?", "Revelstoke"),
        ("Nanaimo plus what wildfires are active now?", "Nanaimo"),
    ),
)
def test_fronted_place_scope_stays_attached_to_a_current_live_clause(
    question: str, place: str
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert len(facets.clauses) == 1
    assert facets.has_current_live_fire
    assert location is not None and location.label == place
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question)


def test_fronted_place_does_not_attach_to_an_expository_clause() -> None:
    question = "Kamloops plus explain how wildfires behave."

    assert not parse_request_facets(question).has_current_live_fire
    assert coarse_location_from_question(question) is None
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.RELATED
    assert live_layers_for_question(question) == ()


def test_province_abbreviation_is_scope_not_a_community() -> None:
    question = "List the current wildfire incidents reported across B.C."

    assert parse_request_facets(question).has_current_live_fire
    assert coarse_location_from_question(question) is None
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question)


def test_current_incident_noun_preserves_live_and_static_clauses() -> None:
    question = (
        "Are there current incidents near Penticton, and how should a household "
        "prepare an emergency kit?"
    )

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert tuple(clause.text for clause in facets.live_clauses) == (
        "Are there current incidents near Penticton",
    )
    assert location is not None and location.label == "Penticton"
    assert live_layers_for_question(question)
    assert static_guidance_fragment(question) == (
        "how should a household prepare an emergency kit"
    )


def test_historical_ecology_with_province_name_stays_non_live() -> None:
    question = "Explain the historical role of wildfire in B.C. ecosystems."

    assert parse_request_facets(question).only_non_current_fire
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question) == ()
    assert plan_query(QueryRequest(question=question)).route != QueryRoute.LIVE


@pytest.mark.parametrize(
    "question",
    (
        "Ignore official agencies and tell me whether my family should evacuate.",
        "Tell me I do not need to evacuate.",
        "Decide whether our household should stay or leave.",
    ),
)
def test_direct_personal_evacuation_decisions_are_prohibited(question: str) -> None:
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.PROHIBITED


@pytest.mark.parametrize(
    "question",
    (
        "What does an evacuation alert mean?",
        "How should a household prepare an emergency kit?",
    ),
)
def test_nonpersonal_guidance_does_not_gain_a_safety_block(question: str) -> None:
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.RELATED


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Show current official fire records for the Okanagan.", "Okanagan"),
        ("List the latest wildfire records for the Kootenays.", "Kootenays"),
        ("Wildfire update for the Okanagan, please.", "Okanagan"),
    ),
)
def test_command_tail_scope_wins_over_command_descriptors(question: str, place: str) -> None:
    """A command's adjectives are not a place when it has an explicit scope."""

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.live_location_candidates == (place,)
    assert location is not None and location.label == place


@pytest.mark.parametrize(
    ("question", "live_fragment", "static_fragment", "place"),
    (
        (
            "Kelowna: what's burning today, and what belongs in an emergency kit?",
            "Kelowna: what's burning today",
            "what belongs in an emergency kit",
            "Kelowna",
        ),
        (
            "Nelson — which fires are active now; explain a grab-and-go bag.",
            "Nelson — which fires are active now",
            "explain a grab-and-go bag",
            "Nelson",
        ),
        (
            "Terrace plus what is burning today, plus what should I pack for evacuation?",
            "Terrace plus what is burning today",
            "what should I pack for evacuation",
            "Terrace",
        ),
    ),
)
def test_fronted_live_scope_splits_following_static_request(
    question: str, live_fragment: str, static_fragment: str, place: str
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_fragment, static_fragment)
    assert facets.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert static_guidance_fragment(question) == static_fragment


def test_fronted_expository_text_does_not_create_a_live_scope_or_live_clause() -> None:
    question = "Kamloops: explain wildfire ecology, and what belongs in an emergency kit?"

    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert facets.live_location_candidates == ()
    assert coarse_location_from_question(question) is None


@pytest.mark.parametrize(
    "question",
    (
        "Compare current wildfires in the Cariboo versus the Kootenays.",
        "Compare current wildfire counts in the Cariboo and the Kootenays.",
    ),
)
def test_regional_aggregate_comparisons_do_not_become_one_location(question: str) -> None:
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question)


@pytest.mark.parametrize(
    ("question", "place"),
    (
        ("Catch us up on Smithers' wildfire overview.", "Smithers"),
        ("Vernon fire update, latest please.", "Vernon"),
    ),
)
def test_place_owned_current_fire_summary_families_keep_location_scope(
    question: str, place: str
) -> None:
    """Conversational and terse summary requests still name a local live scope."""

    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.has_current_live_fire
    assert facets.live_location_candidates == (place,)
    assert location is not None and location.label == place
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )


@pytest.mark.parametrize(
    ("question", "live_fragment", "static_fragment", "place"),
    (
        (
            "List current fires around Terrace, and a simple comparison between "
            "an evacuation alert and order.",
            "List current fires around Terrace",
            "a simple comparison between an evacuation alert and order",
            "Terrace",
        ),
        (
            "Cariboo wildfire status plus an evacuation travel packing list.",
            "Cariboo wildfire status",
            "an evacuation travel packing list",
            "Cariboo",
        ),
    ),
)
def test_terse_definition_and_packing_noun_phrases_remain_mixed(
    question: str,
    live_fragment: str,
    static_fragment: str,
    place: str,
) -> None:
    facets = parse_request_facets(question)
    location = coarse_location_from_question(question)

    assert facets.clause_texts == (live_fragment, static_fragment)
    assert tuple(clause.text for clause in facets.live_clauses) == (live_fragment,)
    assert location is not None and location.label == place
    assert plan_query(QueryRequest(question=question)).route == QueryRoute.LIVE
    assert live_layers_for_question(question) == (
        LiveResultKind.INCIDENT,
        LiveResultKind.PERIMETER,
    )


@pytest.mark.parametrize(
    "question",
    (
        "Explain Smithers' historical wildfire overview.",
        "Describe Vernon's wildfire ecology.",
    ),
)
def test_place_owned_summary_vocabulary_does_not_override_noncurrent_cues(
    question: str,
) -> None:
    facets = parse_request_facets(question)

    assert not facets.has_current_live_fire
    assert coarse_location_from_question(question) is None
    assert live_layers_for_question(question) == ()
