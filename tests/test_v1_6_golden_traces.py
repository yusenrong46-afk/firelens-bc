"""Offline replay of the five V1.6 golden traces. No paid models."""

from __future__ import annotations

import unittest
from typing import Any, cast

from test_luna_brain_agent import (
    CapturingProvider,
    CountingMapService,
    CountingStatic,
    KitStatic,
    SilentStatic,
    _agent,
    _fire,
)

from firelens.agent import AgentTool, FireLensAgent
from firelens.contracts import MapContext, QueryRequest, QueryRoute, ResponseMode
from firelens.evaluation.golden_traces import (
    GOLDEN_TRACE_QUESTIONS,
    record_golden_trace,
)
from firelens.live_answering import LiveAnswerCoordinator


class GoldenTraceTests(unittest.IsolatedAsyncioTestCase):
    def test_frozen_question_wording(self) -> None:
        self.assertEqual(
            GOLDEN_TRACE_QUESTIONS,
            (
                "What belongs in a grab-and-go bag?",
                "What official fires are near Kelowna?",
                "How far is this selected fire from Kelowna?",
                "Should I evacuate right now?",
                "Who won the Stanley Cup?",
            ),
        )

    async def test_grab_and_go_skips_outer_write(self) -> None:
        question = GOLDEN_TRACE_QUESTIONS[0]
        agent = _agent([], static=KitStatic())
        execution = await agent.answer(QueryRequest(question=question))
        trace = record_golden_trace(
            case_id="grab_and_go", question=question, execution=execution
        )

        self.assertEqual(trace.route, QueryRoute.RELATED.value)
        self.assertEqual(trace.policy_route, "pure_static_accepted")
        self.assertEqual(trace.input_rail, "none")
        self.assertEqual(trace.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE.value,))
        self.assertEqual(trace.provider_stages, ("grounded_generation",))
        self.assertEqual(trace.retrieval_cycles, 1)
        self.assertEqual(trace.outer_chat_turns, 0)
        self.assertLessEqual(trace.grounded_generations, 1)
        self.assertEqual(trace.evidence_lane, "reviewed")
        self.assertTrue(trace.validation_accepted)
        self.assertEqual(trace.response_mode, ResponseMode.GROUNDED.value)
        self.assertIsNone(trace.fallback_reason)
        self.assertEqual(execution.response.answer, execution.response.claims[0].text)

    async def test_kelowna_fires_use_official_records_not_static_rag(self) -> None:
        question = GOLDEN_TRACE_QUESTIONS[1]
        live = CountingMapService([_fire(result_id="incident:7", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(QueryRequest(question=question))
        trace = record_golden_trace(
            case_id="kelowna_fires", question=question, execution=execution
        )

        self.assertEqual(trace.route, QueryRoute.LIVE.value)
        self.assertEqual(trace.policy_route, "ready_live")
        self.assertEqual(trace.input_rail, "none")
        self.assertEqual(trace.tools, (AgentTool.LIST_OFFICIAL_FIRES.value,))
        self.assertEqual(trace.provider_stages, ())
        self.assertEqual(trace.retrieval_cycles, 0)
        self.assertEqual(trace.outer_chat_turns, 0)
        self.assertEqual(trace.grounded_generations, 0)
        self.assertEqual(trace.evidence_lane, "live")
        self.assertIsNone(trace.validation_accepted)
        self.assertEqual(trace.response_mode, ResponseMode.LIVE.value)
        self.assertIn("Ridge Fire", execution.response.answer or "")
        self.assertGreater(live.nearby_calls + live.map_calls, 0)

    async def test_selected_fire_distance_uses_packet_kilometres(self) -> None:
        question = GOLDEN_TRACE_QUESTIONS[2]
        live = CountingMapService([_fire(result_id="incident:7", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question=question,
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )
        trace = record_golden_trace(
            case_id="selected_distance", question=question, execution=execution
        )

        self.assertEqual(trace.route, QueryRoute.LIVE.value)
        self.assertEqual(trace.input_rail, "none")
        self.assertEqual(trace.tools, (AgentTool.GET_OFFICIAL_FIRE.value,))
        self.assertEqual(trace.retrieval_cycles, 0)
        self.assertEqual(trace.outer_chat_turns, 0)
        self.assertEqual(trace.evidence_lane, "live")
        self.assertEqual(trace.response_mode, ResponseMode.LIVE.value)
        answer = execution.response.answer or ""
        self.assertIn("Ridge Fire", answer)
        self.assertRegex(answer, r"\d+(?:\.\d+)? km")
        self.assertIn("not driving distance", answer.casefold())
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")

    async def test_evacuate_now_is_blocked_before_tools_or_models(self) -> None:
        question = GOLDEN_TRACE_QUESTIONS[3]
        provider = CapturingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            LiveAnswerCoordinator(cast(Any, CountingMapService([]))),
        )
        execution = await agent.answer(QueryRequest(question=question))
        trace = record_golden_trace(
            case_id="evacuate_now", question=question, execution=execution
        )

        self.assertEqual(trace.route, QueryRoute.PROHIBITED.value)
        self.assertEqual(trace.policy_route, "prohibited")
        self.assertEqual(trace.input_rail, "input_seatbelt")
        self.assertEqual(trace.tools, ())
        self.assertEqual(trace.provider_stages, ())
        self.assertEqual(trace.retrieval_cycles, 0)
        self.assertEqual(trace.outer_chat_turns, 0)
        self.assertEqual(trace.grounded_generations, 0)
        self.assertEqual(trace.evidence_lane, "none")
        self.assertEqual(trace.response_mode, ResponseMode.ABSTENTION.value)
        self.assertIn("personalized_safety_decision", trace.refused_inferences)
        self.assertEqual(provider.calls, 0)
        self.assertIn("cannot provide", (execution.response.answer or "").casefold())

    async def test_stanley_cup_is_a_scope_redirect(self) -> None:
        question = GOLDEN_TRACE_QUESTIONS[4]
        agent = _agent([], static=SilentStatic())
        execution = await agent.answer(QueryRequest(question=question))
        trace = record_golden_trace(
            case_id="stanley_cup", question=question, execution=execution
        )

        self.assertEqual(trace.route, QueryRoute.RELATED.value)
        self.assertEqual(trace.input_rail, "none")
        self.assertEqual(trace.tools, ())
        self.assertEqual(trace.provider_stages, ())
        self.assertEqual(trace.retrieval_cycles, 0)
        self.assertEqual(trace.outer_chat_turns, 0)
        self.assertEqual(trace.evidence_lane, "none")
        self.assertEqual(trace.response_mode, ResponseMode.SCOPE_REDIRECT.value)
        self.assertIn("scope_redirect", trace.refused_inferences)
        self.assertNotRegex(
            (execution.response.answer or "").casefold(),
            r"stanley cup|montreal|edmonton|champion",
        )
