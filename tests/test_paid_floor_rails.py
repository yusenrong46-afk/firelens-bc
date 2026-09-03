"""Failing-first rails for the V1.6 paid hard-probe floor (J/I/G/F families)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.agent.compose import compose_response
from firelens.agent.packet import AgentPacket
from firelens.answering.live_response_support import empty_live_response
from firelens.config import FireLensConfig
from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    PlanningDecision,
    PlanningResponse,
    QueryRelation,
    QueryRequest,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
)
from firelens.evaluation.hard_probe_expectations import OFFICIAL_HANDOFF_ANSWER
from firelens.live_contracts import CoarseResolvedLocation, LocationInput
from firelens.live_support import LiveResultKind, resolve_bc_location
from firelens.providers.fake import FakeProvider
from firelens.publication.compiler import (
    compile_high_risk_answer,
    compile_structured_claim,
    select_typed_claim_ids,
)
from firelens.publication.records import admitted_corpus_index, get_versioned
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]
_GRAB_AND_GO_HISTORY = [
    {"role": "user", "content": "What belongs in a grab-and-go bag?"},
    {
        "role": "assistant",
        "content": "Reviewed guides list water, food, radio, and documents.",
    },
]


class AdjacentGeneratingProvider(FakeProvider):
    """A provider that would reclassify follow-ups as adjacent and generate."""

    async def plan(
        self,
        messages: list[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> PlanningResponse:
        result = await super().plan(messages, output_schema=output_schema)
        return result.model_copy(
            update={
                "decision": PlanningDecision(
                    relation=QueryRelation.ADJACENT,
                    retrieval_queries=["why grab-and-go bags matter as background"],
                    required_aspects=["why that matters"],
                    explanation="Would reclassify this follow-up as adjacent background.",
                )
            }
        )


def _publication_kinds(response: Any) -> set[str]:
    kinds: set[str] = set()
    for claim in response.claims:
        publication = getattr(claim, "publication", None)
        kind = getattr(publication, "kind", None)
        if kind is not None:
            kinds.add(getattr(kind, "value", str(kind)))
    return kinds


def _structured_packet(question: str, typed_claim_id: str) -> EvidencePacket:
    record = get_versioned(typed_claim_id)
    quote = record.source_span_text
    chunk_id = ""
    canonical_url = record.canonical_url or (
        "https://www2.gov.bc.ca/gov/content/safety/emergency-preparedness-response-recovery"
    )
    document_sha256 = record.record.source_document_sha256 or "0" * 64
    for admitted_id, row in admitted_corpus_index().items():
        corpus_text = row["text"]
        if quote in corpus_text or " ".join(quote.split()) in " ".join(corpus_text.split()):
            chunk_id = admitted_id
            canonical_url = row["canonical_url"]
            document_sha256 = row["document_sha256"]
            break
    evidence_id = "E1"
    return EvidencePacket(
        question=question,
        corpus_version="paid-floor.v1",
        items=[
            EvidenceSpan(
                evidence_id=evidence_id,
                primary_chunk_ids=[chunk_id or record.source_span_ids[0]],
                chunk_ids=[chunk_id or record.source_span_ids[0]],
                primary_text=quote,
                context_text=quote,
                source_id="structured-source",
                title="Official source",
                publisher=record.authority,
                canonical_url=canonical_url,
                page_number=1,
                section_title=None,
                locator="page:1",
                temporal_class="stable_guidance",
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=document_sha256,
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(
                quote_id="E1Q1",
                evidence_id=evidence_id,
                text=quote,
            )
        ],
    )


def test_high_risk_history_followup_does_not_consult_a_generating_planner() -> None:
    async def run() -> None:
        provider = AdjacentGeneratingProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            execution = await runtime.service.execute_ask(
                QueryRequest(
                    question="Why does that matter?",
                    history=_GRAB_AND_GO_HISTORY,
                )
            )
        finally:
            await runtime.aclose()

        response = execution.response
        assert provider.plan_calls == 0
        assert all(item.stage != "background_generation" for item in execution.generations)
        assert response.response_mode == ResponseMode.SCOPE_REDIRECT
        assert response.answer == OFFICIAL_HANDOFF_ANSWER
        assert response.reason_code == ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED
        assert response.claims == []
        assert response.evidence == []

    asyncio.run(run())


def test_pets_followup_stays_quote_only_without_generation() -> None:
    async def run() -> None:
        provider = AdjacentGeneratingProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            execution = await runtime.service.execute_ask(
                QueryRequest(
                    question="What about pets?",
                    history=_GRAB_AND_GO_HISTORY,
                )
            )
        finally:
            await runtime.aclose()

        response = execution.response
        assert provider.plan_calls == 0
        assert all(item.stage != "background_generation" for item in execution.generations)
        assert response.response_mode == ResponseMode.PARTIAL
        assert _publication_kinds(response) == {"official_quote_only"}
        assert "pet" in (response.answer or "").casefold()

    asyncio.run(run())


def test_terse_smoke_question_suppresses_structured_reviewed() -> None:
    async def run() -> None:
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            execution = await runtime.service.execute_ask(QueryRequest(question="smoke?"))
        finally:
            await runtime.aclose()

        response = execution.response
        assert all(item.stage != "background_generation" for item in execution.generations)
        assert response.claims
        assert _publication_kinds(response) == {"official_quote_only"}
        assert response.response_mode == ResponseMode.PARTIAL

    asyncio.run(run())


def test_terse_bag_question_suppresses_structured_reviewed() -> None:
    async def run() -> None:
        provider = FakeProvider(dimensions=1536)
        runtime = load_runtime(FireLensConfig.from_env(ROOT), provider=provider)
        assert runtime.service is not None
        try:
            execution = await runtime.service.execute_ask(QueryRequest(question="bag?"))
        finally:
            await runtime.aclose()

        response = execution.response
        assert all(item.stage != "background_generation" for item in execution.generations)
        assert response.claims
        assert _publication_kinds(response) == {"official_quote_only"}
        assert response.response_mode == ResponseMode.PARTIAL

    asyncio.run(run())


def test_one_token_ask_excludes_structured_claims_even_with_matching_span() -> None:
    """Guard the terse-exclusivity branch itself: a one-token ask must stay
    quote-only even when retrieval surfaces an exact typed-claim source span
    and support reports a matching aspect (the qualified-provider shape)."""

    packet = _structured_packet("bag?", "TC-FIRESMART-021-01")
    assert (
        select_typed_claim_ids(
            packet,
            question="bag?",
            supported_aspects=["What belongs in a grab-and-go bag?"],
        )
        == []
    )
    response = compile_high_risk_answer("bag?", packet, trace_id="terse-span-guard")
    assert _publication_kinds(response) == {"official_quote_only"}
    assert response.response_mode == ResponseMode.PARTIAL


def test_full_contents_question_still_allows_mixed_structured_and_quote() -> None:
    packet = _structured_packet(
        "What belongs in a grab-and-go bag?",
        "TC-FIRESMART-021-01",
    )
    response = compile_high_risk_answer(
        packet.question,
        packet,
        trace_id="contents-mixed",
    )
    kinds = _publication_kinds(response)
    assert "structured_reviewed" in kinds


def test_mixed_live_down_keeps_visible_live_failure_not_pure_grounded() -> None:
    static = compile_structured_claim(
        typed_claim_id="TC-FIRESMART-021-01",
        public_claim_id="C1",
    ).response
    assert static is not None
    packet = AgentPacket(
        static_response=static,
        unavailable_layers=[LiveResultKind.EVACUATION],
        resolved_location=CoarseResolvedLocation(latitude=49.89, longitude=-119.50),
    )
    response = compose_response(
        QueryRequest(
            question=(
                "Any evacuation order near Kelowna right now, and how do I prepare "
                "my home ignition zone?"
            )
        ),
        packet,
        static.answer or "",
    )
    assert response.response_mode in {ResponseMode.PARTIAL, ResponseMode.MIXED}
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert "unavailable" in public
    assert response.unavailable_layers == [LiveResultKind.EVACUATION]


def test_all_required_layers_unavailable_is_abstention() -> None:
    response = empty_live_response(
        requested_layers=(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
        unavailable_layers=[LiveResultKind.INCIDENT, LiveResultKind.PERIMETER],
        resolved_location=CoarseResolvedLocation(latitude=49.89, longitude=-119.50),
        retrieved_at=datetime(2026, 8, 26, 18, 34, 38, tzinfo=UTC),
    )
    assert response.response_mode == ResponseMode.ABSTENTION
    assert response.status == ResponseStatus.ABSTENTION
    public = " ".join([response.answer or "", *response.limitations]).casefold()
    assert "unavailable" in public
    assert "not an all-clear" in public
    assert response.related_links
    assert "incident" in {layer.value for layer in response.unavailable_layers}


def test_empty_available_layers_with_a_place_stay_live() -> None:
    response = empty_live_response(
        requested_layers=(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
        unavailable_layers=[],
        resolved_location=CoarseResolvedLocation(latitude=49.89, longitude=-119.50),
        retrieved_at=datetime(2026, 8, 26, 18, 34, 38, tzinfo=UTC),
    )
    assert response.response_mode == ResponseMode.LIVE
    assert "no fires are listed" in (response.answer or "").casefold()


def test_okanagan_region_resolves_without_the_community_geocoder() -> None:
    async def forbidden_get(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("Okanagan must resolve from the gazetteer, not the geocoder")

    latitude, longitude = asyncio.run(
        resolve_bc_location(forbidden_get, LocationInput(label="Okanagan"))
    )
    assert 49.0 <= latitude <= 51.0
    assert -121.0 <= longitude <= -118.0
    the_valley = asyncio.run(
        resolve_bc_location(forbidden_get, LocationInput(label="the Okanagan"))
    )
    assert the_valley == (latitude, longitude)


def test_vancouver_island_region_resolves_without_the_community_geocoder() -> None:
    async def forbidden_get(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("Vancouver Island must use the bounded region gazetteer")

    latitude, longitude = asyncio.run(
        resolve_bc_location(forbidden_get, LocationInput(label="Vancouver Island"))
    )

    assert 48.0 <= latitude <= 51.0
    assert -128.0 <= longitude <= -123.0
