from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import HttpUrl

from firelens.agent import AgentTool, FireLensAgent
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    DETERMINISTIC_CONFLICT_TEXT,
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


def _incident(*, authority: str = "BC Wildfire Service") -> LiveResult:
    timestamp = datetime(2026, 8, 13, tzinfo=UTC)
    return LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority=authority,
        source_url="https://example.test/FeatureServer/0/7",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name="Mountain Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


class FixedLiveService:
    def __init__(self) -> None:
        self.requested_location = None
        results = [_incident()]
        self.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 13, tzinfo=UTC),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        return self.response

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        return 50.27, -119.27

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        self.requested_location = location
        return cast(
            Any,
            type(
                "Nearby",
                (),
                {
                    "results": self.response.results,
                    "limitations": [],
                    "unavailable_layers": [],
                    "resolved_location": CoarseResolvedLocation(
                        latitude=50.27, longitude=-119.27
                    ),
                },
            )(),
        )


def _accepted_background() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="b" * 32,
        response_mode=ResponseMode.BACKGROUND,
        answer="Pack water, medication, and copies of important documents.",
        claims=[
            PublicClaim(
                claim_id="C1",
                text="Pack water, medication, and copies of important documents.",
                evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            )
        ],
        limitations=[BACKGROUND_LIMITATION],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            policy_valid=True,
        ),
    )


def _accepted_conflict() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="One reviewed source contains a conflicting requirement.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Conflicting requirement")],
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="c" * 32,
        response_mode=ResponseMode.CONFLICT,
        answer=DETERMINISTIC_CONFLICT_TEXT,
        claims=[claim],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Reviewed emergency guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/reviewed-conflict"),
                locator="Section 1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Conflicting requirement",
                context_text="Conflicting requirement in reviewed context.",
            )
        ],
        limitations=["The reviewed sources materially disagree."],
        reason_code=ReasonCode.CONFLICTING_EVIDENCE,
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
    )


class V3CompositionTests(unittest.IsolatedAsyncioTestCase):
    def test_agent_extracts_a_general_clause_from_a_mixed_live_question(self) -> None:
        request = LiveAnswerCoordinator.static_request(
            QueryRequest(
                question=(
                    "Show fires around Kelowna and give me a simple weekend packing list."
                )
            )
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.question, "give me a simple weekend packing list")

    def test_agent_preserves_explanatory_clauses_beside_live_records(self) -> None:
        expected = {
            "Show fires around Kelowna and explain what drives wildfire spread.": (
                "explain what drives wildfire spread"
            ),
            "Show fires around Kelowna and explain what AQHI means.": (
                "explain what AQHI means"
            ),
            "Show fires around Kelowna and explain the weather cycle.": (
                "explain the weather cycle"
            ),
            "Show evacuation information for Williams Lake and explain alert versus order.": (
                "explain alert versus order"
            ),
        }
        for question, fragment in expected.items():
            with self.subTest(question=question):
                request = LiveAnswerCoordinator.static_request(QueryRequest(question=question))
                self.assertIsNotNone(request)
                assert request is not None
                self.assertEqual(request.question, fragment)

    async def test_live_plus_validated_background_keeps_both_halves(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))
        response = await coordinator.answer(
            QueryRequest(
                question=(
                    "Show fires around Kelowna and give me a simple weekend packing list."
                )
            ),
            _accepted_background(),
        )

        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertTrue(response.live_results)
        self.assertEqual(response.claims[0].evidence_status, EvidenceStatus.GENERAL_BACKGROUND)
        self.assertEqual(response.evidence, [])
        self.assertEqual(
            [section.kind for section in response.answer_sections],
            [
                AnswerSectionKind.CURRENT_RECORDS,
                AnswerSectionKind.GENERAL_BACKGROUND,
            ],
        )
        self.assertIn(BACKGROUND_LIMITATION, response.limitations)

    async def test_live_plus_reviewed_conflict_preserves_the_explicit_conflict(self) -> None:
        conflict = _accepted_conflict()
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))

        response = await coordinator.answer(
            QueryRequest(
                question=(
                    "Show fires around Kelowna and explain the difference between an "
                    "evacuation alert and an order."
                )
            ),
            conflict,
        )

        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertEqual(response.reason_code, ReasonCode.CONFLICTING_EVIDENCE)
        self.assertEqual(response.claims, conflict.claims)
        self.assertEqual(response.evidence, conflict.evidence)
        self.assertIn(conflict.answer or "", response.answer or "")
        self.assertIn(
            AnswerSectionKind.CONFLICTING_GUIDANCE,
            [section.kind for section in response.answer_sections],
        )

    async def test_missing_live_records_do_not_erase_a_reviewed_conflict(self) -> None:
        class EmptyLiveService(FixedLiveService):
            def __init__(self) -> None:
                super().__init__()
                self.response = LiveMapResponse(
                    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
                    results=[],
                )

        conflict = _accepted_conflict()
        coordinator = LiveAnswerCoordinator(cast(Any, EmptyLiveService()))
        response = await coordinator.answer(
            QueryRequest(
                question=(
                    "Show fires around Kelowna and explain the difference between an "
                    "evacuation alert and an order."
                )
            ),
            conflict,
        )

        self.assertEqual(response.response_mode, ResponseMode.CONFLICT)
        self.assertEqual(response.reason_code, ReasonCode.CONFLICTING_EVIDENCE)
        self.assertEqual(response.claims, conflict.claims)
        self.assertIn(
            AnswerSectionKind.CONFLICTING_GUIDANCE,
            [section.kind for section in response.answer_sections],
        )

    async def test_empty_live_results_keep_validated_background_half(self) -> None:
        class EmptyLiveService(FixedLiveService):
            def __init__(self) -> None:
                super().__init__()
                self.response = LiveMapResponse(
                    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
                    results=[],
                )

        coordinator = LiveAnswerCoordinator(cast(Any, EmptyLiveService()))
        response = await coordinator.answer(
            QueryRequest(
                question=(
                    "Show fires around Kelowna and give me a simple weekend packing list."
                )
            ),
            _accepted_background(),
        )

        self.assertEqual(response.response_mode, ResponseMode.BACKGROUND)
        self.assertFalse(response.live_results)
        self.assertEqual(response.claims[0].evidence_status, EvidenceStatus.GENERAL_BACKGROUND)
        self.assertEqual(
            [section.kind for section in response.answer_sections],
            [AnswerSectionKind.UNCERTAINTY, AnswerSectionKind.GENERAL_BACKGROUND],
        )
        self.assertIn(BACKGROUND_LIMITATION, response.limitations)

    async def test_selected_record_source_followup_uses_official_record(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))
        request = QueryRequest(
            question="What source reported it?",
            context=MapContext(selected_live_result_id="incident:7"),
        )

        self.assertTrue(coordinator.handles(request))
        response = await coordinator.answer(request, None)

        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertEqual(response.selected_live_result_id, "incident:7")
        self.assertEqual(response.live_results[0].authority, "BC Wildfire Service")
        self.assertIn("BC Wildfire Service", response.answer or "")
        self.assertIn("source", (response.answer or "").casefold())

    async def test_selected_prediction_uses_detail_tool_only_for_a_safe_handoff(self) -> None:
        service = FixedLiveService()

        class UnexpectedStaticService:
            async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
                raise AssertionError("a selected-record boundary must remain deterministic")

        agent = FireLensAgent(
            cast(Any, UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, service)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="When will this fire reach Kelowna?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(execution.tools, (AgentTool.GET_FIRE_DETAILS,))
        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertIn("did not infer", execution.response.limitations[0])

    async def test_live_answer_keeps_related_official_handoff(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))

        response = await coordinator.answer(
            QueryRequest(question="Show fires around Kelowna and the current air quality."),
            None,
        )

        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertTrue(response.live_results)
        self.assertTrue(response.related_links)
        self.assertEqual(
            [section.kind for section in response.answer_sections],
            [AnswerSectionKind.CURRENT_RECORDS, AnswerSectionKind.OFFICIAL_HANDOFF],
        )
        self.assertIn("air quality", (response.answer or "").casefold())

    async def test_empty_live_answer_keeps_related_official_handoff(self) -> None:
        class EmptyLiveService(FixedLiveService):
            def __init__(self) -> None:
                super().__init__()
                self.response = LiveMapResponse(
                    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
                    results=[],
                )

        coordinator = LiveAnswerCoordinator(cast(Any, EmptyLiveService()))
        response = await coordinator.answer(
            QueryRequest(question="Show fires around Kelowna and the current air quality."),
            None,
        )

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertFalse(response.live_results)
        self.assertIsNotNone(response.resolved_location)
        self.assertTrue(response.related_links)
        self.assertIn("air quality", (response.answer or "").casefold())
        self.assertEqual(
            [section.kind for section in response.answer_sections],
            [AnswerSectionKind.UNCERTAINTY, AnswerSectionKind.OFFICIAL_HANDOFF],
        )

    async def test_personalized_safety_boundary_precedes_mixed_live_composition(
        self,
    ) -> None:
        request = QueryRequest(
            question=(
                "Show fires around Kelowna and the current air quality and tell me "
                "whether I should evacuate."
            )
        )
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))

        self.assertFalse(coordinator.handles(request))

    async def test_unsupported_live_handoff_keeps_personalized_safety_refusal(
        self,
    ) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))
        request = QueryRequest(
            question="What is the current air quality in Kelowna and should I evacuate?"
        )

        self.assertTrue(coordinator.handles(request))
        response = await coordinator.answer(request, None)

        self.assertEqual(response.status, ResponseStatus.ABSTENTION)
        self.assertEqual(response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(response.reason_code, "personalized_safety_decision")
        self.assertTrue(response.related_links)
        self.assertIn("cannot provide personalized safety", (response.answer or "").casefold())
        self.assertEqual(
            [section.kind for section in response.answer_sections],
            [AnswerSectionKind.UNCERTAINTY, AnswerSectionKind.OFFICIAL_HANDOFF],
        )

    async def test_place_correction_reuses_previous_live_task(self) -> None:
        service = FixedLiveService()

        class UnexpectedStaticService:
            async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
                raise AssertionError(
                    "a live place correction must not fall through to static RAG"
                )

        agent = FireLensAgent(
            cast(Any, UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, service)),
        )
        request = QueryRequest(
            question="I meant Vernon",
            history=[
                ConversationTurn(role="user", content="Show fires around Kelowna."),
                ConversationTurn(
                    role="assistant",
                    content="Current official information: Mountain Fire.",
                ),
            ],
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.route, QueryRoute.LIVE)
        self.assertEqual(execution.tools, (AgentTool.LIST_ACTIVE_FIRES,))
        self.assertIsNotNone(service.requested_location)
        assert service.requested_location is not None
        self.assertEqual(service.requested_location.label, "Vernon")
        self.assertIsNotNone(execution.response.resolved_location)

    async def test_personal_place_correction_requests_location_permission(self) -> None:
        service = FixedLiveService()

        class UnexpectedStaticService:
            async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
                raise AssertionError("a personal live correction must remain a live task")

        agent = FireLensAgent(
            cast(Any, UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, service)),
        )
        request = QueryRequest(
            question="I meant my place",
            history=[
                ConversationTurn(role="user", content="Show fires around Kelowna."),
                ConversationTurn(
                    role="assistant",
                    content="Current official information: Mountain Fire.",
                ),
            ],
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.route, QueryRoute.LIVE)
        self.assertEqual(execution.response.response_mode, ResponseMode.REQUIRES_INPUT)
        self.assertIsNotNone(execution.response.required_input)
        self.assertIsNone(service.requested_location)

    async def test_nearest_perimeter_continuation_uses_distance_tool(self) -> None:
        service = FixedLiveService()
        results = [
            LiveResult(
                result_id="perimeter:7",
                kind=LiveResultKind.PERIMETER,
                source_url="https://example.test/perimeter/7",
                source_updated_at=datetime(2026, 8, 13, tzinfo=UTC),
                retrieved_at=datetime(2026, 8, 13, tzinfo=UTC),
                freshness=Freshness.FRESH,
                status="Mapped perimeter",
                name="Mountain Fire perimeter",
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-119.52, 49.88],
                            [-119.48, 49.88],
                            [-119.48, 49.92],
                            [-119.52, 49.92],
                            [-119.52, 49.88],
                        ]
                    ],
                },
            )
        ]
        service.response = LiveMapResponse(
            generated_at=datetime(2026, 8, 13, tzinfo=UTC),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

        class UnexpectedStaticService:
            async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
                raise AssertionError("a nearest-perimeter distance task must remain live")

        agent = FireLensAgent(
            cast(Any, UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, service)),
        )
        request = QueryRequest.model_validate(
            {
                "question": "How close is the nearest perimeter to my home?",
                "location": {"label": "Kelowna"},
            }
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.tools, (AgentTool.LIST_OFFICIAL_FIRES,))
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Mountain Fire perimeter", execution.response.answer or "")
        self.assertEqual(
            execution.response.live_results[0].kind,
            LiveResultKind.PERIMETER,
        )

    async def test_topic_pivot_is_not_treated_as_a_place_correction(self) -> None:
        service = FixedLiveService()

        class RecordingStaticService:
            def __init__(self) -> None:
                self.questions: list[str] = []

            async def ask(
                self, request: QueryRequest, *args: Any, **kwargs: Any
            ) -> AskResponse:
                self.questions.append(request.question)
                return _accepted_background()

        static_service = RecordingStaticService()
        agent = FireLensAgent(
            cast(Any, static_service),
            LiveAnswerCoordinator(cast(Any, service)),
        )
        history = [
            ConversationTurn(role="user", content="Show evacuation orders around Kelowna."),
            ConversationTurn(
                role="assistant",
                content="Current official evacuation information was shown for Kelowna.",
            ),
        ]

        for question in (
            "Actually what should I pack?",
            "I meant how to prepare my pets.",
        ):
            with self.subTest(question=question):
                execution = await agent.answer(QueryRequest(question=question, history=history))
                self.assertEqual(execution.response.response_mode, ResponseMode.BACKGROUND)
                self.assertEqual(static_service.questions[-1], question)

        self.assertIsNone(service.requested_location)
