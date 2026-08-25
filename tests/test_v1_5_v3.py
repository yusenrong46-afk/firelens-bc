from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

from firelens.agent import AgentTool, FireLensAgent
from firelens.config import FireLensConfig
from firelens.contracts import (
    AskResponse,
    Freshness,
    LiveResult,
    LiveResultKind,
    MapContext,
    QueryRequest,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
)
from firelens.live_answering import LiveAnswerCoordinator
from firelens.live_contracts import bind_distance_derivation
from firelens.live_support import distance_to_geometry_km


class V3ContractTests(unittest.TestCase):
    def test_luna_is_default_and_generation_model_is_configurable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            default = FireLensConfig.from_env(root)
            self.assertEqual(default.generation_model, "openai/gpt-5.6-luna")

            with patch.dict(
                "os.environ",
                {"FIRELENS_GENERATION_MODEL": "openai/gpt-5.6-luna-test"},
            ):
                configured = FireLensConfig.from_env(root)
            self.assertEqual(configured.generation_model, "openai/gpt-5.6-luna-test")

    def test_all_openrouter_stage_models_are_explicitly_configurable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(
                "os.environ",
                {
                    "FIRELENS_EMBEDDING_MODEL": "vendor/embedding",
                    "FIRELENS_RERANK_MODEL": "vendor/reranker",
                    "FIRELENS_GENERATION_MODEL": "vendor/generator",
                },
            ):
                configured = FireLensConfig.from_env(root)

        self.assertEqual(configured.embedding_model, "vendor/embedding")
        self.assertEqual(configured.rerank_model, "vendor/reranker")
        self.assertEqual(configured.generation_model, "vendor/generator")

    def test_query_accepts_bounded_map_context_without_location(self) -> None:
        request = QueryRequest(
            question="What is happening with this fire?",
            context=MapContext(
                selected_live_result_id="incident:7",
                visible_live_result_ids=["incident:7", "perimeter:7"],
            ),
        )

        self.assertIsNone(request.location)
        self.assertEqual(request.context.selected_live_result_id, "incident:7")

    def test_location_request_preserves_the_pending_question(self) -> None:
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="a" * 32,
            response_mode=ResponseMode.REQUIRES_INPUT,
            answer="Share an approximate location or enter a community to calculate distance.",
            required_input=RequiredInput(
                kind=RequiredInputKind.LOCATION,
                prompt="Use approximate location or enter a community.",
                continuation_question="How far is this fire from me?",
            ),
            selected_live_result_id="incident:7",
        )

        self.assertEqual(response.required_input.kind, RequiredInputKind.LOCATION)
        self.assertEqual(response.selected_live_result_id, "incident:7")


class V3DistanceTests(unittest.TestCase):
    def test_point_distance_uses_wgs84_geodesic_distance(self) -> None:
        distance = distance_to_geometry_km(
            {"type": "Point", "coordinates": [-123.0, 50.0]},
            latitude=49.0,
            longitude=-123.0,
        )

        self.assertIsNotNone(distance)
        assert distance is not None
        self.assertGreater(distance, 111.0)
        self.assertLess(distance, 112.0)

    def test_location_inside_perimeter_has_zero_distance(self) -> None:
        distance = distance_to_geometry_km(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-124.0, 49.0],
                        [-123.0, 49.0],
                        [-123.0, 50.0],
                        [-124.0, 50.0],
                        [-124.0, 49.0],
                    ]
                ],
            },
            latitude=49.5,
            longitude=-123.5,
        )

        self.assertEqual(distance, 0.0)

    def test_live_result_can_expose_labelled_distance(self) -> None:
        timestamp = datetime(2026, 8, 13, tzinfo=UTC)
        result = LiveResult(
            result_id="incident:7",
            kind=LiveResultKind.INCIDENT,
            source_url="https://example.test/fire/7",
            source_updated_at=timestamp,
            retrieved_at=timestamp,
            freshness=Freshness.FRESH,
            status="Out of Control",
            name="Test Fire",
            geometry={"type": "Point", "coordinates": [-123.0, 50.0]},
            distance_km=17.4,
            distance_basis="incident_point",
            distance_derivation=bind_distance_derivation(
                result_id="incident:7",
                distance_km=17.4,
                distance_basis="incident_point",
                calculated_at=timestamp,
                extra_input_ids=("place:50.00,-123.00",),
                input_freshness=Freshness.FRESH,
            ),
        )

        self.assertEqual(result.distance_km, 17.4)
        self.assertEqual(result.distance_basis, "incident_point")


class V3AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_agent_dispatches_selected_distance_to_bounded_tool(self) -> None:
        class UnexpectedStaticService:
            async def ask(self, *args, **kwargs):
                raise AssertionError("distance input request must not call the static model")

        request = QueryRequest(
            question="How far is this fire from me?",
            context=MapContext(selected_live_result_id="incident:7"),
        )
        agent = FireLensAgent(
            cast(Any, UnexpectedStaticService()),
            LiveAnswerCoordinator(cast(Any, object())),
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.response.response_mode, ResponseMode.REQUIRES_INPUT)
        self.assertEqual(execution.tools, (AgentTool.GET_OFFICIAL_FIRE,))
