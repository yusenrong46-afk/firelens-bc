"""Zero-cost ordinary-user exploratory matrix for V1.5 V3.

This is not the frozen 162-case catalog. It records behaviour classes only.
"""

from __future__ import annotations

import json
import re
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import HttpUrl

from firelens.agent import AgentTool, FireLensAgent
from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    BACKGROUND_LIMITATION,
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
)
from firelens.evaluation.product_question_cases import build_product_question_cases
from firelens.evaluation.v3_exploratory_roster import (
    ExploratoryCase,
    build_v3_exploratory_roster,
    roster_counts,
)
from firelens.live import LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "output/v1_5_v3_exploratory/sanitized_roster_report.json"
_SAFE_LANGUAGE = re.compile(
    r"\b(?:everything|the area|it)\s+is\s+safe\b|\ball clear\b|"
    r"\bnothing\s+to\s+worry\b",
    re.IGNORECASE,
)


def _request(case: ExploratoryCase) -> QueryRequest:
    history = [ConversationTurn(role=role, content=content) for role, content in case.history]
    context = MapContext(selected_live_result_id=case.selected_result_id)
    return QueryRequest(question=case.question, history=history, context=context)


def _incident() -> LiveResult:
    timestamp = datetime(2026, 8, 15, tzinfo=UTC)
    return LiveResult(
        result_id="incident:7",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url="https://example.test/FeatureServer/0/7",
        source_updated_at=timestamp,
        retrieved_at=timestamp,
        freshness=Freshness.FRESH,
        status="Being Held",
        name="Mountain Fire",
        geometry={"type": "Point", "coordinates": [-119.5, 49.9]},
    )


class FixedLiveService:
    def __init__(self, *, empty: bool = False, fail: bool = False) -> None:
        self.fail = fail
        timestamp = datetime(2026, 8, 15, tzinfo=UTC)
        self.response = LiveMapResponse(
            generated_at=timestamp,
            results=[] if empty else [_incident()],
        )
        self.requested_location = None

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        if self.fail:
            raise LiveDataUnavailable("official live source unavailable")
        return self.response

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        if self.fail:
            raise LiveDataUnavailable("official live source unavailable")
        return 49.89, -119.49

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        if self.fail:
            raise LiveDataUnavailable("official live source unavailable")
        self.requested_location = location
        return type(
            "Nearby",
            (),
            {
                "results": self.response.results,
                "limitations": list(self.response.limitations),
                "unavailable_layers": list(self.response.unavailable_layers),
                "resolved_location": CoarseResolvedLocation(latitude=49.89, longitude=-119.49),
            },
        )()


def _background() -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="b" * 32,
        response_mode=ResponseMode.BACKGROUND,
        answer="Pack water and copies of important documents.",
        claims=[
            PublicClaim(
                claim_id="C1",
                text="Pack water and copies of important documents.",
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


def _grounded() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Include water, food, and copies of documents in a grab-and-go bag.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Include water, food, and copies")],
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
                title="PreparedBC guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/preparedbc"),
                locator="Section 1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Include water, food, and copies",
                context_text="Include water, food, and copies of documents.",
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


class V3ExploratoryRosterTests(unittest.TestCase):
    def test_roster_meets_breadth_and_does_not_touch_frozen_catalog(self) -> None:
        cases = build_v3_exploratory_roster()
        counts = roster_counts(cases)
        self.assertGreaterEqual(counts["single"], 250)
        self.assertGreaterEqual(counts["multi"], 60)
        self.assertEqual(counts["unique_ids"], counts["total"])
        self.assertEqual(counts["unique_questions"], counts["total"])
        frozen = build_product_question_cases()
        self.assertEqual(len(frozen), 162)
        self.assertTrue(all(case.id.startswith("EX-") for case in cases))
        buckets = {case.bucket for case in cases}
        for required in (
            "named_place_live",
            "named_place_evacuation",
            "province_live",
            "personal_location",
            "selected_followup",
            "mixed_reviewed",
            "mixed_background",
            "mixed_unsupported",
            "unsupported_current",
            "personalized_safety",
            "personalized_medical",
            "policy_manipulation",
            "place_correction",
            "topic_pivot",
            "deictic_safety",
            "location_recovery",
        ):
            self.assertIn(required, buckets)

    def test_product_invariants_hold_for_every_roster_case(self) -> None:
        rows: list[dict[str, object]] = []
        failures: list[str] = []
        for case in build_v3_exploratory_roster():
            request = _request(case)
            plan = plan_query(request)
            location = coarse_location_from_question(case.question)
            layers = live_layers_for_question(case.question)
            topics = unsupported_live_topics(case.question)
            personal = live_query_requires_location(case.question)
            selected = is_selected_live_request(request)
            unsupported_selected = is_unsupported_selected_request(request)
            distance = is_distance_request(request)
            fragment = static_guidance_fragment(case.question)
            row = {
                "id": case.id,
                "bucket": case.bucket,
                "turn_kind": case.turn_kind,
                "route": plan.route.value,
                "reason_code": plan.boundary_reason.value if plan.boundary_reason else None,
                "location_class": "required"
                if personal
                else "inferred"
                if location is not None
                else "none",
                "location_label_present": location.label is not None if location else False,
                "layers": [kind.value for kind in layers],
                "unsupported_topics": list(topics),
                "selected": selected,
                "unsupported_selected": unsupported_selected,
                "distance": distance,
                "mixed_static_fragment": bool(fragment),
                "tool_hint": (
                    "get_official_fire"
                    if selected or unsupported_selected
                    else "list_official_fires"
                    if distance
                    or LiveResultKind.INCIDENT in layers
                    or LiveResultKind.PERIMETER in layers
                    else "list_official_evacuations"
                    if LiveResultKind.EVACUATION in layers
                    else None
                ),
            }
            rows.append(row)
            if case.safety_class == "safety" and (
                plan.route != QueryRoute.PROHIBITED
                or plan.boundary_reason != ReasonCode.PERSONALIZED_SAFETY_DECISION
            ):
                failures.append(f"{case.id}: safety did not prohibit")
            if case.safety_class == "medical" and (
                plan.route != QueryRoute.PROHIBITED
                or plan.boundary_reason != ReasonCode.PERSONALIZED_MEDICAL_ADVICE
            ):
                failures.append(f"{case.id}: medical did not prohibit")
            if case.safety_class == "manipulation" and (
                plan.route != QueryRoute.PROHIBITED
                or plan.boundary_reason != ReasonCode.POLICY_MANIPULATION
            ):
                failures.append(f"{case.id}: manipulation did not prohibit")
            if case.bucket == "personal_location":
                if location is not None:
                    failures.append(f"{case.id}: personal location became a named label")
                if not personal:
                    failures.append(f"{case.id}: personal live ask did not require location")
                if plan.route != QueryRoute.LIVE:
                    failures.append(f"{case.id}: personal live ask was not live")
            if case.bucket == "named_place_live":
                if location is None:
                    failures.append(f"{case.id}: named place was not inferred")
                if plan.route != QueryRoute.LIVE:
                    failures.append(f"{case.id}: named place was not live")
                if plan.route == QueryRoute.CAPABILITY:
                    failures.append(f"{case.id}: named place fell through to capability")
            if case.bucket == "province_live" and location is not None:
                failures.append(f"{case.id}: province-wide invented a place")
            if case.bucket == "reviewed_or_background":
                if location is not None:
                    failures.append(f"{case.id}: guidance question invented a place")
                if plan.route == QueryRoute.PROHIBITED:
                    failures.append(f"{case.id}: ordinary guidance was prohibited")
            if case.bucket == "mixed_reviewed" and fragment is None:
                failures.append(f"{case.id}: mixed reviewed lost the static clause")
            if case.bucket == "mixed_unsupported" and not topics:
                failures.append(f"{case.id}: mixed unsupported lost the handoff topic")
            if (
                case.selected_class == "unsupported"
                and case.selected_result_id
                and not (unsupported_selected or plan.route == QueryRoute.PROHIBITED)
            ):
                failures.append(f"{case.id}: selected prediction was not bounded")
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "dataset": "v1_5_v3_exploratory_roster.v1",
                    "counts": roster_counts(),
                    "failure_count": len(failures),
                    "rows": rows,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(failures, [])


class V3ExploratoryCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_live_result_is_not_described_as_safe(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(empty=True)))
        response = await coordinator.answer(
            QueryRequest(question="Where are the current wildfires in Kelowna?"),
            None,
        )
        text = " ".join([response.answer or "", *response.limitations]).casefold()
        self.assertFalse(
            _SAFE_LANGUAGE.search(text.replace("does not mean the area is safe", ""))
        )
        self.assertIn("does not mean", text)
        self.assertEqual(response.response_mode, ResponseMode.LIVE)
        self.assertFalse(response.live_results)
        self.assertIsNotNone(response.resolved_location)

    async def test_provider_failure_is_unavailable_not_all_clear(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService(fail=True)))
        response = await coordinator.answer(
            QueryRequest(question="Show the current BC wildfire map."),
            None,
        )
        text = " ".join([response.answer or "", *response.limitations]).casefold()
        self.assertIn("unavailable", text)
        self.assertNotIn("all clear", text)
        self.assertTrue(response.unavailable_layers)

    async def test_mixed_reviewed_keeps_both_halves(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))
        response = await coordinator.answer(
            QueryRequest(
                question="Are there fires near Kelowna today, and what belongs in an emergency kit?"
            ),
            _grounded(),
        )
        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertTrue(response.live_results)
        self.assertTrue(response.claims)
        self.assertTrue(response.evidence)
        self.assertIn(
            AnswerSectionKind.CURRENT_RECORDS, [s.kind for s in response.answer_sections]
        )
        self.assertIn(
            AnswerSectionKind.REVIEWED_GUIDANCE, [s.kind for s in response.answer_sections]
        )

    async def test_mixed_background_keeps_both_halves(self) -> None:
        coordinator = LiveAnswerCoordinator(cast(Any, FixedLiveService()))
        response = await coordinator.answer(
            QueryRequest(
                question="Show fires around Kelowna and give me a simple weekend packing list."
            ),
            _background(),
        )
        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertTrue(response.live_results)
        self.assertEqual(response.claims[0].evidence_status, EvidenceStatus.GENERAL_BACKGROUND)

    async def test_unmatched_selected_distance_does_not_substitute(self) -> None:
        class UnexpectedStatic:
            async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
                raise AssertionError("unmatched selected distance must not call static RAG")

        agent = FireLensAgent(
            cast(Any, UnexpectedStatic()),
            LiveAnswerCoordinator(cast(Any, FixedLiveService())),
        )
        response = (
            await agent.answer(
                QueryRequest(
                    question="How far is this fire from Kelowna?",
                    context=MapContext(selected_live_result_id="incident:missing"),
                )
            )
        ).response
        self.assertTrue(
            any("did not substitute" in item.casefold() for item in response.limitations)
        )
        if response.live_results:
            self.assertNotEqual(response.live_results[0].result_id, "incident:7")

    async def test_place_correction_and_topic_pivot_do_not_cross_wire(self) -> None:
        service = FixedLiveService()

        class RecordingStatic:
            def __init__(self) -> None:
                self.questions: list[str] = []

            async def ask(
                self, request: QueryRequest, *args: Any, **kwargs: Any
            ) -> AskResponse:
                self.questions.append(request.question)
                return _background()

        static = RecordingStatic()
        agent = FireLensAgent(cast(Any, static), LiveAnswerCoordinator(cast(Any, service)))
        history = [
            ConversationTurn(role="user", content="Show fires around Kelowna."),
            ConversationTurn(
                role="assistant", content="Current official information was shown for Kelowna."
            ),
        ]
        live = await agent.answer(QueryRequest(question="I meant Vernon", history=history))
        self.assertEqual(live.route, QueryRoute.LIVE)
        self.assertEqual(getattr(service.requested_location, "label", None), "Vernon")
        pivot = await agent.answer(
            QueryRequest(question="Actually what should I pack?", history=history)
        )
        self.assertEqual(pivot.response.response_mode, ResponseMode.BACKGROUND)
        self.assertEqual(static.questions[-1], "Actually what should I pack?")

    async def test_agent_tools_stay_inside_the_fixed_vocabulary(self) -> None:
        allowed = set(AgentTool)
        service = FixedLiveService()

        class Static:
            async def ask(
                self, request: QueryRequest, *args: Any, **kwargs: Any
            ) -> AskResponse:
                return _grounded()

        agent = FireLensAgent(cast(Any, Static()), LiveAnswerCoordinator(cast(Any, service)))
        for question in (
            "Where are the current wildfires in Kelowna?",
            "What belongs in a wildfire grab-and-go bag?",
            "How far is this fire from Kelowna?",
        ):
            context = MapContext(selected_live_result_id="incident:7")
            execution = await agent.answer(QueryRequest(question=question, context=context))
            self.assertTrue(set(execution.tools) <= allowed)


if __name__ == "__main__":
    unittest.main()
