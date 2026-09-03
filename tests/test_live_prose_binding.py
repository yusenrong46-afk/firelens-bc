"""Live public answers must be bound to fetched typed records."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import HttpUrl, ValidationError

from firelens.agent import FireLensAgent
from firelens.agent.chat import ChatTurn
from firelens.agent.compose import _build_ask_response
from firelens.agent.packet import AgentPacket
from firelens.answering.live_analysis import (
    compose_official_answer,
)
from firelens.answering.live_analysis_distance import (
    closest_locatable_result,
    ranked_live_results_for_request,
)
from firelens.answering.plain_time import human_time
from firelens.contracts import (
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    ClaimSupport,
    ConversationTurn,
    EvidenceStatus,
    Freshness,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapContext,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
    bind_distance_derivation,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.fallback import explanation_authority
from firelens.publication_response_binding import live_answer_binding_error


def _timestamp() -> datetime:
    return datetime(2026, 8, 15, tzinfo=UTC)


def _mountain_held() -> LiveResult:
    stamp = _timestamp()
    return LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/live/incident:7",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name="Mountain Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


def _incident_perimeter_roster() -> list[LiveResult]:
    incidents = [
        _mountain_held().model_copy(
            update={"result_id": f"incident:{index}", "name": f"Fire {index}"}
        )
        for index in range(1, 4)
    ]
    perimeters = [
        incident.model_copy(
            update={
                "result_id": f"perimeter:{index}",
                "kind": LiveResultKind.PERIMETER,
                "name": f"Fire {index} perimeter",
                "status": "Mapped perimeter",
            }
        )
        for index, incident in enumerate(incidents, start=1)
    ]
    return [*incidents, *perimeters]


def test_ordinary_fire_roster_does_not_narrate_perimeters_as_extra_fires() -> None:
    answer = compose_official_answer(
        QueryRequest(question="List the current active fires across BC."),
        _incident_perimeter_roster(),
    )

    assert "lists 3 fires" in answer
    assert "Fire 1 is listed as Being Held" in answer
    assert "Fire 2 is listed as Being Held" in answer
    assert "Fire 3 is listed as Being Held" in answer
    assert "perimeter" not in answer.casefold()


def test_ordinary_fire_roster_keeps_requested_evacuation_record_while_omitting_perimeter() -> (
    None
):
    roster = _incident_perimeter_roster()
    evacuation = _mountain_held().model_copy(
        update={
            "result_id": "evacuation:1",
            "kind": LiveResultKind.EVACUATION,
            "name": "Fire 1 evacuation alert",
            "status": "Alert",
        }
    )

    answer = compose_official_answer(
        QueryRequest(question="List current fires with emergency notices across BC."),
        [*roster, evacuation],
    )

    assert "Fire 1 is listed as Being Held" in answer
    assert "1 evacuation record: Fire 1 evacuation alert (Alert)" in answer
    assert "perimeter" not in answer.casefold()


@pytest.mark.parametrize(
    "question",
    (
        "List the current official fire perimeter records across BC.",
        "Show all current official multi-layer fire records across BC.",
    ),
)
def test_explicit_perimeter_or_multilayer_roster_keeps_perimeter_records(question: str) -> None:
    answer = compose_official_answer(
        QueryRequest(question=question), _incident_perimeter_roster()
    )

    assert "lists 3 fires and 3 perimeters" in answer
    assert "Fire 1 is listed as Being Held" in answer


def test_mixed_fire_lookup_keeps_live_incidents_ahead_of_future_evacuation_guidance() -> None:
    answer = compose_official_answer(
        QueryRequest(
            question=(
                "Are there fires near Penticton, and what should I do if an "
                "evacuation order is issued later?"
            )
        ),
        [_mountain_held()],
        static_answer="An evacuation order means you must leave immediately.",
    )

    assert "Mountain Fire" in answer
    assert "No fetched official fire-related evacuation" not in answer


def _with_distance(result: LiveResult, distance_km: float) -> LiveResult:
    return result.model_copy(
        update={
            "distance_km": distance_km,
            "distance_basis": "incident_point",
            "distance_derivation": bind_distance_derivation(
                result_id=result.result_id,
                distance_km=distance_km,
                distance_basis="incident_point",
                calculated_at=result.retrieved_at,
                extra_input_ids=("place:49.90,-119.50",),
                input_freshness=result.freshness,
            ),
        }
    )


class _FixedLiveService:
    def __init__(self, results: list[LiveResult]) -> None:
        self.results = results
        self.map_calls = 0
        self.nearby_calls = 0

    async def map_results(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.map_calls += 1
        return type(
            "Map",
            (),
            {
                "generated_at": _timestamp(),
                "results": self.results,
                "aggregate_freshness": aggregate_live_freshness(self.results),
            },
        )()

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        return 49.88, -119.49

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        del location, args, kwargs
        self.nearby_calls += 1
        return type(
            "Nearby",
            (),
            {
                "results": self.results,
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": None,
                "pagination": type("Pagination", (), {"total_results": len(self.results)})(),
            },
        )()


class _SilentStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        raise AssertionError("live prose binding must not call static RAG")


class _RejectedStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="r" * 32,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer="The reviewed clause was not established.",
            limitations=["The reviewed clause was not established."],
            validation=ValidationReport(
                accepted=False,
                citation_ids_valid=True,
                quotes_exact=True,
                claim_support_valid=False,
                policy_valid=True,
            ),
        )


class _FixedProseProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(content=self.content)


UNBOUND_LIVE_PROSE = (
    "Mountain Fire is Out of Control.",
    "There are 999 active wildfires in British Columbia.",
    "Every resident should live outside a 10 kilometre radius from every wildfire.",
)


def _live_response(*, answer: str, result: LiveResult) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="live-prose-binding",
        response_mode=ResponseMode.LIVE,
        answer=answer,
        live_results=[result],
        aggregate_freshness=aggregate_live_freshness([result]),
        limitations=["This uses official records and is not a safety assessment."],
    )


@pytest.mark.parametrize("prose", UNBOUND_LIVE_PROSE)
def test_provider_live_prose_cannot_contradict_fetched_records(prose: str) -> None:
    record = _mountain_held()
    agent = FireLensAgent(
        cast(Any, _SilentStatic(_FixedProseProvider(prose))),
        LiveAnswerCoordinator(cast(Any, _FixedLiveService([record]))),
    )

    execution = asyncio.run(
        agent.answer(QueryRequest(question="What official fires are near Kelowna?"))
    )

    answer = execution.response.answer or ""
    assert execution.response.response_mode == ResponseMode.LIVE
    assert execution.response.live_results[0].name == "Mountain Fire"
    assert execution.response.live_results[0].status == "Being Held"
    assert execution.response.proof_cards
    assert execution.response.proof_cards[0].support_state == "live_record"
    assert prose not in answer
    assert "Out of Control" not in answer
    assert "999" not in answer
    assert "10 kilometre" not in answer.casefold() and "10 km" not in answer.casefold()
    assert "Mountain Fire" in answer
    assert "Being Held" in answer


def test_rejected_static_mixed_request_cannot_publish_provider_prose() -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat_turn(
            self,
            messages: list[dict[str, Any]],
            *,
            tools: list[dict[str, Any]] | None = None,
        ) -> ChatTurn:
            del messages, tools
            self.calls += 1
            return ChatTurn(content="Provider prose must not appear in this live answer.")

    provider = Provider()
    record = _mountain_held()
    agent = FireLensAgent(
        cast(Any, _RejectedStatic(provider)),
        LiveAnswerCoordinator(cast(Any, _FixedLiveService([record]))),
    )

    execution = asyncio.run(
        agent.answer(
            QueryRequest(
                question=(
                    "What official fires are near Kelowna, and what belongs in an emergency kit?"
                )
            )
        )
    )

    answer = execution.response.answer or ""
    assert provider.calls == 0
    assert execution.response.response_mode == ResponseMode.LIVE
    assert "Provider prose must not appear" not in answer
    assert "Mountain Fire" in answer
    assert any("non-live clause" in item for item in execution.response.limitations)


@pytest.mark.parametrize("prose", UNBOUND_LIVE_PROSE)
def test_live_contract_rejects_unbound_prose_over_typed_records(prose: str) -> None:
    with pytest.raises(ValidationError):
        _live_response(answer=prose, result=_mountain_held())


def test_bound_luna_prose_is_published_when_it_matches_fetched_records() -> None:
    record = _mountain_held()
    agent = FireLensAgent(
        cast(Any, _SilentStatic(_FixedProseProvider("Mountain Fire is Being Held."))),
        LiveAnswerCoordinator(cast(Any, _FixedLiveService([record]))),
    )

    execution = asyncio.run(
        agent.answer(QueryRequest(question="What official fires are near Kelowna?"))
    )

    answer = execution.response.answer or ""
    assert execution.response.response_mode == ResponseMode.LIVE
    assert "Mountain Fire" in answer
    assert "Being Held" in answer


def test_fire_of_note_distribution_is_not_misread_as_a_total_fire_count() -> None:
    records = [
        _mountain_held().model_copy(update={"status": "Fire of Note"}),
        _mountain_held().model_copy(
            update={"result_id": "incident:8", "name": "Ridge Fire", "status": "Fire of Note"}
        ),
        _mountain_held().model_copy(update={"result_id": "incident:9", "name": "Valley Fire"}),
    ]
    answer = compose_official_answer(
        QueryRequest(question="Give me a distribution of the current wildfire in BC"),
        records,
    )

    assert "2 Fire of Note" in answer
    assert live_answer_binding_error(answer, records) is None
    response = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="distribution-fire-of-note",
        response_mode=ResponseMode.LIVE,
        answer=answer,
        live_results=records,
        aggregate_freshness=aggregate_live_freshness(records),
    )
    assert response.answer == answer


def test_multi_record_freshness_keeps_source_and_retrieval_clocks_separate() -> None:
    first = _mountain_held()
    second = first.model_copy(
        update={
            "result_id": "incident:8",
            "name": "Ridge Fire",
            "source_updated_at": datetime(2026, 8, 15, 1, tzinfo=UTC),
            "retrieved_at": datetime(2026, 8, 15, 2, tzinfo=UTC),
        }
    )

    answer = compose_official_answer(
        QueryRequest(question="When was the wildfire information for Kelowna last updated?"),
        [first, second],
    )

    assert "last updated these records" in answer
    assert "FireLens fetched them" in answer
    assert "two different clocks" in answer
    assert human_time(first.source_updated_at) in answer
    assert human_time(second.retrieved_at) in answer


def test_ranked_closest_list_is_stable_and_does_not_select_only_one_record() -> None:
    first = _with_distance(_mountain_held(), 12.0)
    second = _with_distance(
        _mountain_held().model_copy(update={"result_id": "incident:8", "name": "Ridge Fire"}),
        4.0,
    )

    answer = compose_official_answer(
        QueryRequest(
            question="List the closest fires to Kelowna in order from nearest to farthest."
        ),
        [first, second],
    )

    assert answer.index("Ridge Fire") < answer.index("Mountain Fire")
    assert "4 km" in answer
    assert "12 km" in answer

    ranked = ranked_live_results_for_request(
        "Show me the two closest fires to Kelowna.",
        [first, second],
    )
    assert [item.result_id for item in ranked] == ["incident:8", "incident:7"]

    third = _with_distance(
        _mountain_held().model_copy(update={"result_id": "incident:9", "name": "Creek Fire"}),
        20.0,
    )
    fourth = _with_distance(
        _mountain_held().model_copy(update={"result_id": "incident:10", "name": "Valley Fire"}),
        30.0,
    )
    ranked_records = ranked_live_results_for_request(
        "Can you list the 3 live records closest to Kelowna?",
        [first, second, third, fourth],
    )
    assert [item.result_id for item in ranked_records] == [
        "incident:8",
        "incident:7",
        "incident:9",
    ]


def test_closest_fire_ignores_a_nearer_perimeter_and_breaks_ties_by_id() -> None:
    incident_b = _with_distance(_mountain_held(), 12.0)
    incident_a = _with_distance(
        _mountain_held().model_copy(update={"result_id": "incident:1", "name": "Ridge Fire"}),
        12.0,
    )
    perimeter = _with_distance(
        _mountain_held().model_copy(
            update={
                "result_id": "perimeter:1",
                "kind": LiveResultKind.PERIMETER,
                "name": "Other perimeter",
            }
        ),
        1.0,
    )
    question = "What is the closest active fire to Kelowna?"

    assert closest_locatable_result(question, [incident_b, perimeter, incident_a]) == incident_a
    assert closest_locatable_result(question, [incident_a, perimeter, incident_b]) == incident_a
    assert "Ridge Fire" in compose_official_answer(
        QueryRequest(question=question),
        [incident_b, perimeter, incident_a],
    )


def test_closest_fire_size_question_reports_the_closest_incident_area() -> None:
    farther = _with_distance(
        _mountain_held().model_copy(update={"name": "Farther Fire", "size_hectares": 900.0}),
        12.0,
    )
    closest = _with_distance(
        _mountain_held().model_copy(
            update={"result_id": "incident:8", "name": "Closest Fire", "size_hectares": 7.0}
        ),
        4.0,
    )

    answer = compose_official_answer(
        QueryRequest(question="How big is the closest fire to Kamloops?"),
        [farther, closest],
    )

    assert "Closest Fire" in answer
    assert "7 hectares" in answer
    assert "Farther Fire" not in answer


def test_selected_record_explains_distance_clock_and_unknowns_without_model_inference() -> None:
    selected = _with_distance(_mountain_held(), 12.0)
    context = MapContext(selected_live_result_id=selected.result_id)

    rationale = compose_official_answer(
        QueryRequest(
            question="Why do you believe this fire is the closest one?",
            context=context,
        ),
        [selected],
    )
    clocks = compose_official_answer(
        QueryRequest(
            question=(
                "What is the difference between when the official source updated this fire "
                "and when FireLens retrieved it?"
            ),
            context=context,
        ),
        [selected],
    )
    unknowns = compose_official_answer(
        QueryRequest(
            question="What information about this fire are you not certain about?",
            context=context,
        ),
        [selected],
    )

    assert "12 km" in rationale
    assert "not a judgment" in rationale.casefold()
    assert human_time(selected.source_updated_at) in clocks
    assert human_time(selected.retrieved_at) in clocks
    assert "two different clocks" in clocks
    assert "how it will spread" in unknowns
    assert "whether anyone should evacuate" in unknowns


def test_named_selected_location_cannot_publish_a_stale_selected_record() -> None:
    bald = _mountain_held().model_copy(update={"name": "Bald Range"})
    pine = _mountain_held().model_copy(
        update={"result_id": "incident:pine", "name": "Pine Fire"}
    )
    request = QueryRequest(
        question="Where is Pine Fire?",
        history=[
            ConversationTurn(
                role="assistant", content="Bald Range: Being Held. Pine Fire: Under Control."
            )
        ],
        context=MapContext(selected_live_result_id=bald.result_id),
    )
    response = _build_ask_response(
        request,
        AgentPacket(live_results=[bald, pine]),
        "stale provider prose",
    )

    assert response.response_mode == ResponseMode.ABSTENTION
    assert "no longer in the current official publication" in (response.answer or "")
    assert "Bald Range" not in (response.answer or "")


@pytest.mark.parametrize("question", ("Where is Bald Range?", "Where’s Bald Range?"))
def test_named_selected_location_publishes_only_the_exact_selected_record(
    question: str,
) -> None:
    bald = _mountain_held().model_copy(update={"name": "Bald Range"})
    pine = _mountain_held().model_copy(
        update={"result_id": "incident:pine", "name": "Pine Fire"}
    )
    request = QueryRequest(
        question=question,
        history=[
            ConversationTurn(
                role="assistant", content="Bald Range: Being Held. Pine Fire: Under Control."
            )
        ],
        context=MapContext(selected_live_result_id=bald.result_id),
    )
    response = _build_ask_response(
        request, AgentPacket(live_results=[bald, pine]), "provider prose"
    )

    assert response.response_mode == ResponseMode.LIVE
    assert response.selected_live_result_id == bald.result_id
    assert "Bald Range" in (response.answer or "")
    assert "Pine Fire" not in (response.answer or "")


def test_closest_three_fact_request_returns_exactly_three_numbered_facts() -> None:
    selected = _with_distance(_mountain_held(), 12.0).model_copy(update={"size_hectares": 84.0})

    answer = compose_official_answer(
        QueryRequest(
            question="Give me only the three most important facts about the closest fire to Kelowna."
        ),
        [selected],
    )

    assert answer.count("1.") == 1
    assert answer.count("2.") == 1
    assert answer.count("3.") == 1
    assert "Mountain Fire" in answer
    assert "Being Held" in answer
    assert "12 km" in answer


def test_province_distribution_ignores_retained_community_location() -> None:
    live = _FixedLiveService(
        [
            _mountain_held().model_copy(
                update={"status": "Fire of Note", "fire_centre": "Southeast Fire Centre"}
            ),
            _mountain_held().model_copy(
                update={
                    "result_id": "incident:8",
                    "name": "Coastal Fire",
                    "fire_centre": "Coastal Fire Centre",
                }
            ),
        ]
    )
    agent = FireLensAgent(
        cast(Any, _SilentStatic(_FixedProseProvider("unused"))),
        LiveAnswerCoordinator(cast(Any, live)),
    )

    execution = asyncio.run(
        agent.answer(
            QueryRequest(
                question="Give me a distribution of the current wildfire in BC",
                location=LocationInput(label="Kelowna"),
            )
        )
    )

    assert execution.response.response_mode == ResponseMode.LIVE
    assert "Grouped by the fire centre" in (execution.response.answer or "")
    assert execution.response.resolved_location is None
    assert live.map_calls >= 1
    assert live.nearby_calls == 0


def test_live_contract_accepts_record_bound_status() -> None:
    response = _live_response(
        answer="Current official information: Mountain Fire: Being Held.",
        result=_mountain_held(),
    )
    assert response.proof_cards[0].support_state == "live_record"
    assert response.proof_cards[0].claim_text == "Mountain Fire"
    assert "Being Held" in (response.answer or "")


def _canonical_live_text() -> str:
    return "Current official information: Mountain Fire: Being Held."


def _sectioned_live_response(answer: str) -> AskResponse:
    canonical = _canonical_live_text()
    record = _mountain_held()
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="live-section-binding",
        response_mode=ResponseMode.LIVE,
        answer=answer,
        answer_sections=[
            AnswerSection(
                kind=AnswerSectionKind.CURRENT_RECORDS,
                heading="Current official records",
                text=canonical,
            )
        ],
        live_results=[record],
        aggregate_freshness=aggregate_live_freshness([record]),
        limitations=["This uses official records and is not a safety assessment."],
    )


@pytest.mark.parametrize(
    "answer",
    (
        "Out of Control. " + _canonical_live_text(),
        _canonical_live_text() + " There are 999 active wildfires.",
    ),
)
def test_live_contract_rejects_malicious_top_level_prefix_or_suffix(answer: str) -> None:
    with pytest.raises(ValidationError, match="canonical current-record composition"):
        _sectioned_live_response(answer)


def test_live_contract_accepts_canonical_sectioned_current_records() -> None:
    response = _sectioned_live_response(_canonical_live_text())
    assert response.answer == _canonical_live_text()
    assert response.answer_sections[0].kind == AnswerSectionKind.CURRENT_RECORDS


_REVIEWED_WITH_LIVE_LOOKING_FACTS = (
    "Keep water in a grab-and-go bag even if there are 999 active wildfires "
    "or you live outside a 10 kilometre radius."
)


def _mixed_response(
    answer: str, *, reviewed: str = _REVIEWED_WITH_LIVE_LOOKING_FACTS
) -> AskResponse:
    live_text = _canonical_live_text()
    record = _mountain_held()
    evidence = PublicEvidence(
        evidence_id="E1",
        title="Official preparedness guide",
        publisher="PreparedBC",
        canonical_url=HttpUrl("https://example.test/preparedness"),
        locator="Section 1",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text="Official supporting text.",
        context_text="Official supporting text in context.",
    )
    claim = PublicClaim(
        claim_id="C1",
        text=reviewed,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Official supporting text.")],
        publication=explanation_authority(),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="mixed-section-binding",
        response_mode=ResponseMode.MIXED,
        answer=answer,
        answer_sections=[
            AnswerSection(
                kind=AnswerSectionKind.CURRENT_RECORDS,
                heading="Current official records",
                text=live_text,
            ),
            AnswerSection(
                kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                heading="Reviewed guidance",
                text=reviewed,
            ),
        ],
        claims=[claim],
        evidence=[evidence],
        validation=ValidationReport(
            accepted=True,
            schema_valid=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
        live_results=[record],
        aggregate_freshness=aggregate_live_freshness([record]),
        limitations=["This uses official records and is not a safety assessment."],
    )


def _canonical_mixed_text() -> str:
    return _canonical_live_text() + "\n\n" + _REVIEWED_WITH_LIVE_LOOKING_FACTS


@pytest.mark.parametrize(
    "answer",
    (
        "Out of Control. " + _canonical_mixed_text(),
        _canonical_mixed_text() + " There are 999 active wildfires.",
    ),
)
def test_mixed_contract_rejects_malicious_top_level_prefix_or_suffix(answer: str) -> None:
    with pytest.raises(ValidationError, match="canonical current-record composition"):
        _mixed_response(answer)


def test_mixed_contract_accepts_canonical_composition_without_scanning_reviewed_as_live() -> (
    None
):
    response = _mixed_response(_canonical_mixed_text())
    assert response.answer == _canonical_mixed_text()
    assert "999" in (response.answer_sections[1].text)
    assert "10 kilometre" in response.answer_sections[1].text
    assert response.answer_sections[0].text == _canonical_live_text()
