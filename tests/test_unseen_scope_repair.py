"""Direct regression coverage for the bounded unseen product journeys."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl

from firelens.agent import FireLensAgent
from firelens.agent.query_plan import AgentGeography, AgentRequestMode, plan_agent_request
from firelens.agent.tools import AgentTool
from firelens.answering.intent_automaton import parse_request_intent
from firelens.answering.location_intent import coarse_location_from_question
from firelens.answering.service import StaticRAGService
from firelens.api.answer_routes import install_answer_routes
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    CoarseResolvedLocation,
    ConversationTurn,
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
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.fallback import explanation_authority
from firelens.runtime import Runtime


def _reviewed_guidance() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Pack water and copies of important documents in the kit.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Pack water and copies")],
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
                title="Reviewed preparedness guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/guide"),
                locator="Kit section",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Pack water and copies",
                context_text="Pack water and copies of important documents in the kit.",
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


def _live_result(kind: LiveResultKind = LiveResultKind.INCIDENT) -> LiveResult:
    timestamp = datetime(2026, 8, 31, tzinfo=UTC)
    return LiveResult(
        result_id=f"{kind.value}:test-1",
        kind=kind,
        authority="BC Wildfire Service",
        source_url=HttpUrl("https://example.test/live"),
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Being Held" if kind != LiveResultKind.EVACUATION else "Alert",
        name="Test Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


class RecordingStaticService:
    provider = None

    def __init__(self, response: AskResponse) -> None:
        self.response = response
        self.questions: list[str] = []

    async def ask(
        self,
        request: QueryRequest,
        *,
        allow_live: bool = True,
        prefer_reviewed_quotes: bool = False,
    ) -> AskResponse:
        self.questions.append(request.question)
        del allow_live, prefer_reviewed_quotes
        return self.response


class RecordingLiveService:
    def __init__(self) -> None:
        self.map_layers: list[tuple[LiveResultKind, ...]] = []
        self.nearby_labels: list[str | None] = []
        self.resolve_labels: list[str | None] = []

    async def resolve_location(self, location: Any) -> tuple[float, float]:
        self.resolve_labels.append(getattr(location, "label", None))
        return 49.89, -119.49

    async def map_results(self, *, layers: tuple[LiveResultKind, ...]) -> LiveMapResponse:
        self.map_layers.append(layers)
        result = _live_result(
            LiveResultKind.EVACUATION
            if LiveResultKind.EVACUATION in layers
            else LiveResultKind.INCIDENT
        )
        return LiveMapResponse(
            generated_at=result.retrieved_at,
            results=[result],
            aggregate_freshness=aggregate_live_freshness([result]),
        )

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        layers = kwargs.get("layers", ())
        del args
        self.nearby_labels.append(getattr(location, "label", None))
        result = _live_result(
            LiveResultKind.EVACUATION
            if LiveResultKind.EVACUATION in layers
            else LiveResultKind.INCIDENT
        )
        return type(
            "Nearby",
            (),
            {
                "results": [result],
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": CoarseResolvedLocation(latitude=49.89, longitude=-119.49),
            },
        )()


def _execute_request(
    request: QueryRequest,
) -> tuple[Any, RecordingStaticService, RecordingLiveService]:
    static = RecordingStaticService(_reviewed_guidance())
    live = RecordingLiveService()
    execution = asyncio.run(
        FireLensAgent(static, LiveAnswerCoordinator(live)).answer(  # type: ignore[arg-type]
            request
        )
    )
    return execution, static, live


def _execute(question: str) -> tuple[Any, RecordingStaticService, RecordingLiveService]:
    return _execute_request(QueryRequest(question=question))


def _ask_app(
    tmp_path: Path,
    static: RecordingStaticService,
    live: RecordingLiveService,
) -> FastAPI:
    app = FastAPI()
    config = FireLensConfig.from_env(tmp_path)
    runtime = Runtime(
        config=config,
        service=cast(StaticRAGService, static),
        corpus_version="unseen-scope-repair",
    )
    install_answer_routes(
        app,
        config,
        lambda: runtime,
        LiveAnswerCoordinator(live),  # type: ignore[arg-type]
    )
    return app


async def _post_ask(app: FastAPI, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post("/api/v1/ask", json=payload)


def test_general_smoke_home_guidance_reaches_public_agent_without_location_prompt() -> None:
    execution, static, live = _execute(
        "What are practical ways to keep wildfire smoke out of my home?"
    )

    assert execution.response.response_mode in {
        ResponseMode.GROUNDED,
        ResponseMode.PARTIAL,
        ResponseMode.BACKGROUND,
    }
    assert execution.response.required_input is None
    assert "share an approximate location" not in (execution.response.answer or "").casefold()
    assert static.questions == [
        "What are practical ways to keep wildfire smoke out of my home?"
    ]
    assert live.nearby_labels == []
    assert live.map_layers == []


def test_province_live_plus_kit_reaches_public_agent_as_mixed_and_executes_static_clause() -> (
    None
):
    question = "List active BC fires and summarize their reported status, then give general kit guidance."
    plan = plan_agent_request(QueryRequest(question=question))
    execution, static, live = _execute(question)

    assert execution.response.response_mode == ResponseMode.MIXED
    assert execution.response.answer is not None
    assert "Pack water and copies" in execution.response.answer
    # The immutable plan retains the user's clause; the reviewed static
    # boundary receives its typed retrieval/publication question.
    assert plan.static_subrequest == "give general kit guidance"
    assert plan.tool_calls[-1].as_arguments() == {"query": "give general kit guidance"}
    assert static.questions == ["emergency kit contents checklist"]
    assert live.map_layers == [(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)]
    assert execution.tools == (
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    )


@pytest.mark.parametrize(
    ("question", "expected_tool", "expected_place"),
    (
        ("show fIres arnd kelowna", AgentTool.LIST_OFFICIAL_FIRES, "kelowna"),
        ("closest moutain fire vernon", AgentTool.LIST_OFFICIAL_FIRES, "vernon"),
        ("evac alert kelowna rn", AgentTool.LIST_OFFICIAL_EVACUATIONS, "kelowna"),
    ),
)
def test_compressed_live_questions_execute_location_scoped_tool(
    question: str, expected_tool: AgentTool, expected_place: str
) -> None:
    execution, _static, live = _execute(question)

    assert expected_tool in execution.tools
    assert live.nearby_labels == [expected_place]
    assert execution.response.required_input is None
    assert execution.response.response_mode == ResponseMode.LIVE


@pytest.mark.parametrize(
    "question",
    (
        "What are practical ways to keep wildfire smoke out of my home?",
        "How can I stop wildfire smoke getting inside my house?",
    ),
)
def test_general_smoke_home_guidance_is_static_without_location(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.RELATED
    assert plan.mode == AgentRequestMode.STATIC
    assert plan.geography == AgentGeography.NONE
    assert plan.live_layers == ()
    assert plan.tool_calls[0].name == AgentTool.SEARCH_REVIEWED_GUIDANCE


@pytest.mark.parametrize(
    "question",
    (
        "List active BC fires and summarize their reported status, then give general kit guidance.",
        "Show active fires across BC, then tell me what to pack in an emergency kit.",
    ),
)
def test_province_live_and_general_kit_guidance_keep_both_lanes(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.MIXED
    assert plan.geography == AgentGeography.PROVINCE_WIDE
    assert plan.live_layers == (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
    assert plan.static_subrequest is not None
    assert "kit" in plan.static_subrequest.casefold()
    assert [call.name for call in plan.tool_calls] == [
        AgentTool.LIST_OFFICIAL_FIRES,
        AgentTool.SEARCH_REVIEWED_GUIDANCE,
    ]


@pytest.mark.parametrize(
    ("question", "expected_place"),
    (
        ("show fIres arnd kelowna", "kelowna"),
        ("show fires around Kelowna", "kelowna"),
    ),
)
def test_compressed_around_form_binds_named_fire_lookup(
    question: str, expected_place: str
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert location is not None and location.label is not None
    assert location.label.casefold() == expected_place
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label is not None
    assert plan.location_label.casefold() == expected_place
    assert plan.tool_calls[0].as_arguments() == {"place_label": plan.location_label}


@pytest.mark.parametrize(
    ("question", "expected_place"),
    (
        ("closest moutain fire vernon", "vernon"),
        ("nearest mountain fire Vernon", "vernon"),
    ),
)
def test_closest_compressed_form_preserves_location_and_closest_operation(
    question: str, expected_place: str
) -> None:
    parsed = parse_request_intent(question)
    location = coarse_location_from_question(question)
    plan = plan_agent_request(QueryRequest(question=question))

    assert parsed.has_live_records
    assert parsed.clauses[0].operation is not None
    assert parsed.clauses[0].operation.value == "locate"
    assert location is not None and location.label is not None
    assert location.label.casefold() == expected_place
    assert plan.location_label is not None
    assert plan.location_label.casefold() == expected_place
    assert "mountain" not in plan.location_label.casefold()


@pytest.mark.parametrize(
    "question",
    (
        "evac alert kelowna rn",
        "current evacuation alert in Kelowna",
    ),
)
def test_compact_evacuation_question_selects_official_local_layer(question: str) -> None:
    plan = plan_agent_request(QueryRequest(question=question))

    assert plan.route == QueryRoute.LIVE
    assert plan.mode == AgentRequestMode.LIVE
    assert plan.geography == AgentGeography.LOCATION_RADIUS
    assert plan.location_label is not None
    assert plan.location_label.casefold() == "kelowna"
    assert plan.live_layers == (LiveResultKind.EVACUATION,)
    assert plan.tool_calls[0].name == AgentTool.LIST_OFFICIAL_EVACUATIONS
    assert plan.tool_calls[0].as_arguments() == {"place_label": plan.location_label}
    assert "high-risk" not in str(plan.terminal_response).casefold()


@pytest.mark.parametrize(
    "question",
    (
        "Tell me whether I personally should drive through this fire area.",
        "Can you tell me if it is safe for me to drive through this wildfire area?",
    ),
)
def test_personal_travel_decision_is_a_deterministic_no_tool_abstention(
    question: str,
) -> None:
    execution, static, live = _execute(question)

    assert execution.response.status == ResponseStatus.ABSTENTION
    assert execution.response.response_mode == ResponseMode.ABSTENTION
    assert execution.response.reason_code == ReasonCode.PERSONALIZED_SAFETY_DECISION
    assert (
        "cannot decide whether you should drive" in (execution.response.answer or "").casefold()
    )
    assert execution.tools == ()
    assert static.questions == []
    assert live.map_layers == []
    assert live.nearby_labels == []


@pytest.mark.parametrize(
    "question",
    ("Actually, I meant Vernon.", "Actually I meant Vernon instead."),
)
def test_live_place_correction_replaces_prior_scope_without_implicit_record_selection(
    question: str,
) -> None:
    execution, static, live = _execute_request(
        QueryRequest(
            question=question,
            history=[
                ConversationTurn(role="user", content="Show current fires around Kelowna."),
                ConversationTurn(
                    role="assistant", content="Current official information for Kelowna."
                ),
            ],
            context=MapContext(visible_live_result_ids=["incident:1", "incident:2"]),
        )
    )

    assert execution.route == QueryRoute.LIVE
    assert execution.response.response_mode == ResponseMode.LIVE
    assert execution.tools == (AgentTool.LIST_OFFICIAL_FIRES,)
    assert static.questions == []
    assert live.nearby_labels == ["Vernon"]
    assert "Kelowna" not in live.nearby_labels


@pytest.mark.parametrize(
    "question",
    ("What about pets?", "What about supplies for my pets?"),
)
def test_pets_followup_uses_reviewed_preparedness_retrieval_with_prior_context(
    question: str,
) -> None:
    execution, static, live = _execute_request(
        QueryRequest(
            question=question,
            history=[
                ConversationTurn(
                    role="user", content="What should I include in an emergency kit?"
                ),
                ConversationTurn(role="assistant", content="Pack water and copies."),
            ],
        )
    )

    assert execution.response.response_mode == ResponseMode.GROUNDED
    assert execution.response.reason_code is None
    assert execution.tools == (AgentTool.SEARCH_REVIEWED_GUIDANCE,)
    assert len(static.questions) == 1
    assert "pet" in static.questions[0].casefold()
    assert "emergency kit" in static.questions[0].casefold()
    assert live.map_layers == []
    assert live.nearby_labels == []


@pytest.mark.parametrize(
    "question",
    (
        "Tell me whether I personally should drive through this fire area.",
        "Can you tell me if it is safe for me to drive through this wildfire area?",
    ),
)
def test_ask_api_keeps_personal_travel_decisions_out_of_tools(
    tmp_path: Path, question: str
) -> None:
    static = RecordingStaticService(_reviewed_guidance())
    live = RecordingLiveService()
    response = asyncio.run(_post_ask(_ask_app(tmp_path, static, live), {"question": question}))

    assert response.status_code == 200
    body = response.json()
    assert body["response_mode"] == ResponseMode.ABSTENTION.value
    assert body["reason_code"] == ReasonCode.PERSONALIZED_SAFETY_DECISION.value
    assert static.questions == []
    assert live.map_layers == []
    assert live.nearby_labels == []


@pytest.mark.parametrize(
    "question",
    ("Actually, I meant Vernon.", "Actually I meant Vernon instead."),
)
def test_ask_api_runs_a_new_vernon_lookup_for_live_place_corrections(
    tmp_path: Path, question: str
) -> None:
    static = RecordingStaticService(_reviewed_guidance())
    live = RecordingLiveService()
    response = asyncio.run(
        _post_ask(
            _ask_app(tmp_path, static, live),
            {
                "question": question,
                "history": [
                    {"role": "user", "content": "Show current fires around Kelowna."},
                    {
                        "role": "assistant",
                        "content": "Current official information for Kelowna.",
                    },
                ],
                "context": {"visible_live_result_ids": ["incident:1", "incident:2"]},
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["response_mode"] == ResponseMode.LIVE.value
    assert static.questions == []
    assert live.nearby_labels == ["Vernon"]


@pytest.mark.parametrize(
    "question",
    ("What about pets?", "What about supplies for my pets?"),
)
def test_ask_api_keeps_pets_followups_in_reviewed_preparedness_retrieval(
    tmp_path: Path, question: str
) -> None:
    static = RecordingStaticService(_reviewed_guidance())
    live = RecordingLiveService()
    response = asyncio.run(
        _post_ask(
            _ask_app(tmp_path, static, live),
            {
                "question": question,
                "history": [
                    {
                        "role": "user",
                        "content": "What should I include in an emergency kit?",
                    },
                    {"role": "assistant", "content": "Pack water and copies."},
                ],
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["response_mode"] == ResponseMode.GROUNDED.value
    assert len(static.questions) == 1
    assert "pet" in static.questions[0].casefold()
    assert "emergency kit" in static.questions[0].casefold()
    assert live.map_layers == []
