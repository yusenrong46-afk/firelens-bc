from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import HttpUrl, ValidationError

from firelens.answering.grounded import GroundedAnswerEngine
from firelens.answering.live_handoffs import merge_related_links
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    DETERMINISTIC_CONFLICT_TEXT,
    MAX_RELATED_LINKS,
    PUBLIC_ANSWER_MAX_CHARS,
    RELATED_LINK_DESCRIPTION_MAX_CHARS,
    RELATED_LINK_TITLE_MAX_CHARS,
    AggregateFreshness,
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    AuthorityClass,
    ClaimSupport,
    ConversationTurn,
    EvidencePacket,
    EvidenceSpan,
    EvidenceStatus,
    Freshness,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
    render_claim_texts,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.publication.compiler import background_authority, explanation_authority


def _accepted_validation() -> ValidationReport:
    return ValidationReport(
        accepted=True,
        citation_ids_valid=True,
        quotes_exact=True,
        claim_support_valid=True,
        policy_valid=True,
    )


def _public_evidence() -> PublicEvidence:
    return PublicEvidence(
        evidence_id="E1",
        title="Official preparedness guide",
        publisher="PreparedBC",
        canonical_url=HttpUrl("https://example.test/preparedness"),
        locator="Section 1",
        temporal_class=TemporalClass.STABLE_GUIDANCE,
        primary_text="Official supporting text.",
        context_text="Official supporting text in context.",
    )


def _grounded_claim(index: int, text: str) -> PublicClaim:
    return PublicClaim(
        claim_id=f"C{index}",
        text=text,
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Official supporting text.")],
        publication=explanation_authority(),
    )


def _related_link(index: int, *, url: str | None = None) -> RelatedLink:
    return RelatedLink(
        title=f"Static source {index}",
        url=HttpUrl(url or f"https://example.test/static/{index}"),
        description="Official related source.",
    )


def _incident(index: int, *, maximum_labels: bool = False) -> LiveResult:
    timestamp = datetime(2026, 8, 14, tzinfo=UTC)
    return LiveResult(
        result_id=f"incident:{index}",
        kind=LiveResultKind.INCIDENT,
        source_url=f"https://example.test/live/{index}",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="S" * 200 if maximum_labels else "Being Held",
        name="N" * 300 if maximum_labels else f"Test Fire {index}",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


class FixedLiveService:
    def __init__(self, results: list[LiveResult]) -> None:
        self.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 14, tzinfo=UTC),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        return self.response


class PublicContractBoundTests(unittest.TestCase):
    def test_public_answer_and_claim_count_reject_overflow(self) -> None:
        AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="a" * 32,
            response_mode=ResponseMode.CAPABILITY,
            answer="x" * PUBLIC_ANSWER_MAX_CHARS,
        )
        with self.assertRaises(ValidationError):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="b" * 32,
                response_mode=ResponseMode.CAPABILITY,
                answer="x" * (PUBLIC_ANSWER_MAX_CHARS + 1),
            )

        claims = [
            PublicClaim(
                claim_id=f"C{index}",
                text=f"Background claim {index}.",
                evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
                publication=background_authority(),
            )
            for index in range(1, 14)
        ]
        with self.assertRaises(ValidationError):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="c" * 32,
                response_mode=ResponseMode.BACKGROUND,
                answer=render_claim_texts(claims),
                claims=claims,
                limitations=[BACKGROUND_LIMITATION],
            )

    def test_grounded_and_background_answers_are_canonical(self) -> None:
        claim = _grounded_claim(1, "Keep water in an emergency kit.")
        with self.assertRaisesRegex(ValidationError, "rendered from its public claims"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="d" * 32,
                response_mode=ResponseMode.GROUNDED,
                answer="Different unsupported wording.",
                claims=[claim],
                evidence=[_public_evidence()],
            )

        background_claim = PublicClaim(
            claim_id="C1",
            text="Wildfire smoke can affect air quality.",
            evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            publication=background_authority(),
        )
        with self.assertRaisesRegex(ValidationError, "rendered from its public claims"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="e" * 32,
                response_mode=ResponseMode.BACKGROUND,
                answer="Different background wording.",
                claims=[background_claim],
                limitations=[BACKGROUND_LIMITATION],
            )

    def test_authority_section_text_must_match_typed_claims(self) -> None:
        claim = _grounded_claim(1, "Keep water in an emergency kit.")
        with self.assertRaisesRegex(ValidationError, "typed public claims"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="f" * 32,
                response_mode=ResponseMode.PARTIAL,
                answer="Reviewed guidance is shown below.",
                answer_sections=[
                    AnswerSection(
                        kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                        heading="Reviewed guidance",
                        text="Text that is not the validated public claim.",
                    )
                ],
                claims=[claim],
                evidence=[_public_evidence()],
            )

    def test_conflict_prose_requires_the_deterministic_renderer(self) -> None:
        claim = _grounded_claim(1, "One source contains a conflicting requirement.")
        with self.assertRaisesRegex(ValidationError, "deterministic conflict"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="1" * 32,
                response_mode=ResponseMode.CONFLICT,
                answer="Completely unrelated conflict summary.",
                answer_sections=[
                    AnswerSection(
                        kind=AnswerSectionKind.CONFLICTING_GUIDANCE,
                        heading="Conflicting reviewed sources",
                        text="Arbitrary prose not present in the validated conflict renderer.",
                    )
                ],
                claims=[claim],
                evidence=[_public_evidence()],
                reason_code=ReasonCode.CONFLICTING_EVIDENCE,
                validation=_accepted_validation(),
            )

        canonical = DETERMINISTIC_CONFLICT_TEXT
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="2" * 32,
            response_mode=ResponseMode.CONFLICT,
            answer=canonical,
            claims=[claim],
            evidence=[_public_evidence()],
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            validation=_accepted_validation(),
        )
        self.assertEqual(response.answer, canonical)

        with self.assertRaisesRegex(ValidationError, "deterministic conflict"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="5" * 32,
                response_mode=ResponseMode.CONFLICT,
                answer="Unsupported direction. " + canonical,
                answer_sections=[
                    AnswerSection(
                        kind=AnswerSectionKind.CONFLICTING_GUIDANCE,
                        heading="Conflicting reviewed sources",
                        text=canonical,
                    )
                ],
                claims=[claim],
                evidence=[_public_evidence()],
                reason_code=ReasonCode.CONFLICTING_EVIDENCE,
                validation=_accepted_validation(),
            )

    def test_mixed_conflict_rejects_arbitrary_answer_edges_and_section_text(self) -> None:
        claim = _grounded_claim(1, "One source contains a conflicting requirement.")
        live_result = _incident(1)
        live_text = "Test Fire 1 is being held."
        canonical_answer = (
            live_text + "\n\nConflicting reviewed sources: " + DETERMINISTIC_CONFLICT_TEXT
        )
        sections = [
            AnswerSection(
                kind=AnswerSectionKind.CURRENT_RECORDS,
                heading="Current official records",
                text=live_text,
            ),
            AnswerSection(
                kind=AnswerSectionKind.CONFLICTING_GUIDANCE,
                heading="Conflicting reviewed sources",
                text=DETERMINISTIC_CONFLICT_TEXT,
            ),
        ]
        common = {
            "status": ResponseStatus.ANSWER,
            "trace_id": "a" * 32,
            "response_mode": ResponseMode.MIXED,
            "claims": [claim],
            "evidence": [_public_evidence()],
            "reason_code": ReasonCode.CONFLICTING_EVIDENCE,
            "validation": _accepted_validation(),
            "live_results": [live_result],
            "aggregate_freshness": AggregateFreshness.FRESH,
        }

        accepted = AskResponse(answer=canonical_answer, answer_sections=sections, **common)
        self.assertEqual(accepted.answer, canonical_answer)

        for answer in (
            "Unsupported direction. " + canonical_answer,
            canonical_answer + " Unsupported direction.",
        ):
            with (
                self.subTest(answer=answer),
                self.assertRaisesRegex(ValidationError, "deterministic conflict"),
            ):
                AskResponse(answer=answer, answer_sections=sections, **common)

        arbitrary_conflict = "Arbitrary prose not emitted by the conflict renderer."
        with self.assertRaisesRegex(ValidationError, "deterministic conflict"):
            AskResponse(
                answer=(live_text + "\n\nConflicting reviewed sources: " + arbitrary_conflict),
                answer_sections=[
                    sections[0],
                    AnswerSection(
                        kind=AnswerSectionKind.CONFLICTING_GUIDANCE,
                        heading="Conflicting reviewed sources",
                        text=arbitrary_conflict,
                    ),
                ],
                **common,
            )

    def test_live_history_labels_validated_record_freshness(self) -> None:
        stale = _incident(1).model_copy(update={"freshness": Freshness.STALE})
        live = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="3" * 32,
            response_mode=ResponseMode.LIVE,
            answer="Cached Fire is listed.",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading="Official records (cached; refresh failed)",
                    text="Cached Fire is listed.",
                )
            ],
            live_results=[stale],
            aggregate_freshness=AggregateFreshness.STALE,
        )
        self.assertTrue(
            (live.history_text or "").startswith("Authority: Official cached records")
        )

        claim = _grounded_claim(1, "Keep water in an emergency kit.")
        mixed = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="4" * 32,
            response_mode=ResponseMode.MIXED,
            answer="Cached Fire is listed. Keep water in an emergency kit.",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading="Official records (cached; refresh failed)",
                    text="Cached Fire is listed.",
                ),
                AnswerSection(
                    kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                    heading="Reviewed guidance",
                    text=claim.text,
                ),
            ],
            claims=[claim],
            evidence=[_public_evidence()],
            validation=_accepted_validation(),
            live_results=[stale],
            aggregate_freshness=AggregateFreshness.STALE,
        )
        history = mixed.history_text or ""
        self.assertIn("Official cached records", history)
        self.assertNotIn("Official current records", history)

    def test_current_record_section_rejects_reviewed_claim_text(self) -> None:
        claim = _grounded_claim(1, "Keep water in an emergency kit.")
        live = _incident(1)

        with self.assertRaisesRegex(ValidationError, "current record section"):
            AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="8" * 32,
                response_mode=ResponseMode.MIXED,
                answer="Test Fire 1 is being held. Keep water in an emergency kit.",
                answer_sections=[
                    AnswerSection(
                        kind=AnswerSectionKind.CURRENT_RECORDS,
                        heading="Current official records",
                        text="Test Fire 1 is being held. Keep water in an emergency kit.",
                    ),
                    AnswerSection(
                        kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                        heading="Reviewed guidance",
                        text=claim.text,
                    ),
                ],
                claims=[claim],
                evidence=[_public_evidence()],
                validation=_accepted_validation(),
                live_results=[live],
                aggregate_freshness=AggregateFreshness.FRESH,
            )

    def test_history_keeps_authority_and_deduplicated_limitations(self) -> None:
        claim = PublicClaim(
            claim_id="C1",
            text="Wildfire smoke can affect air quality.",
            evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            publication=background_authority(),
        )
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="6" * 32,
            response_mode=ResponseMode.BACKGROUND,
            answer=claim.text,
            claims=[claim],
            limitations=[BACKGROUND_LIMITATION, BACKGROUND_LIMITATION],
        )

        self.assertIsNotNone(response.history_text)
        history = response.history_text or ""
        self.assertTrue(
            history.startswith("Authority: General background (not corpus-verified). Answer:")
        )
        self.assertEqual(history.count(BACKGROUND_LIMITATION), 1)
        self.assertNotIn("mode=", history)

    def test_maximum_answer_history_keeps_its_limitation_visible(self) -> None:
        limitation = "Current official records were unavailable."
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="9" * 32,
            response_mode=ResponseMode.CAPABILITY,
            answer="A" * PUBLIC_ANSWER_MAX_CHARS,
            limitations=[limitation],
        )

        history = response.history_text or ""
        self.assertEqual(len(history), PUBLIC_ANSWER_MAX_CHARS)
        self.assertTrue(history.startswith("Authority: FireLens capability information."))
        self.assertIn("Answer: ", history)
        self.assertTrue(history.endswith("Limitations: " + limitation))

    def test_two_turn_history_preserves_section_authority_and_uncertainty(self) -> None:
        claim = _grounded_claim(1, "Keep water in an emergency kit.")
        limitation = "Current official records were unavailable."
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="7" * 32,
            response_mode=ResponseMode.PARTIAL,
            answer=("Current information unavailable. Preparedness guidance: " + claim.text),
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.UNCERTAINTY,
                    heading="Current information unavailable",
                    text="Current information unavailable.",
                ),
                AnswerSection(
                    kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                    heading="Reviewed preparedness guidance",
                    text=claim.text,
                ),
            ],
            claims=[claim],
            evidence=[_public_evidence()],
            limitations=[limitation, limitation],
            validation=_accepted_validation(),
        )
        follow_up = QueryRequest(
            question="What does that limitation mean?",
            history=[
                ConversationTurn(role="user", content="What should I prepare?"),
                ConversationTurn(role="assistant", content=response.history_text or ""),
            ],
        )

        assistant_turn = follow_up.history[1].content
        self.assertIn("Authority: Uncertainty", assistant_turn)
        self.assertIn("Reviewed guidance", assistant_turn)
        self.assertIn("Limitations: " + limitation, assistant_turn)
        self.assertEqual(assistant_turn.count(limitation), 1)

    def test_safety_history_uses_plain_language_boundary(self) -> None:
        response = AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id="8" * 32,
            response_mode=ResponseMode.ABSTENTION,
            answer="Use the issuing authority for a personal evacuation decision.",
            reason_code=ReasonCode.PERSONALIZED_SAFETY_DECISION,
            limitations=["FireLens cannot decide whether a person should evacuate."],
        )

        history = response.history_text or ""
        self.assertTrue(history.startswith("Safety boundary:"))
        self.assertIn("personal safety or evacuation decision", history)
        self.assertNotIn("personalized_safety_decision", history)

    def test_related_link_merge_is_url_deduped_and_has_stable_priority(self) -> None:
        live = RelatedLink(
            title="Current B.C. AQHI",
            url=HttpUrl("https://weather.gc.ca/airquality/bc"),
            description="Current official air-quality information.",
        )
        static = [_related_link(index) for index in range(4)]

        merged = merge_related_links(
            live_handoff_links=[live],
            static_handoff_links=static,
        )

        self.assertEqual(
            [str(link.url) for link in merged],
            [str(live.url), *(str(link.url) for link in static[:3])],
        )
        self.assertEqual(len(merged), MAX_RELATED_LINKS)

        duplicate_static = [
            _related_link(0, url=str(live.url)),
            *static[1:],
        ]
        deduped = merge_related_links(
            live_handoff_links=[live],
            static_handoff_links=duplicate_static,
        )
        self.assertEqual(
            [str(link.url) for link in deduped],
            [str(live.url), *(str(link.url) for link in static[1:4])],
        )

    def test_source_handoff_bounds_display_metadata_without_changing_url(self) -> None:
        source_url = "https://example.test/official-source"
        packet = EvidencePacket(
            question="What source is related?",
            corpus_version="test.v1",
            items=[
                EvidenceSpan(
                    evidence_id="E1",
                    primary_chunk_ids=["chunk-1"],
                    chunk_ids=["chunk-1"],
                    primary_text="Official text.",
                    context_text="Official text in context.",
                    source_id="source-1",
                    title="T" * (RELATED_LINK_TITLE_MAX_CHARS + 1),
                    publisher="P" * RELATED_LINK_DESCRIPTION_MAX_CHARS,
                    canonical_url=source_url,
                    page_number=None,
                    section_title=None,
                    locator=None,
                    temporal_class=TemporalClass.STABLE_GUIDANCE,
                    authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                    document_sha256="a" * 64,
                )
            ],
        )

        response = GroundedAnswerEngine.source_handoff(
            "2" * 32,
            packet,
            answer="Open the official source.",
            reason_code=ReasonCode.GENERATION_UNAVAILABLE,
            extra_limitation="No generated claim was published.",
        )

        link = response.related_links[0]
        self.assertEqual(str(link.url), source_url)
        self.assertLessEqual(len(link.title), RELATED_LINK_TITLE_MAX_CHARS)
        self.assertLessEqual(len(link.description), RELATED_LINK_DESCRIPTION_MAX_CHARS)
        self.assertTrue(link.title.endswith("..."))
        self.assertTrue(link.description.endswith("..."))


class CompositionBoundTests(unittest.IsolatedAsyncioTestCase):
    async def test_maximum_valid_composition_stays_within_public_answer_bound(self) -> None:
        claim_lengths = [500, 500, 500, 500, 496]
        claims = [
            _grounded_claim(index, "G" * length)
            for index, length in enumerate(claim_lengths, start=1)
        ]
        canonical_answer = render_claim_texts(claims)
        self.assertEqual(len(canonical_answer), 2_500)
        static_result = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="3" * 32,
            response_mode=ResponseMode.GROUNDED,
            answer=canonical_answer,
            claims=claims,
            evidence=[_public_evidence()],
            validation=_accepted_validation(),
        )
        coordinator = LiveAnswerCoordinator(
            cast(Any, FixedLiveService([_incident(i, maximum_labels=True) for i in range(5)]))
        )

        response = await coordinator.answer(
            QueryRequest(question="Show active wildfires in BC and current air quality."),
            static_result,
        )

        reviewed = next(
            section
            for section in response.answer_sections
            if section.kind == AnswerSectionKind.REVIEWED_GUIDANCE
        )
        self.assertEqual(reviewed.text, canonical_answer)
        self.assertEqual(response.claims, claims)
        self.assertEqual(response.validation, static_result.validation)
        self.assertLessEqual(len(response.answer or ""), PUBLIC_ANSWER_MAX_CHARS)

    async def test_scope_handoff_merge_keeps_live_and_static_destinations(self) -> None:
        static_links = [_related_link(index) for index in range(4)]
        static_result = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="4" * 32,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer="Open the related official sources.",
            related_links=static_links,
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService([_incident(1)])))

        response = await coordinator.answer(
            QueryRequest(question="Show active wildfires in BC and current air quality."),
            static_result,
        )

        self.assertEqual(len(response.related_links), MAX_RELATED_LINKS)
        self.assertEqual(
            [str(link.url) for link in response.related_links],
            [
                "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
                *(str(link.url) for link in static_links[:3]),
            ],
        )

    async def test_oversized_claimless_handoff_degrades_without_losing_links(self) -> None:
        static_result = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="5" * 32,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer="x" * PUBLIC_ANSWER_MAX_CHARS,
            related_links=[_related_link(0)],
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService([_incident(1)])))

        response = await coordinator.answer(
            QueryRequest(question="Show active wildfires in BC."),
            static_result,
        )

        self.assertTrue(response.live_results)
        self.assertEqual(response.related_links, static_result.related_links)
        self.assertLessEqual(len(response.answer or ""), PUBLIC_ANSWER_MAX_CHARS)
        self.assertNotIn("x" * 100, response.answer or "")
        self.assertTrue(any("handoff was shortened" in item for item in response.limitations))
