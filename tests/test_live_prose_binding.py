"""Live public answers must be bound to fetched typed records."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import HttpUrl, ValidationError

from firelens.agent import FireLensAgent
from firelens.agent.chat import ChatTurn
from firelens.contracts import (
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    ClaimSupport,
    EvidenceStatus,
    Freshness,
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


class _FixedLiveService:
    def __init__(self, results: list[LiveResult]) -> None:
        self.results = results

    async def map_results(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
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


@pytest.mark.parametrize("prose", UNBOUND_LIVE_PROSE)
def test_live_contract_rejects_unbound_prose_over_typed_records(prose: str) -> None:
    with pytest.raises(ValidationError):
        _live_response(answer=prose, result=_mountain_held())


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
