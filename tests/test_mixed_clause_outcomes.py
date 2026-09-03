"""PRODUCT TRUTH: every clause of a mixed question gets an explicit outcome.

"What fires are near Kelowna, and should I evacuate?" is two requests. The
records clause is answered from the official layers; the decision clause is
declined as its own section with the official next step. Nothing is silently
dropped, and a lone personal decision still keeps its whole-turn response.
"""

from __future__ import annotations

import unittest
from typing import Any, cast

from test_luna_brain_agent import (
    FixedLiveService,
    KitStatic,
    SilentStatic,
    _fire,
    _with_distance,
)

from firelens.agent import AgentTool, FireLensAgent
from firelens.agent.query_plan import plan_agent_request
from firelens.answering.clause_boundaries import (
    EVACUATION_DECISION_TEXT,
    PERSONAL_SAFETY_TEXT,
    clause_boundaries,
)
from firelens.answering.intent_automaton import parse_request_intent
from firelens.contracts import (
    AnswerSectionKind,
    LiveResultKind,
    QueryRequest,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
)
from firelens.live_answering import LiveAnswerCoordinator

_KELOWNA_067 = "What fires are near Kelowna, and should I evacuate?"
_VERNON_073 = "Show current fires near Vernon and tell me where to check road closures."
_COUNT_074 = (
    "How many incidents are returned, what changed since yesterday, and what should I pack?"
)


def _fires() -> list[Any]:
    return [
        _with_distance(
            _fire(
                result_id="incident:K51402",
                name="Bald Range",
                status="Out of Control",
                size_hectares=120.0,
                fire_centre="Kamloops Fire Centre",
                incident_number="K51402",
            ),
            12.4,
        ),
        _with_distance(
            _fire(
                result_id="incident:K52001",
                name="McDougall Creek",
                status="Being Held",
                size_hectares=40.0,
                fire_centre="Kamloops Fire Centre",
                incident_number="K52001",
            ),
            30.1,
        ),
    ]


def _agent(static: Any = None) -> FireLensAgent:
    return FireLensAgent(
        cast(Any, static or SilentStatic()),
        LiveAnswerCoordinator(cast(Any, FixedLiveService(_fires()))),
    )


def _kinds(response: Any) -> list[AnswerSectionKind]:
    return [section.kind for section in response.answer_sections]


class ClauseSplittingTests(unittest.TestCase):
    def test_comma_separates_two_requests_but_not_a_preamble(self) -> None:
        self.assertEqual(
            [clause.text for clause in parse_request_intent(_COUNT_074).clauses],
            [
                "How many incidents are returned",
                "what changed since yesterday",
                "what should I pack",
            ],
        )
        wrapped = "Regarding the earlier question 'What official fires are near Kelowna?', How far is the closest one?"
        self.assertEqual(len(parse_request_intent(wrapped).clauses), 1)

    def test_boundaries_need_a_second_clause(self) -> None:
        self.assertEqual(clause_boundaries("Should I evacuate Kelowna?"), ())
        boundaries = clause_boundaries(_KELOWNA_067)
        self.assertEqual([b.kind for b in boundaries], [AnswerSectionKind.SAFETY_BOUNDARY])
        self.assertEqual(boundaries[0].text, EVACUATION_DECISION_TEXT)

    def test_a_located_safety_clause_is_still_a_boundary(self) -> None:
        # The parser files "Am I safe in Kelowna" with the live clauses because it
        # names a place; the decision is still declined, not answered from records.
        boundaries = clause_boundaries("Am I safe in Kelowna and what fires are near?")
        self.assertEqual([b.text for b in boundaries], [PERSONAL_SAFETY_TEXT])

    def test_plan_fetches_evacuation_records_beside_a_declined_evacuation_decision(
        self,
    ) -> None:
        plan = plan_agent_request(QueryRequest(question=_KELOWNA_067))
        self.assertEqual(
            [call.name for call in plan.tool_calls],
            [AgentTool.LIST_OFFICIAL_FIRES, AgentTool.LIST_OFFICIAL_EVACUATIONS],
        )
        self.assertIn(LiveResultKind.EVACUATION, plan.live_layers)
        self.assertEqual([b.kind for b in plan.boundaries], [AnswerSectionKind.SAFETY_BOUNDARY])


class MixedClauseOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_plus_evacuation_decision(self) -> None:
        response = (await _agent().answer(QueryRequest(question=_KELOWNA_067))).response

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertEqual(
            _kinds(response),
            [AnswerSectionKind.CURRENT_RECORDS, AnswerSectionKind.SAFETY_BOUNDARY],
        )
        self.assertEqual(len(response.live_results), 2)
        assert response.answer is not None
        self.assertIn("Bald Range", response.answer)
        self.assertIn(EVACUATION_DECISION_TEXT, response.answer)
        self.assertNotRegex(
            response.answer,
            r"(?i)\byou (?:should|must|need to) (?:not )?(?:evacuate|leave|stay)\b",
        )
        self.assertIn(LiveResultKind.EVACUATION, response.requested_layers)
        self.assertIn("EmergencyInfoBC", {link.title for link in response.related_links})
        self.assertIn("FireLens did not make a personal safety decision.", response.limitations)

    async def test_records_plus_road_status_handoff(self) -> None:
        for question in (
            _VERNON_073,
            "Fires near Kelowna and where do I check the highway status?",
        ):
            with self.subTest(question=question):
                response = (await _agent().answer(QueryRequest(question=question))).response

                self.assertEqual(response.status, ResponseStatus.ANSWER)
                self.assertEqual(
                    _kinds(response),
                    [AnswerSectionKind.CURRENT_RECORDS, AnswerSectionKind.OFFICIAL_HANDOFF],
                )
                self.assertEqual(len(response.live_results), 2)
                self.assertEqual(
                    [str(link.url) for link in response.related_links],
                    ["https://www.drivebc.ca/"],
                )
                assert response.answer is not None
                self.assertNotRegex(
                    response.answer,
                    r"(?i)\b(?:highway|road)s?\b.{0,30}\b(?:is|are) (?:open|closed)\b",
                )

    async def test_count_plus_unavailable_history_plus_reviewed_guidance(self) -> None:
        response = (
            await _agent(KitStatic()).answer(QueryRequest(question=_COUNT_074))
        ).response

        self.assertEqual(response.status, ResponseStatus.ANSWER)
        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertEqual(
            _kinds(response),
            [
                AnswerSectionKind.CURRENT_RECORDS,
                AnswerSectionKind.REVIEWED_GUIDANCE,
                AnswerSectionKind.UNAVAILABLE,
            ],
        )
        assert response.answer is not None
        self.assertIn("2 incident records", response.answer)
        self.assertIn("Include water, medication", response.answer)
        self.assertIn("what changed since yesterday", response.answer)
        self.assertIn("keeps no earlier copies", response.answer)
        self.assertEqual(len(response.claims), 1)

    async def test_a_lone_decision_keeps_the_whole_turn_safety_response(self) -> None:
        for question in (
            "Should I evacuate Kelowna?",
            "Is it safe to stay in Kelowna tonight?",
        ):
            with self.subTest(question=question):
                response = (await _agent().answer(QueryRequest(question=question))).response
                self.assertEqual(response.status, ResponseStatus.ABSTENTION)
                self.assertEqual(response.reason_code, ReasonCode.PERSONALIZED_SAFETY_DECISION)
                self.assertEqual(response.live_results, [])
                self.assertEqual(response.answer_sections, [])

    async def test_the_safety_response_uses_the_words_of_the_question(self) -> None:
        stay = (
            await _agent().answer(
                QueryRequest(question="Is it safe to stay in Kelowna tonight?")
            )
        ).response
        evacuate = (
            await _agent().answer(QueryRequest(question="Should I evacuate Kelowna?"))
        ).response
        assert stay.answer is not None and evacuate.answer is not None
        self.assertTrue(stay.answer.startswith("FireLens cannot judge your personal safety"))
        self.assertTrue(
            evacuate.answer.startswith("FireLens cannot decide whether you should evacuate")
        )
        self.assertNotIn("you are safe", stay.answer)

    async def test_clause_order_does_not_change_the_outcome(self) -> None:
        response = (
            await _agent().answer(
                QueryRequest(question="Am I safe in Kelowna and what fires are near?")
            )
        ).response
        self.assertEqual(
            _kinds(response),
            [AnswerSectionKind.CURRENT_RECORDS, AnswerSectionKind.SAFETY_BOUNDARY],
        )
        self.assertEqual(len(response.live_results), 2)


if __name__ == "__main__":
    unittest.main()
