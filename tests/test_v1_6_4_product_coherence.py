from __future__ import annotations

from datetime import UTC, datetime

from pydantic import HttpUrl

from firelens.agent.compose import compose_response
from firelens.agent.packet import AgentPacket
from firelens.answering.input_clarity import (
    is_low_substance_question,
    missing_source_antecedent,
    missing_source_antecedent_response,
    unclear_input_response,
)
from firelens.answering.live_sample import INLINE_SAMPLE_LIMIT, sample_record_ids
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidenceStatus,
    Freshness,
    GeometryRelation,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.evaluation.v1_6_4_product_coherence import load_product_coherence_cases
from firelens.guidance_capabilities import resolve_capability
from firelens.presentation_identity import PresentationShell, ProvenanceClass
from firelens.publication.fallback import explanation_authority


def test_frozen_product_coherence_cases_include_required_questions() -> None:
    payload = load_product_coherence_cases()
    questions = {case["question"] for case in payload["cases"]}
    assert "What wildfires are currently listed in B.C.?" in questions
    assert "Current wildfire records, and what should I pack?" in questions
    assert "What are mistakes that I should avoid while evacuating?" in questions
    assert "asdf qwerty zxcv quantum foam" in questions
    assert len(payload["cases"]) >= 10


def test_evacuation_mistake_paraphrases_share_capability_and_aspects() -> None:
    payload = load_product_coherence_cases()
    cases = [case for case in payload["cases"] if case["expect"].get("capability_id")]
    assert len(cases) >= 10
    resolved = [resolve_capability(case["question"]) for case in cases]
    assert all(item is not None for item in resolved)
    ids = {item.id for item in resolved if item is not None}
    assert ids == {"evacuation_mistakes_to_avoid"}
    aspects = {tuple(item.aspects) for item in resolved if item is not None}
    assert len(aspects) == 1


def test_unclear_and_missing_source_antecedent_are_clarifications() -> None:
    assert is_low_substance_question("asdf qwerty zxcv quantum foam")
    unclear = unclear_input_response()
    assert unclear.provenance_class == ProvenanceClass.CLARIFICATION
    assert unclear.live_results == []
    request = QueryRequest(
        question="What does the official BC Wildfire Service say about this source?"
    )
    assert missing_source_antecedent(request)
    missing = missing_source_antecedent_response()
    assert missing.provenance_class == ProvenanceClass.CLARIFICATION
    assert missing.live_results == []
    assert missing.presentation_shell == PresentationShell.CHAT


def _record(index: int, *, status: str = "Being Held") -> LiveResult:
    stamp = datetime(2026, 9, 1, tzinfo=UTC)
    return LiveResult(
        result_id=f"incident:{index}",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url=HttpUrl(f"https://example.invalid/incident/{index}"),
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=Freshness.FRESH,
        status=status,
        name=f"Fire {index}" if index % 3 else None,
        incident_number=f"N{index:05d}",
        size_hectares=float(index),
        geometry={"type": "Point", "coordinates": [-119.0, 49.0]},
        geometry_relation=GeometryRelation.UNKNOWN,
        fire_of_note=index == 9,
    )


def test_mixed_pack_question_keeps_two_sections_and_chat_shell() -> None:
    live = [
        _record(index, status="Out of Control" if index > 7 else "Being Held")
        for index in range(1, 11)
    ]
    evidence = PublicEvidence(
        evidence_id="E1",
        title="Official preparedness guide",
        publisher="PreparedBC",
        canonical_url=HttpUrl("https://example.invalid/pack"),
        locator="Section 1",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text="Keep water and food in a grab-and-go bag.",
        context_text="Keep water and food in a grab-and-go bag.",
    )
    static = AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="mixed-pack",
        response_mode=ResponseMode.GROUNDED,
        answer="Keep water and food in a grab-and-go bag.",
        claims=[
            PublicClaim(
                claim_id="C1",
                text="Keep water and food in a grab-and-go bag.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=[
                    ClaimSupport(
                        evidence_id="E1", quote="Keep water and food in a grab-and-go bag."
                    )
                ],
                publication=explanation_authority(),
            )
        ],
        evidence=[evidence],
        validation=ValidationReport(
            accepted=True,
            schema_valid=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
    )
    response = compose_response(
        QueryRequest(question="Current wildfire records, and what should I pack?"),
        AgentPacket(live_results=live, static_response=static, roster_total=len(live)),
        "Provider prose is not publication authority.",
    )
    assert response.response_mode == ResponseMode.MIXED
    assert [section.kind.value for section in response.answer_sections] == [
        "current_records",
        "reviewed_guidance",
    ]
    assert response.presentation_shell == PresentationShell.CHAT
    assert response.provenance_class == ProvenanceClass.MIXED
    assert response.roster_total == 10
    assert len(response.sample_record_ids) <= INLINE_SAMPLE_LIMIT
    assert response.sample_record_ids == sample_record_ids(live)
    assert "Fire 9" in (response.answer or "") or "incident:9" in response.sample_record_ids


def test_live_multi_incident_uses_analysis_shell() -> None:
    live = [_record(1, status="Out of Control"), _record(2)]
    response = compose_response(
        QueryRequest(question="What wildfires are currently listed in B.C.?"),
        AgentPacket(live_results=live, roster_total=2),
        "Provider prose is not publication authority.",
    )
    assert response.response_mode == ResponseMode.LIVE
    assert response.presentation_shell == PresentationShell.ANALYSIS
    assert response.provenance_class == ProvenanceClass.OFFICIAL_LIVE
    assert set(
        response.live_results[i].result_id for i in range(len(response.live_results))
    ) == {
        "incident:1",
        "incident:2",
    }
