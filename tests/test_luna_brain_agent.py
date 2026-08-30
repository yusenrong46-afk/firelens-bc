"""Characterization for the thin-app Luna brain. Not frozen benchmark labels."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import HttpUrl

from firelens.agent import AgentTool, FireLensAgent
from firelens.agent.chat import ChatToolCall, ChatTurn
from firelens.agent.compose import compose_response
from firelens.agent.loop_support import pure_static_ready
from firelens.agent.packet import AgentPacket, live_record_fact
from firelens.agent.rails import output_rail_errors
from firelens.agent.runtime_tools import execute_tool
from firelens.answering.live_analysis import (
    compose_official_answer,
    filter_requested_named_fire_results,
)
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    AskResponse,
    ClaimSupport,
    CoarseResolvedLocation,
    ConversationTurn,
    EvidenceStatus,
    Freshness,
    GeometryRelation,
    LiveMapResponse,
    LiveResult,
    LiveResultKind,
    LocationInput,
    MapContext,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
    aggregate_live_freshness,
)
from firelens.live import LiveDataErrorKind, LiveDataUnavailable
from firelens.live_answering import LiveAnswerCoordinator
from firelens.live_contracts import bind_distance_derivation
from firelens.publication.compiler import compile_structured_claim
from firelens.publication.fallback import background_authority, explanation_authority


def _timestamp() -> datetime:
    return datetime(2026, 8, 15, tzinfo=UTC)


def _fire(
    *,
    result_id: str,
    name: str | None = None,
    status: str = "Being Held",
    size_hectares: float | None = None,
    fire_centre: str | None = None,
    incident_number: str | None = None,
    kind: LiveResultKind = LiveResultKind.INCIDENT,
    longitude: float = -119.5,
    latitude: float = 49.9,
    geometry: dict[str, object] | None = None,
    geometry_relation: GeometryRelation = GeometryRelation.UNKNOWN,
    freshness: Freshness = Freshness.FRESH,
    issuer: str | None = None,
) -> LiveResult:
    stamp = _timestamp()
    return LiveResult(
        result_id=result_id,
        kind=kind,
        source_url=f"https://example.test/live/{result_id}",
        source_updated_at=stamp,
        retrieved_at=stamp,
        freshness=freshness,
        status=status,
        name=name,
        incident_number=incident_number,
        size_hectares=size_hectares,
        fire_centre=fire_centre,
        issuer=issuer,
        geometry_relation=geometry_relation,
        geometry=geometry
        or (
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [longitude - 0.02, latitude - 0.02],
                        [longitude + 0.02, latitude - 0.02],
                        [longitude + 0.02, latitude + 0.02],
                        [longitude - 0.02, latitude + 0.02],
                        [longitude - 0.02, latitude - 0.02],
                    ]
                ],
            }
            if kind == LiveResultKind.PERIMETER
            else {"type": "Point", "coordinates": [longitude, latitude]}
        ),
    )


def _with_distance(
    result: LiveResult,
    distance_km: float,
    *,
    basis: str = "incident_point",
) -> LiveResult:
    return result.model_copy(
        update={
            "distance_km": distance_km,
            "distance_basis": basis,
            "distance_derivation": bind_distance_derivation(
                result_id=result.result_id,
                distance_km=distance_km,
                distance_basis=basis,  # type: ignore[arg-type]
                calculated_at=result.retrieved_at,
                extra_input_ids=("place:49.90,-119.50",),
                input_freshness=result.freshness,
            ),
        }
    )


class FixedLiveService:
    def __init__(
        self,
        results: list[LiveResult],
        *,
        map_results: list[LiveResult] | None = None,
        nearby_results: list[LiveResult] | None = None,
        roster_total: int | None = None,
    ) -> None:
        self.results = results
        self._map_results = map_results
        self._nearby_results = nearby_results
        self._roster_total = roster_total
        self.requested_location = None

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        results = self._map_results if self._map_results is not None else self.results
        return LiveMapResponse(
            generated_at=_timestamp(),
            results=results,
            aggregate_freshness=aggregate_live_freshness(results),
        )

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        return 49.88, -119.49

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        self.requested_location = location
        page_results = (
            self._nearby_results if self._nearby_results is not None else self.results
        )
        total = self._roster_total if self._roster_total is not None else len(page_results)
        return type(
            "Nearby",
            (),
            {
                "results": page_results,
                "limitations": [],
                "unavailable_layers": [],
                "resolved_location": CoarseResolvedLocation(latitude=49.88, longitude=-119.49),
                "pagination": type("Pagination", (), {"total_results": total})(),
            },
        )()


class SilentStatic:
    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("this live characterization must not call static RAG")


def _kit_response(*, mode: ResponseMode) -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Include water, medication, and copies of important documents.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[
            ClaimSupport(
                evidence_id="E1",
                quote="Include water, medication, and copies of important documents.",
            )
        ],
        publication=explanation_authority(),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="k" * 32,
        response_mode=mode,
        answer="Include water, medication, and copies of important documents.",
        claims=[claim] if mode == ResponseMode.GROUNDED else [],
        evidence=[
            PublicEvidence(
                evidence_id="E1",
                title="Reviewed emergency kit guide",
                publisher="Government of British Columbia",
                canonical_url=HttpUrl("https://example.test/kit"),
                locator="Section 1",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                primary_text="Include water, medication, and copies of important documents.",
                context_text="Include water, medication, and copies of important documents.",
            )
        ]
        if mode == ResponseMode.GROUNDED
        else [],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        )
        if mode == ResponseMode.GROUNDED
        else None,
        limitations=(
            []
            if mode == ResponseMode.GROUNDED
            else ["General background — not verified against the FireLens corpus."]
        ),
    )


class KitStatic:
    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del request, args, kwargs
        return _kit_response(mode=ResponseMode.GROUNDED)


class ApprovedReturnStatic:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del args
        self.calls.append((request.question, dict(kwargs)))
        compiled = compile_structured_claim(
            typed_claim_id="TC-EVAC-003-01",
            public_claim_id="C1",
        )
        assert compiled.response is not None
        return compiled.response


class AdjacentKitStatic:
    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del request, args
        if kwargs.get("prefer_reviewed_quotes"):
            return _kit_response(mode=ResponseMode.GROUNDED)
        return _kit_response(mode=ResponseMode.BACKGROUND)


class RecordingStatic:
    def __init__(self, response: AskResponse) -> None:
        self.response = response
        self.calls: list[tuple[QueryRequest, dict[str, Any]]] = []

    async def ask(self, request: QueryRequest, *args: Any, **kwargs: Any) -> AskResponse:
        del args
        self.calls.append((request, dict(kwargs)))
        return self.response


def _background_response() -> AskResponse:
    claim = PublicClaim(
        claim_id="C1",
        text="Dragons appear in stories and folklore from many cultures.",
        evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
        publication=background_authority(),
    )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id="b" * 32,
        response_mode=ResponseMode.BACKGROUND,
        answer=claim.text,
        claims=[claim],
        limitations=[BACKGROUND_LIMITATION],
        validation=ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        ),
    )


def _agent(results: list[LiveResult], static: Any = None) -> FireLensAgent:
    return FireLensAgent(
        cast(Any, SilentStatic() if static is None else static),
        LiveAnswerCoordinator(cast(Any, FixedLiveService(results))),
    )


class InventingThenRewritingProvider:
    def __init__(self) -> None:
        self.turns = 0
        self.rewrites = 0

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        self.turns += 1
        joined = " ".join(str(message.get("content")) for message in messages)
        if "previous_answer_rejected_for" in joined:
            self.rewrites += 1
            return ChatTurn(content="Mountain Fire is Being Held in the official records.")
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_1",
                        name="list_official_fires",
                        arguments={"place_label": "Kelowna"},
                    ),
                ),
            )
        return ChatTurn(
            content=("You should evacuate now. Phantom Ridge Fire is at 123 Main Street.")
        )


class ProvinceLabelProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_bc",
                        name="list_official_fires",
                        arguments={"place_label": "British Columbia"},
                    ),
                ),
            )
        return ChatTurn(content="Official records list active wildfires.")


class LeaveNowDefinitionProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_def",
                        name="search_reviewed_guidance",
                        arguments={
                            "query": (
                                "What is the difference between an evacuation "
                                "alert and an order?"
                            )
                        },
                    ),
                ),
            )
        return ChatTurn(content="You should evacuate now from Kelowna.")


class CoordinateDumpProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(content="The perimeter point is 49.589303, -119.906732.")


class WriteOnlyProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(content="There are wildfires in British Columbia.")


class CapturingProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] | None = None
        self.calls = 0
        self.tools_seen: list[list[dict[str, Any]] | None] = []

    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if self.messages is None:
            self.messages = list(messages)
        self.calls += 1
        self.tools_seen.append(tools)
        return ChatTurn(content="Ridge Fire is Being Held.")


class ChattyOffScopeProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        del messages, tools
        return ChatTurn(
            content=(
                "Dragons are fascinating! In BC folklore they are said to guard "
                "mountain lakes and start legendary blazes."
            )
        )


class GetThenWriteProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_get",
                        name="get_official_fire",
                        arguments={"result_id": "incident:7"},
                    ),
                ),
            )
        return ChatTurn(content="Mountain Fire is Being Held.")


class ListKelownaProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_list",
                        name="list_official_fires",
                        arguments={"place_label": "Kelowna"},
                    ),
                ),
            )
        return ChatTurn(content="Other Fire is Being Held.")


class EvacProvinceProvider:
    async def chat_turn(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurn:
        if tools and not any(message.get("role") == "tool" for message in messages):
            return ChatTurn(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        id="call_evac",
                        name="list_official_evacuations",
                        arguments={"place_label": "British Columbia"},
                    ),
                ),
            )
        return ChatTurn(content="No fetched official fire-related evacuation.")


class CountingMapService(FixedLiveService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.map_calls = 0
        self.nearby_calls = 0
        self.resolve_calls = 0
        self.map_layer_requests: list[tuple[LiveResultKind, ...] | None] = []

    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        self.map_calls += 1
        self.map_layer_requests.append(kwargs.get("layers"))
        return await super().map_results(*args, **kwargs)

    async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
        self.nearby_calls += 1
        return await super().nearby_page(location, *args, **kwargs)

    async def resolve_location(self, location: Any) -> tuple[float, float]:
        self.resolve_calls += 1
        return await super().resolve_location(location)


class UnavailableLiveService:
    async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
        del args, kwargs
        raise LiveDataUnavailable("incident source is unavailable")

    async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise LiveDataUnavailable("incident source is unavailable")

    async def resolve_location(self, _location: Any) -> tuple[float, float]:
        raise LiveDataUnavailable("geocode unavailable")


class _ProviderStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("province-wide characterization must not call static RAG")


class _DefinitionStatic:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        del args, kwargs
        text = (
            "An evacuation alert means prepare to leave; an evacuation order "
            "means leave when officials issue it."
        )
        claim = PublicClaim(
            claim_id="C1",
            text=text,
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[
                ClaimSupport(
                    evidence_id="E1",
                    quote=text,
                )
            ],
            publication=explanation_authority(),
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id="d" * 32,
            response_mode=ResponseMode.GROUNDED,
            answer=text,
            claims=[claim],
            evidence=[
                PublicEvidence(
                    evidence_id="E1",
                    title="Reviewed evacuation definitions",
                    publisher="Government of British Columbia",
                    canonical_url=HttpUrl("https://example.test/evac"),
                    locator="Section 1",
                    temporal_class=TemporalClass.STABLE_GUIDANCE,
                    primary_text=(
                        "An evacuation alert means prepare to leave; an evacuation "
                        "order means leave when officials issue it."
                    ),
                    context_text=(
                        "An evacuation alert means prepare to leave; an evacuation "
                        "order means leave when officials issue it."
                    ),
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


class CountingStatic:
    def __init__(self, provider: InventingThenRewritingProvider) -> None:
        self.provider = provider

    async def ask(self, *args: Any, **kwargs: Any) -> AskResponse:
        raise AssertionError("veto-rewrite characterization must not call static RAG")


class LunaBrainCharacterizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_place_cannot_replace_the_user_bound_place(self) -> None:
        class ReplacingProvider:
            async def chat_turn(
                self,
                messages: list[dict[str, Any]],
                *,
                tools: list[dict[str, Any]] | None = None,
            ) -> ChatTurn:
                if tools and not any(row.get("role") == "tool" for row in messages):
                    return ChatTurn(
                        content=None,
                        tool_calls=(
                            ChatToolCall(
                                id="replace-place",
                                name="list_official_fires",
                                arguments={"place_label": "Prince George"},
                            ),
                        ),
                    )
                return ChatTurn(content="Prince George Ridge Fire is listed.")

        class PlaceAwareService(FixedLiveService):
            def __init__(self) -> None:
                super().__init__(
                    [_fire(result_id="incident:pg", name="Prince George Ridge Fire")]
                )
                self.requested_labels: list[str | None] = []

            async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
                label = getattr(location, "label", None)
                self.requested_labels.append(label)
                rows = self.results if str(label).casefold() == "prince george" else []
                return type(
                    "Nearby",
                    (),
                    {
                        "results": rows,
                        "limitations": [],
                        "unavailable_layers": [],
                        "resolved_location": CoarseResolvedLocation(
                            latitude=49.88, longitude=-119.49
                        ),
                        "pagination": type("Pagination", (), {"total_results": len(rows)})(),
                    },
                )()

        live = PlaceAwareService()
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ReplacingProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires near Kelowna currently?")
        )

        self.assertNotIn("Prince George", live.requested_labels)
        self.assertNotIn(
            "Prince George Ridge Fire",
            [row.name for row in execution.response.live_results],
        )

    async def test_one_turn_tool_fanout_cannot_escape_the_request_plan(self) -> None:
        class FanoutProvider:
            async def chat_turn(
                self,
                messages: list[dict[str, Any]],
                *,
                tools: list[dict[str, Any]] | None = None,
            ) -> ChatTurn:
                if tools and not any(row.get("role") == "tool" for row in messages):
                    labels = (
                        "Vancouver",
                        "Victoria",
                        "Kelowna",
                        "Kamloops",
                        "Nanaimo",
                        "Surrey",
                        "Burnaby",
                        "Richmond",
                        "Abbotsford",
                        "Prince George",
                    )
                    return ChatTurn(
                        content=None,
                        tool_calls=tuple(
                            ChatToolCall(
                                id=f"fanout-{index}",
                                name="list_official_fires",
                                arguments={"place_label": label},
                            )
                            for index, label in enumerate(labels, start=1)
                        ),
                    )
                return ChatTurn(content="No official records were returned.")

        live = CountingMapService([])
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(FanoutProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertEqual(live.map_calls + live.nearby_calls, 1)
        self.assertEqual(execution.policy.tool_calls, 1)
        # A pure-live response is application-owned; the provider does not get
        # a chance to propose extra calls after the deterministic prefetch.
        self.assertEqual(execution.policy.refused_tool_calls, 0)

    async def test_duplicate_tool_fanout_cannot_repeat_the_planned_dispatch(self) -> None:
        class DuplicateFanoutProvider:
            async def chat_turn(
                self,
                messages: list[dict[str, Any]],
                *,
                tools: list[dict[str, Any]] | None = None,
            ) -> ChatTurn:
                if tools and not any(row.get("role") == "tool" for row in messages):
                    return ChatTurn(
                        content=None,
                        tool_calls=tuple(
                            ChatToolCall(
                                id=f"duplicate-{index}",
                                name="list_official_fires",
                                arguments={"place_label": "British Columbia"},
                            )
                            for index in range(10)
                        ),
                    )
                return ChatTurn(content="No official records were returned.")

        live = CountingMapService([])
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(DuplicateFanoutProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        # Only the application-owned province-wide call is executable. Model
        # arguments cannot widen or repeat that deterministic dispatch.
        self.assertEqual(live.map_calls + live.nearby_calls, 1)
        self.assertEqual(execution.policy.tool_calls, 1)
        self.assertEqual(execution.policy.repeated_tool_dispatch, 0)
        self.assertEqual(execution.policy.refused_tool_calls, 0)

    async def test_empty_pure_live_lookup_never_uses_provider_prose(self) -> None:
        provider = CapturingProvider()
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(provider)),
            LiveAnswerCoordinator(cast(Any, CountingMapService([]))),
        )

        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertEqual(provider.calls, 0)
        self.assertIn(
            execution.response.response_mode,
            {ResponseMode.LIVE, ResponseMode.ABSTENTION},
        )
        self.assertNotIn("Ridge Fire", execution.response.answer or "")

    async def test_selection_overrides_named_closest_and_ordinal_record_choice(self) -> None:
        selected = _fire(result_id="incident:7", name="Selected Fire", size_hectares=12.0)
        other = _fire(result_id="incident:8", name="Other Fire", size_hectares=2.0)
        agent = _agent([selected, other])

        for question in (
            "Tell me about Other Fire",
            "Which fire is closest to Kelowna?",
            "What about the second fire?",
        ):
            with self.subTest(question=question):
                execution = await agent.answer(
                    QueryRequest(
                        question=question,
                        context=MapContext(selected_live_result_id="incident:7"),
                    )
                )

                self.assertEqual(execution.response.selected_live_result_id, "incident:7")
                self.assertIn("Selected Fire", execution.response.answer or "")
                self.assertNotIn("Other Fire", execution.response.answer or "")

    async def test_closest_near_a_place_names_a_fetched_fire(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="where is the closest moutainfire near Kelowna")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(execution.tools, (AgentTool.LIST_OFFICIAL_FIRES,))
        self.assertIn("Mountain Fire", execution.response.answer or "")
        self.assertNotIn("capability", (execution.response.answer or "").casefold())
        self.assertEqual(execution.response.live_results[0].name, "Mountain Fire")

    async def test_where_is_named_fire_in_kelowna_uses_stated_community(self) -> None:
        live = FixedLiveService(
            [
                _fire(result_id="incident:7", name="Mountain Fire"),
                _fire(result_id="incident:8", name="Unrelated Ridge Fire"),
            ]
        )
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )

        execution = await agent.answer(
            QueryRequest(question="where is the moutain fire in kelowna ?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(getattr(live.requested_location, "label", None), "kelowna")
        self.assertIsNotNone(execution.response.resolved_location)
        self.assertIn("Mountain Fire", execution.response.answer or "")
        self.assertNotIn("Unrelated Ridge Fire", execution.response.answer or "")
        self.assertEqual(
            [item.name for item in execution.response.live_results], ["Mountain Fire"]
        )
        self.assertFalse(execution.response.required_input)

    async def test_named_fire_miss_does_not_substitute_an_unrelated_nearby_record(
        self,
    ) -> None:
        agent = _agent([_fire(result_id="incident:8", name="Unrelated Ridge Fire")])

        execution = await agent.answer(
            QueryRequest(question="where is Mountain Fire in Kelowna?")
        )

        self.assertFalse(execution.response.live_results)
        answer = execution.response.answer or ""
        self.assertIn("do not report that fact", answer)
        self.assertIn("No unrelated nearby record was substituted", answer)
        self.assertNotIn("Mountain Fire", answer)
        self.assertNotIn("Unrelated Ridge Fire", answer)
        rebuilt = AskResponse.model_validate(execution.response.model_dump(mode="python"))
        self.assertIn("No unrelated nearby record was substituted", rebuilt.history_text or "")

    async def test_contracted_named_fire_question_keeps_no_substitution_boundary(
        self,
    ) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:7", name="Mountain Fire"),
                _fire(result_id="incident:8", name="Unrelated Ridge Fire"),
            ]
        )

        execution = await agent.answer(
            QueryRequest(question="where's Mountain Fire in Kelowna?")
        )

        self.assertEqual(
            [item.name for item in execution.response.live_results], ["Mountain Fire"]
        )
        self.assertNotIn("Unrelated Ridge Fire", execution.response.answer or "")

    async def test_exact_incident_number_prefers_incident_point_over_shared_perimeter(
        self,
    ) -> None:
        incident = _fire(
            result_id="incident:1068",
            name="Quilpituk Creek",
            incident_number="K51402",
            status="Under Control",
        )
        perimeter = _fire(
            result_id="perimeter:138",
            name=None,
            incident_number="K51402",
            status="Under Control",
            kind=LiveResultKind.PERIMETER,
            geometry={
                "type": "Polygon",
                "coordinates": [[[-119.52, 50.06], [-119.51, 50.06], [-119.52, 50.06]]],
            },
        )
        agent = _agent(
            [incident, perimeter, _fire(result_id="incident:9", name="Unrelated Ridge Fire")]
        )

        execution = await agent.answer(
            QueryRequest(question="Where is wildfire K51402 right now?")
        )

        self.assertEqual(
            [item.result_id for item in execution.response.live_results],
            ["incident:1068"],
        )
        self.assertEqual(
            execution.response.selected_live_result_id,
            "incident:1068",
        )
        answer = execution.response.answer or ""
        self.assertIn("Quilpituk Creek", answer)
        self.assertIn("K51402", answer)
        self.assertIn("Point", answer)
        self.assertNotIn("-119.5", answer)
        self.assertNotIn("locatable geometry", answer.casefold())

    def test_exact_incident_identity_survives_supported_history_follow_up(self) -> None:
        incident = _fire(
            result_id="incident:1068",
            name="Quilpituk Creek",
            incident_number="K51402",
        )
        perimeter = _fire(
            result_id="perimeter:138",
            incident_number="K51402",
            kind=LiveResultKind.PERIMETER,
        )
        request = QueryRequest(
            question="How large is it?",
            history=[
                ConversationTurn(role="user", content="Where is wildfire K51402 right now?"),
                ConversationTurn(
                    role="assistant",
                    content=(
                        "The official incident record maps Quilpituk Creek (K51402) as a Point."
                    ),
                ),
            ],
        )

        filtered = filter_requested_named_fire_results(request, [incident, perimeter])

        self.assertEqual([item.result_id for item in filtered], ["incident:1068"])

    async def test_exact_incident_selection_supports_distance_follow_up(self) -> None:
        incident = _fire(
            result_id="incident:1068",
            name="Quilpituk Creek",
            incident_number="K51402",
            longitude=-120.2,
            latitude=50.1,
        )
        agent = _agent([incident])
        first_question = "Where is wildfire K51402 right now?"

        first = await agent.answer(QueryRequest(question=first_question))
        selected_id = first.response.selected_live_result_id
        self.assertEqual(selected_id, "incident:1068")

        follow_up = await agent.answer(
            QueryRequest(
                question="How far is it from Kelowna?",
                history=[
                    ConversationTurn(role="user", content=first_question),
                    ConversationTurn(
                        role="assistant",
                        content=first.response.answer or "",
                    ),
                ],
                context=MapContext(selected_live_result_id=selected_id),
            )
        )

        self.assertEqual(follow_up.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(follow_up.response.selected_live_result_id, "incident:1068")
        self.assertIn("Quilpituk Creek", follow_up.response.answer or "")
        self.assertRegex(follow_up.response.answer or "", r"\d+(?:\.\d+)? km")

    async def test_max_hectares_uses_official_size_field(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Small Fire",
                    size_hectares=12.0,
                    fire_centre="Kamloops",
                ),
                _fire(
                    result_id="incident:2",
                    name="Ridge Fire",
                    size_hectares=840.0,
                    fire_centre="Southeast",
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="which BC mountain fire has the most burned hectares")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Ridge Fire", execution.response.answer or "")
        self.assertIn("840", execution.response.answer or "")
        self.assertNotIn("Small Fire", execution.response.answer or "")
        self.assertNotRegex(
            execution.response.answer or "",
            r"I (?:don't|do not) have that capability",
        )

    async def test_unknown_when_hectares_field_is_absent(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="which fire has the most burned hectares")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("do not report", (execution.response.answer or "").casefold())
        self.assertNotIn("840", execution.response.answer or "")

    async def test_geography_distribution_uses_official_centres(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Lake Fire",
                    fire_centre="Kamloops",
                    status="Out of Control",
                ),
                _fire(
                    result_id="incident:2",
                    name="Ridge Fire",
                    fire_centre="Kamloops",
                    status="Being Held",
                ),
                _fire(
                    result_id="incident:3",
                    name="Peak Fire",
                    fire_centre="Southeast",
                    status="Being Held",
                ),
                _fire(
                    result_id="perimeter:1",
                    name="Lake Fire perimeter",
                    fire_centre="Phantom",
                    status="Perimeter-only status",
                    kind=LiveResultKind.PERIMETER,
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="distribution of mountain fire geography")
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Kamloops has 2 incidents", answer)
        self.assertIn("Southeast has 1 incident", answer)
        self.assertIn("highest count in this bounded result", answer)
        self.assertNotIn("Phantom", answer)
        self.assertNotIn("Perimeter-only status", answer)

    async def test_area_ranking_uses_province_wide_official_fire_centres(self) -> None:
        live = CountingMapService(
            [
                _fire(result_id="incident:1", fire_centre="Kamloops"),
                _fire(result_id="incident:2", fire_centre="Kamloops"),
                _fire(result_id="incident:3", fire_centre="Coastal"),
            ]
        )
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )

        execution = await agent.answer(
            QueryRequest(question="which areas of BC have the most wildfires?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(live.map_calls, 1)
        self.assertEqual(live.nearby_calls, 0)
        self.assertEqual(
            live.map_layer_requests,
            [(LiveResultKind.INCIDENT,)],
        )
        self.assertIn("Kamloops has 2 incidents", execution.response.answer or "")
        self.assertIsNone(execution.response.required_input)

        where_most = await agent.answer(
            QueryRequest(question="Where are most wildfires in BC?")
        )
        self.assertEqual(where_most.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Kamloops has 2 incidents", where_most.response.answer or "")
        self.assertIn("Coastal has 1 incident", where_most.response.answer or "")

    async def test_requested_unsupported_geographies_remain_explicitly_unknown(
        self,
    ) -> None:
        records = [
            _fire(result_id="incident:1", fire_centre="Kamloops"),
            _fire(result_id="incident:2", fire_centre="Kamloops"),
            _fire(result_id="incident:3", fire_centre="Southeast"),
        ]
        cases = (
            (
                "Break down the current wildfire count by region in BC.",
                "These fetched incident records use the official fire-centre label",
                (),
            ),
            (
                "Are active wildfires more concentrated in northern or southern BC?",
                "The official records do not provide a validated north/south classification",
                ("north-versus-south",),
            ),
            (
                "Show current wildfire density by latitude bands across BC.",
                "FireLens has no validated latitude-band or density aggregation",
                ("area denominators are not defined",),
            ),
            (
                "What is wildfire density in BC?",
                "FireLens has no validated wildfire-density measure or area denominator",
                ("does not calculate a density",),
            ),
            (
                "Compare current wildfires in the Okanagan vs Kootenays.",
                "The official records do not provide a validated "
                "Okanagan-versus-Kootenays classification",
                ("does not make that regional comparison",),
            ),
        )

        for question, lead, extra_phrases in cases:
            with self.subTest(question=question):
                execution = await _agent(records).answer(QueryRequest(question=question))
                answer = execution.response.answer or ""
                self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
                self.assertTrue(answer.startswith(lead), answer)
                for phrase in extra_phrases:
                    self.assertIn(phrase, answer)
                self.assertIn("Kamloops has 2 incidents", answer)
                self.assertIn("Southeast has 1 incident", answer)
                self.assertNotIn("records do not include incident geography", answer)
                self.assertNotIn("records do not include geometry", answer)

    async def test_per_centre_counts_and_singular_centre_ranking_share_distribution(
        self,
    ) -> None:
        records = [
            _fire(result_id="incident:1", fire_centre="Kamloops"),
            _fire(result_id="incident:2", fire_centre="Kamloops"),
            _fire(result_id="incident:3", fire_centre="Coastal"),
        ]
        execution = await _agent(records).answer(
            QueryRequest(question="how many wildfires are in each fire centre?")
        )
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Kamloops has 2 incidents", execution.response.answer or "")
        self.assertIn("Coastal has 1 incident", execution.response.answer or "")

        ranking = await _agent(records).answer(
            QueryRequest(question="which fire centre has the most wildfires?")
        )
        self.assertEqual(ranking.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Kamloops", ranking.response.answer or "")
        self.assertIn("with 2", ranking.response.answer or "")

        tied = await _agent(
            [
                _fire(result_id="incident:4", fire_centre="Coastal"),
                _fire(result_id="incident:5", fire_centre="Kamloops"),
            ]
        ).answer(QueryRequest(question="which fire centre has the most wildfires?"))
        self.assertIn("Coastal, Kamloops are tied", tied.response.answer or "")
        self.assertIn("with 1 each", tied.response.answer or "")

    async def test_regional_count_summary_uses_human_count_phrases_and_status_order(
        self,
    ) -> None:
        execution = await _agent(
            [
                _fire(
                    result_id="incident:1",
                    fire_centre="Kamloops Fire Centre",
                    status="Being Held",
                ),
                _fire(
                    result_id="incident:2",
                    fire_centre="Kamloops Fire Centre",
                    status="Out of Control",
                ),
                _fire(
                    result_id="incident:3",
                    fire_centre="Southeast Fire Centre",
                    status="Being Held",
                ),
            ]
        ).answer(QueryRequest(question="break down current wildfires by region in BC"))

        answer = execution.response.answer or ""
        self.assertIn(
            "Kamloops Fire Centre has 2 incidents, the highest count in this bounded result.",
            answer,
        )
        self.assertIn("Other fire-centre counts: Southeast Fire Centre has 1 incident.", answer)
        self.assertIn(
            "Statuses in the same records: 2 Being Held and 1 Out of Control.", answer
        )
        self.assertNotIn("=", answer)

    async def test_regional_count_summary_explains_ties_and_singular_counts(self) -> None:
        execution = await _agent(
            [
                _fire(result_id="incident:1", fire_centre="Coastal", status="Being Held"),
                _fire(result_id="incident:2", fire_centre="Kamloops", status="Out of Control"),
            ]
        ).answer(QueryRequest(question="break down current wildfires by region in BC"))

        answer = execution.response.answer or ""
        self.assertIn(
            "Coastal and Kamloops are tied for the highest count in this bounded result, "
            "with 1 incident each.",
            answer,
        )
        self.assertIn(
            "Statuses in the same records: 1 Being Held and 1 Out of Control.", answer
        )

    async def test_largest_wildfire_by_hectares_uses_full_bc_map(self) -> None:
        live = CountingMapService(
            [
                _fire(result_id="incident:1", name="Small Fire", size_hectares=12),
                _fire(result_id="incident:2", name="Large Fire", size_hectares=840),
            ]
        )
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )

        execution = await agent.answer(
            QueryRequest(question="largest wildfire in BC by hectares")
        )

        self.assertEqual(live.map_calls, 1)
        self.assertEqual(live.nearby_calls, 0)
        self.assertIn("Large Fire", execution.response.answer or "")
        self.assertIn("840", execution.response.answer or "")

    async def test_kit_question_uses_reviewed_guidance(self) -> None:
        agent = _agent([], static=KitStatic())
        execution = await agent.answer(
            QueryRequest(question="What belongs in a grab-and-go bag?")
        )

        self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(
            execution.response.claims[0].supports[0].quote, execution.response.answer
        )
        self.assertFalse(execution.response.live_results)

    async def test_alert_and_go_bag_prefetches_reviewed_guidance(self) -> None:
        live = CountingMapService(
            [
                _fire(
                    result_id="evacuation:1",
                    name="Kamloops alert",
                    kind=LiveResultKind.EVACUATION,
                    longitude=-120.33,
                    latitude=50.67,
                )
            ]
        )
        agent = FireLensAgent(
            cast(Any, KitStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="Is there an alert for Kamloops and what should go in a go-bag?"
            )
        )

        self.assertIn(AgentTool.SEARCH_REVIEWED_GUIDANCE, execution.tools)
        self.assertIn(AgentTool.LIST_OFFICIAL_EVACUATIONS, execution.tools)
        self.assertEqual(execution.response.response_mode, ResponseMode.MIXED)
        self.assertTrue(execution.response.live_results)
        self.assertTrue(execution.response.claims)

    async def test_partial_layer_outage_response_survives_contract_revalidation(self) -> None:
        class PartialLive(FixedLiveService):
            async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
                layers = kwargs.get("layers")
                if layers and LiveResultKind.EVACUATION in layers:
                    raise LiveDataUnavailable("evacuation source is unavailable")
                return await super().map_results(*args, **kwargs)

            async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
                layers = kwargs.get("layers")
                if layers and LiveResultKind.EVACUATION in layers:
                    raise LiveDataUnavailable("evacuation source is unavailable")
                return await super().nearby_page(location, *args, **kwargs)

        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(
                cast(Any, PartialLive([_fire(result_id="incident:1", name="Ridge Fire")]))
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there fires and evacuation orders near Kelowna?")
        )

        response = execution.response
        self.assertIn(LiveResultKind.EVACUATION, response.unavailable_layers)
        self.assertIn(
            "could not verify evacuation records",
            (response.answer or "").casefold(),
        )
        self.assertIn("Available official records in this response", response.answer or "")
        self.assertIn("Ridge Fire: Being Held", response.answer or "")
        self.assertNotIn("No fetched official", response.answer or "")
        # FastAPI revalidates the response model on serialization; a stale
        # history_text after the limitation append must not 500 a served Ask.
        AskResponse.model_validate(response.model_dump(mode="json"))

    async def test_precaution_near_mountain_fire_uses_reviewed_guidance_not_live(self) -> None:
        live = CountingMapService([])
        agent = FireLensAgent(
            cast(Any, KitStatic()),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        for question in (
            "what precaution should I take if I am near moutain fire",
            "What precautions should I take if I am near a mountain fire?",
        ):
            with self.subTest(question=question):
                live.map_calls = 0
                live.nearby_calls = 0
                live.resolve_calls = 0
                execution = await agent.answer(QueryRequest(question=question))
                self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
                self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
                self.assertFalse(execution.response.live_results)
                self.assertEqual(live.map_calls, 0)
                self.assertEqual(live.nearby_calls, 0)
                self.assertEqual(live.resolve_calls, 0)
                self.assertIn("water", (execution.response.answer or "").casefold())

    async def test_safety_language_is_vetoed_then_rewritten(self) -> None:
        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            LiveAnswerCoordinator(
                cast(
                    Any, FixedLiveService([_fire(result_id="incident:7", name="Mountain Fire")])
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertEqual(provider.rewrites, 0)
        self.assertEqual(provider.turns, 0)
        answer = execution.response.answer or ""
        self.assertIn("Mountain Fire", answer)
        self.assertNotIn("evacuate", answer.casefold())
        self.assertNotIn("Phantom Ridge", answer)
        self.assertNotIn("123 Main", answer)

    async def test_input_seatbelt_blocks_evacuate_without_a_model_call(self) -> None:
        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(question="Should I evacuate from Kelowna right now?")
        )

        self.assertEqual(execution.route, QueryRoute.PROHIBITED)
        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(provider.turns, 0)
        self.assertIn("cannot decide", (execution.response.answer or "").casefold())
        self.assertIn("kelowna", (execution.response.answer or "").casefold())
        self.assertIsNone(execution.response.required_input)
        self.assertGreaterEqual(len(execution.response.related_links), 2)

    async def test_generic_return_condition_compiles_the_reviewed_claim(self) -> None:
        static = ApprovedReturnStatic()
        live = CountingMapService([])
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        )

        execution = await agent.answer(
            QueryRequest(question="Can I return home after an evacuation?")
        )

        response = execution.response
        self.assertEqual(execution.route, QueryRoute.RELATED)
        self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
        self.assertEqual(response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(len(response.claims), 1)
        publication = response.claims[0].publication
        self.assertIsNotNone(publication)
        assert publication is not None
        self.assertEqual(publication.typed_claim_id, "TC-EVAC-003-01")
        self.assertEqual(publication.kind.value, "structured_reviewed")
        self.assertIn("only return home when officials say it is safe", response.answer or "")
        self.assertEqual(
            static.calls,
            [
                (
                    "Can I return home after an evacuation?",
                    {"allow_live": False, "prefer_reviewed_quotes": True},
                )
            ],
        )
        self.assertEqual((live.map_calls, live.nearby_calls, live.resolve_calls), (0, 0, 0))

    async def test_universal_evacuation_distance_uses_uncovered_high_risk_handoff(
        self,
    ) -> None:
        for question in (
            "Tell me the universal distance everyone should evacuate from every wildfire.",
            "Give a universal evacuation distance every family must follow.",
            "What exact evacuation distance should every resident use from any wildfire?",
            (
                "Give one exact evacuation radius in kilometres that is safe for every "
                "wildfire and every person."
            ),
        ):
            live = CountingMapService([])
            agent = FireLensAgent(
                cast(Any, SilentStatic()),
                LiveAnswerCoordinator(cast(Any, live)),
            )
            with self.subTest(question=question):
                execution = await agent.answer(QueryRequest(question=question))

                response = execution.response
                self.assertEqual(execution.route, QueryRoute.RELATED)
                self.assertEqual(execution.tools, ())
                self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
                self.assertEqual(
                    response.reason_code,
                    ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED,
                )
                self.assertEqual(
                    response.answer,
                    "FireLens does not have a reviewed structured claim for this high-risk "
                    "question. Use the issuing authority for official wording.",
                )
                self.assertFalse(response.claims)
                self.assertFalse(response.evidence)
                self.assertFalse(response.live_results)
                self.assertNotRegex(response.answer or "", r"\b\d+(?:\.\d+)?\b")
                self.assertEqual(
                    (live.map_calls, live.nearby_calls, live.resolve_calls),
                    (0, 0, 0),
                )

    async def test_named_place_how_close_is_not_unbound(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="perimeter:9",
                    name="Vernon Perimeter",
                    kind=LiveResultKind.PERIMETER,
                )
            ]
        )
        for question in (
            "How close is the wildfire perimeter near Vernon today?",
            "Which official wildfire perimeter is nearest to Vernon?",
        ):
            with self.subTest(question=question):
                execution = await agent.answer(QueryRequest(question=question))

                answer = execution.response.answer or ""
                self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
                self.assertNotIn("Select a mapped fire", answer)
                self.assertIn("Vernon Perimeter", answer)
                self.assertRegex(answer, r"\d+(?:\.\d+)? km")

    async def test_deictic_distance_without_selection_still_abstains(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="How far is this fire from Kelowna?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertIn("Select a mapped fire", execution.response.answer or "")

    async def test_selected_id_missing_from_nearby_page_still_resolves(self) -> None:
        selected = _fire(result_id="incident:101", name="Far Fire")
        fillers = [
            _fire(result_id=f"incident:{index}", name=f"Filler {index}") for index in range(100)
        ]
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(
                cast(
                    Any,
                    FixedLiveService(
                        fillers,
                        nearby_results=fillers,
                        map_results=[*fillers, selected],
                    ),
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What source reported it?",
                context=MapContext(selected_live_result_id="incident:101"),
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Far Fire", execution.response.answer or "")
        self.assertEqual(execution.response.selected_live_result_id, "incident:101")

    async def test_closest_uses_minimum_distance_not_first_record(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Far Fire",
                    longitude=-123.0,
                    latitude=49.0,
                ),
                _fire(
                    result_id="incident:2",
                    name="Near Fire",
                    longitude=-119.49,
                    latitude=49.88,
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="What is the closest wildfire near Kelowna?")
        )

        answer = execution.response.answer or ""
        self.assertIn("Near Fire", answer)
        self.assertNotIn("Far Fire", answer)

    async def test_two_largest_compare_uses_official_sizes(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Small Fire", size_hectares=12.0),
                _fire(result_id="incident:2", name="Ridge Fire", size_hectares=840.0),
                _fire(result_id="incident:3", name="Lake Fire", size_hectares=200.0),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Compare the two largest BC mountain fires by hectares")
        )

        answer = execution.response.answer or ""
        self.assertIn("Ridge Fire", answer)
        self.assertIn("Lake Fire", answer)
        self.assertNotIn("Small Fire", answer)

    async def test_oldest_says_start_field_is_absent(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="Which official fire is the oldest?")
        )

        self.assertIn("do not report", (execution.response.answer or "").casefold())
        self.assertIn("start", (execution.response.answer or "").casefold())
        self.assertNotIn("Current official information:", execution.response.answer or "")

    async def test_named_fire_existence_does_not_list_substitutes(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(question="Is there a fire called Phantom Ridge Fire?")
        )

        answer = execution.response.answer or ""
        self.assertEqual(
            answer,
            "No fetched official record is named Phantom Ridge Fire.",
        )
        self.assertNotIn("Mountain Fire", answer)

    async def test_fire_number_is_used_when_name_is_missing(self) -> None:
        agent = _agent(
            [_fire(result_id="incident:7", incident_number="K21320", status="Being Held")]
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertIn("K21320", execution.response.answer or "")
        self.assertNotIn("Unnamed official record", execution.response.answer or "")

    async def test_unknown_geometry_is_not_treated_as_closest(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Broken Geometry Fire",
                    geometry={"type": "Polygon", "coordinates": []},
                ),
                _fire(
                    result_id="incident:2",
                    name="Locatable Fire",
                    longitude=-119.2,
                    latitude=49.7,
                ),
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="What is the closest wildfire near Kelowna?")
        )

        answer = execution.response.answer or ""
        self.assertIn("Locatable Fire", answer)
        self.assertNotIn("Broken Geometry Fire", answer)

    async def test_province_count_does_not_treat_page_size_as_total(self) -> None:
        page = [
            _fire(result_id=f"incident:{index}", name=f"Fire {index}") for index in range(100)
        ]
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, FixedLiveService(page, roster_total=240))),
        )
        execution = await agent.answer(
            QueryRequest(question="How many wildfires near Kelowna right now?")
        )

        answer = execution.response.answer or ""
        self.assertIn("100 of 240", answer)
        self.assertNotRegex(answer, r"contains 100 incident records and 0 perimeter")

    async def test_evac_yes_no_answers_the_asked_place(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.NEARBY,
                    status="Order",
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("Kelowna Order", answer)
        self.assertIn("not a stay-or-leave", answer.casefold())

    async def test_static_guidance_preserves_selected_record_id(self) -> None:
        agent = _agent([], static=KitStatic())
        execution = await agent.answer(
            QueryRequest(
                question="What belongs in a grab-and-go bag?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")

    async def test_guidance_tool_keeps_quotes_when_planner_is_adjacent(self) -> None:
        agent = _agent([], static=AdjacentKitStatic())
        execution = await agent.answer(
            QueryRequest(
                question="According to the official guide, what belongs in a grab-and-go bag?"
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertIn("water", (execution.response.answer or "").casefold())
        self.assertNotIn("not verified", (execution.response.answer or "").casefold())

    async def test_province_wide_place_label_uses_full_layer_not_nearby(self) -> None:
        live = FixedLiveService(
            [],
            map_results=[_fire(result_id="incident:9", name="Ridge Fire", size_hectares=840.0)],
            nearby_results=[],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ProvinceLabelProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertIsNone(live.requested_location)
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(execution.response.live_results[0].name, "Ridge Fire")
        self.assertNotEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)

    async def test_model_cannot_invent_a_local_filter_for_an_unlocated_request(self) -> None:
        live = FixedLiveService(
            [],
            map_results=[_fire(result_id="incident:9", name="Ridge Fire")],
            nearby_results=[_fire(result_id="incident:10", name="Kelowna Fire")],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ListKelownaProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )

        execution = await agent.answer(QueryRequest(question="List official active fires."))

        self.assertIsNone(live.requested_location)
        self.assertEqual(
            [item.name for item in execution.response.live_results], ["Ridge Fire"]
        )

    async def test_write_without_tools_still_fetches_official_fires(self) -> None:
        live = FixedLiveService(
            [_fire(result_id="incident:9", name="Ridge Fire", size_hectares=840.0)]
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Are there active wildfires in BC currently?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertTrue(execution.response.live_results)
        self.assertEqual(execution.response.live_results[0].name, "Ridge Fire")

    async def test_definition_keeps_quotes_when_luna_uses_leave_now(self) -> None:
        agent = FireLensAgent(
            cast(Any, _DefinitionStatic(LeaveNowDefinitionProvider())),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the difference between an evacuation alert and an order?"
            )
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertIn("alert", (execution.response.answer or "").casefold())
        self.assertIn("order", (execution.response.answer or "").casefold())
        self.assertNotEqual(execution.response.response_mode, ResponseMode.ABSTENTION)

    async def test_analysis_composer_wins_after_prefetch(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(
                cast(
                    Any,
                    FixedLiveService(
                        [
                            _fire(
                                result_id="incident:1",
                                name="Small Fire",
                                size_hectares=12.0,
                            ),
                            _fire(
                                result_id="incident:2",
                                name="Ridge Fire",
                                size_hectares=840.0,
                            ),
                        ]
                    ),
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="which BC mountain fire has the most burned hectares")
        )

        self.assertIn("Ridge Fire", execution.response.answer or "")
        self.assertIn("840", execution.response.answer or "")
        self.assertNotIn(
            "There are wildfires in British Columbia.", execution.response.answer or ""
        )

    async def test_existence_miss_does_not_list_substitutes(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(WriteOnlyProvider())),
            LiveAnswerCoordinator(
                cast(
                    Any, FixedLiveService([_fire(result_id="incident:2", name="Mountain Fire")])
                )
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="is there a wildfire called Phantom Ridge Fire in BC")
        )

        answer = execution.response.answer or ""
        self.assertEqual(
            answer,
            "No fetched official record is named Phantom Ridge Fire.",
        )
        self.assertNotIn("Mountain Fire", answer)

    async def test_published_answer_strips_precise_coordinates(self) -> None:
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(CoordinateDumpProvider())),
            LiveAnswerCoordinator(
                cast(Any, FixedLiveService([_fire(result_id="incident:2", name="Ridge Fire")]))
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertNotIn("49.589303", execution.response.answer or "")
        self.assertNotIn("-119.906732", execution.response.answer or "")
        self.assertIn("Ridge Fire", execution.response.answer or "")

    async def test_official_packet_omits_raw_coordinates(self) -> None:
        fact = live_record_fact(_fire(result_id="incident:2", name="Ridge Fire"))
        self.assertNotIn("coordinates", fact)
        self.assertNotIn("geometry", fact)
        self.assertEqual(fact["source_updated_at"], "2026-08-15T00:00:00+00:00")

    async def test_mixed_prefetch_does_not_construct_discarded_provider_packet(self) -> None:
        provider = CapturingProvider()

        class KitWithChat(KitStatic):
            def __init__(self, chat_provider: Any) -> None:
                self.provider = chat_provider

        live = FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, KitWithChat(provider)),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question=(
                    "What official fires are near Kelowna, and what belongs in a grab-and-go bag?"
                )
            )
        )

        self.assertIsNone(provider.messages)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(execution.response.response_mode, ResponseMode.MIXED)
        self.assertEqual(
            execution.response.answer_sections[1].text,
            "Include water, medication, and copies of important documents.",
        )

    async def test_unbound_history_reference_does_not_reopen_provider_scope(self) -> None:
        provider = CapturingProvider()
        live = FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")])
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(provider)),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        history = (
            ConversationTurn(role="user", content="Are there active wildfires near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Official BC Wildfire Service records show Ridge Fire near Kelowna.",
            ),
        )
        execution = await agent.answer(
            QueryRequest(
                question="How large is that fire?",
                history=list(history),
            )
        )

        self.assertIsNone(provider.messages)
        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertIn("Select a mapped official record", execution.response.answer or "")

    async def test_unselected_size_follow_up_after_a_place_list_requires_selection(
        self,
    ) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:1",
                    name="Bald Range",
                    status="Fire of Note",
                    size_hectares=120.0,
                ),
                _fire(
                    result_id="incident:2",
                    name="Ridge Fire",
                    status="Being Held",
                    size_hectares=40.0,
                ),
            ]
        )
        history = [
            ConversationTurn(role="user", content="Are there active wildfires near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Bald Range: Fire of Note; Ridge Fire: Being Held.",
            ),
        ]

        execution = await agent.answer(QueryRequest(question="How big is it?", history=history))

        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)
        answer = execution.response.answer or ""
        self.assertIn("Select a mapped official record", answer)
        self.assertNotIn("Bald Range", answer)
        self.assertNotIn("Ridge Fire", answer)

    async def test_unselected_status_follow_up_requires_selection(self) -> None:
        agent = _agent(
            [_fire(result_id="incident:1", name="Bald Range", status="Fire of Note")]
        )
        history = [
            ConversationTurn(role="user", content="Are there active wildfires near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Bald Range: Fire of Note.",
            ),
        ]

        execution = await agent.answer(
            QueryRequest(question="What is its status?", history=history)
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertIn("Select a mapped official record", execution.response.answer or "")
        self.assertNotIn("Bald Range", execution.response.answer or "")

    async def test_tell_me_about_named_fire_filters_the_roster(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Bald Range", status="Fire of Note"),
                _fire(result_id="incident:2", name="Unrelated Ridge Fire"),
            ]
        )

        execution = await agent.answer(QueryRequest(question="Tell me about Bald Range Fire"))

        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(
            [item.name for item in execution.response.live_results],
            ["Bald Range"],
        )
        self.assertNotIn("Unrelated Ridge Fire", execution.response.answer or "")

    async def test_closest_follow_up_after_a_place_list_uses_fetched_distances(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Far Fire", longitude=-123.0, latitude=49.0),
                _fire(
                    result_id="incident:2", name="Near Fire", longitude=-119.49, latitude=49.88
                ),
            ]
        )
        history = [
            ConversationTurn(role="user", content="What official fires are near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Far Fire: Being Held; Near Fire: Being Held.",
            ),
        ]

        execution = await agent.answer(
            QueryRequest(question="How far is the closest one?", history=history)
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Near Fire", answer)
        self.assertNotIn("Far Fire", answer)
        self.assertRegex(answer, r"\d+(?:\.\d+)? km")

    async def test_second_fire_follow_up_binds_to_roster_order(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Bald Range", status="Fire of Note"),
                _fire(result_id="incident:2", name="Ridge Fire", status="Being Held"),
            ]
        )
        history = [
            ConversationTurn(role="user", content="What official fires are near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Bald Range: Fire of Note; Ridge Fire: Being Held.",
            ),
        ]

        execution = await agent.answer(
            QueryRequest(question="What about the second fire?", history=history)
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Ridge Fire", answer)
        self.assertNotIn("Bald Range", answer)

    async def test_second_fire_after_closest_still_uses_the_place_roster(self) -> None:
        agent = _agent(
            [
                _fire(result_id="incident:1", name="Bald Range", status="Fire of Note"),
                _fire(result_id="incident:2", name="Ridge Fire", status="Being Held"),
            ]
        )
        history = [
            ConversationTurn(role="user", content="What official fires are near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Bald Range: Fire of Note; Ridge Fire: Being Held.",
            ),
            ConversationTurn(role="user", content="How far is the closest one?"),
            ConversationTurn(
                role="assistant", content="Ridge Fire is the closest official record."
            ),
        ]

        execution = await agent.answer(
            QueryRequest(question="What about the second fire?", history=history)
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertIn("Ridge Fire", answer)
        self.assertNotIn("Bald Range", answer)

    async def test_second_fire_follow_up_asks_to_select_when_the_roster_is_short(self) -> None:
        agent = _agent([_fire(result_id="incident:1", name="Bald Range")])
        history = [
            ConversationTurn(role="user", content="What official fires are near Kelowna?"),
            ConversationTurn(
                role="assistant",
                content="Current official information: Bald Range: Fire of Note.",
            ),
        ]

        execution = await agent.answer(
            QueryRequest(question="What about the second fire?", history=history)
        )

        answer = execution.response.answer or ""
        self.assertIn("Select a mapped official record", answer)
        self.assertNotIn("Bald Range", answer)

    def test_compose_official_answer_does_not_substitute_selected(self) -> None:
        answer = compose_official_answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            ),
            [_fire(result_id="incident:8", name="Other Fire")],
        )
        self.assertIn("will not substitute", answer)
        self.assertNotIn("Other Fire", answer)

    async def test_map_how_far_keeps_the_selected_record(self) -> None:
        selected = _with_distance(
            _fire(result_id="incident:7", name="Bald Range"),
            12.4,
        )
        other = _with_distance(_fire(result_id="incident:8", name="Other Fire"), 1.0)
        agent = _agent([selected, other])
        execution = await agent.answer(
            QueryRequest(
                question="How far is this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")
        self.assertIn("Bald Range", answer)
        self.assertNotIn("Other Fire", answer)
        self.assertRegex(answer, r"12(?:\.0+|\.4)? km")

    async def test_missing_selected_record_does_not_substitute_nearby(self) -> None:
        live = FixedLiveService(
            [_fire(result_id="incident:8", name="Other Fire")],
            map_results=[],
            nearby_results=[_fire(result_id="incident:8", name="Other Fire")],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ListKelownaProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(execution.response.status, ResponseStatus.ABSTENTION)
        self.assertIn("did not substitute", " ".join(execution.response.limitations))
        self.assertNotIn("Other Fire", execution.response.answer or "")

    async def test_evac_yes_no_uses_annotated_relation(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.UNKNOWN,
                    status="Order",
                    longitude=-119.49,
                    latitude=49.88,
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("Kelowna Order", answer)

    async def test_named_place_evacuation_order_uses_relation_without_distance(self) -> None:
        records = [
            _fire(
                result_id=f"evacuation:{index}",
                name="Bald Range Wildfire",
                kind=LiveResultKind.EVACUATION,
                status="Order",
                issuer="Regional District of Okanagan-Similkameen",
                geometry_relation=GeometryRelation.NEARBY,
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-119.8, 49.85],
                            [-119.7, 49.85],
                            [-119.7, 49.95],
                            [-119.8, 49.95],
                            [-119.8, 49.85],
                        ]
                    ],
                },
            )
            for index in range(2)
        ]
        records.append(
            _fire(
                result_id="evacuation:alert",
                name="Bradley Creek Wildfire",
                kind=LiveResultKind.EVACUATION,
                status="Alert",
                issuer="Okanagan Indian Band",
                geometry_relation=GeometryRelation.NEARBY,
            )
        )
        agent = _agent(records)

        execution = await agent.answer(
            QueryRequest(question="Are there evacuation orders near West Kelowna right now?")
        )

        self.assertEqual(len(execution.response.live_results), 3)
        answer = execution.response.answer or ""
        self.assertTrue(answer.startswith("Yes."))
        self.assertIn("West Kelowna", answer)
        self.assertIn("Bald Range Wildfire", answer)
        self.assertIn("Order", answer)
        self.assertIn("nearby", answer.casefold())
        self.assertEqual(answer.count("Bald Range Wildfire"), 1)
        self.assertNotIn("Bradley Creek Wildfire", answer)
        self.assertNotIn("geometry is not locatable", answer.casefold())
        self.assertNotIn("do not include locatable geometry", answer.casefold())

    async def test_province_evacuation_text_groups_without_changing_raw_records(self) -> None:
        records = [
            _fire(
                result_id=f"evacuation:bald:{index}",
                name="Bald Range Wildfire",
                kind=LiveResultKind.EVACUATION,
                status="Order",
                issuer="Regional District of Okanagan-Similkameen",
            )
            for index in range(3)
        ]
        records.extend(
            [
                _fire(
                    result_id="evacuation:bald:alert",
                    name="Bald Range Wildfire",
                    kind=LiveResultKind.EVACUATION,
                    status="Alert",
                    issuer="District of Summerland",
                ),
                _fire(
                    result_id="evacuation:brunswick:order",
                    name="Brunswick Wildfire",
                    kind=LiveResultKind.EVACUATION,
                    status="Order",
                    issuer="Boston Bar First Nation",
                ),
            ]
        )
        agent = _agent(records)

        execution = await agent.answer(
            QueryRequest(
                question="What evacuation alerts and orders are active across BC right now?"
            )
        )

        self.assertEqual(
            [item.result_id for item in execution.response.live_results],
            [item.result_id for item in records],
        )
        answer = execution.response.answer or ""
        self.assertEqual(answer.count("Regional District of Okanagan-Similkameen"), 1)
        self.assertIn("3 area records", answer)
        self.assertIn("District of Summerland", answer)
        self.assertIn("Boston Bar First Nation", answer)

    async def test_provider_cannot_broaden_place_bound_evacuation_fetch(self) -> None:
        live = FixedLiveService(
            [],
            map_results=[
                _fire(
                    result_id="evacuation:3",
                    name="Kelowna Order",
                    kind=LiveResultKind.EVACUATION,
                    geometry_relation=GeometryRelation.UNKNOWN,
                    status="Order",
                    longitude=-119.49,
                    latitude=49.88,
                )
            ],
            nearby_results=[],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(EvacProvinceProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(question="Is Kelowna under an evacuation order?")
        )

        answer = execution.response.answer or ""
        self.assertEqual(live.requested_location.label, "Kelowna")
        self.assertFalse(execution.response.live_results)
        self.assertFalse(answer.startswith("Yes."))
        self.assertNotIn("Kelowna Order", answer)

    async def test_unsupported_selected_redirect_uses_requested_id(self) -> None:
        live = FixedLiveService(
            [
                _fire(result_id="incident:7", name="First Fire"),
                _fire(result_id="incident:8", name="Selected Fire"),
            ]
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(ListKelownaProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        execution = await agent.answer(
            QueryRequest(
                question="Why did this fire start?",
                context=MapContext(selected_live_result_id="incident:8"),
            )
        )

        self.assertEqual(execution.response.selected_live_result_id, "incident:8")
        self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)

    async def test_selected_fetch_skips_duplicate_map_results(self) -> None:
        live = CountingMapService(
            [_fire(result_id="incident:7", name="Mountain Fire")],
            map_results=[_fire(result_id="incident:7", name="Mountain Fire")],
        )
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(GetThenWriteProvider())),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        await agent.answer(
            QueryRequest(
                question="What is the status of this fire?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertEqual(live.map_calls, 1)

    async def test_unavailable_layers_are_surfaced_on_ask(self) -> None:
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, UnavailableLiveService())),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertIn(LiveResultKind.INCIDENT, execution.response.unavailable_layers)
        self.assertTrue(
            any("unavailable" in item.casefold() for item in execution.response.limitations)
        )

    async def test_successful_map_partial_outage_unions_unavailable_layers(self) -> None:
        class PartialMap(FixedLiveService):
            async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
                del args, kwargs
                results = [_fire(result_id="incident:1", name="Ridge Fire")]
                return LiveMapResponse(
                    generated_at=_timestamp(),
                    results=results,
                    aggregate_freshness=aggregate_live_freshness(results),
                    unavailable_layers=[LiveResultKind.PERIMETER],
                )

            async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                raise AssertionError("province-wide map path must not use nearby_page")

        packet = AgentPacket()
        payload = json.loads(
            await execute_tool(
                AgentTool.LIST_OFFICIAL_FIRES.value,
                {},
                request=QueryRequest(
                    question="What official fires are listed?",
                    location=LocationInput(label="British Columbia", radius_km=50),
                ),
                live_coordinator=LiveAnswerCoordinator(cast(Any, PartialMap([]))),
                static_service=SilentStatic(),
                packet=packet,
            )
        )

        self.assertEqual([item["result_id"] for item in payload["records"]], ["incident:1"])
        self.assertEqual(packet.unavailable_layers, [LiveResultKind.PERIMETER])
        self.assertEqual(packet.retrieved_at, _timestamp())

    async def test_successful_nearby_partial_outage_unions_unavailable_layers(self) -> None:
        class PartialNearby(FixedLiveService):
            async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
                del args, kwargs
                raise AssertionError("place-bound nearby path must not use map_results")

            async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
                self.requested_location = location
                del args, kwargs
                results = [_fire(result_id="incident:2", name="Kelowna Fire")]
                return type(
                    "Nearby",
                    (),
                    {
                        "generated_at": _timestamp(),
                        "results": results,
                        "limitations": [],
                        "unavailable_layers": [LiveResultKind.EVACUATION],
                        "resolved_location": CoarseResolvedLocation(
                            latitude=49.88, longitude=-119.49
                        ),
                        "pagination": type("Pagination", (), {"total_results": 1})(),
                    },
                )()

        packet = AgentPacket()
        payload = json.loads(
            await execute_tool(
                AgentTool.LIST_OFFICIAL_FIRES.value,
                {},
                request=QueryRequest(
                    question="What official fires are near Kelowna?",
                    location=LocationInput(label="Kelowna", radius_km=50),
                ),
                live_coordinator=LiveAnswerCoordinator(cast(Any, PartialNearby([]))),
                static_service=SilentStatic(),
                packet=packet,
            )
        )

        self.assertEqual([item["result_id"] for item in payload["records"]], ["incident:2"])
        self.assertEqual(packet.unavailable_layers, [LiveResultKind.EVACUATION])
        self.assertEqual(packet.retrieved_at, _timestamp())

    async def test_selected_empty_map_partial_outage_is_not_missing_selected(self) -> None:
        class EmptyPartialMap(FixedLiveService):
            async def map_results(self, *args: Any, **kwargs: Any) -> LiveMapResponse:
                del args, kwargs
                return LiveMapResponse(
                    generated_at=_timestamp(),
                    results=[],
                    unavailable_layers=[LiveResultKind.INCIDENT],
                )

            async def nearby_page(self, *args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                raise AssertionError("selected map path must not use nearby_page")

        packet = AgentPacket()
        payload = json.loads(
            await execute_tool(
                AgentTool.GET_OFFICIAL_FIRE.value,
                {"result_id": "incident:7"},
                request=QueryRequest(
                    question="What is the status of this fire?",
                    context=MapContext(selected_live_result_id="incident:7"),
                ),
                live_coordinator=LiveAnswerCoordinator(cast(Any, EmptyPartialMap([]))),
                static_service=SilentStatic(),
                packet=packet,
            )
        )

        self.assertEqual(payload["records"], [])
        self.assertEqual(payload["error"], "selected_record_not_found")
        self.assertEqual(packet.unavailable_layers, [LiveResultKind.INCIDENT])
        self.assertNotIn("missing_selected_record", packet.unknown_topics)
        self.assertEqual(packet.retrieved_at, _timestamp())

    async def test_selected_update_question_uses_packet_timestamp(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(
                question="When was this fire last updated?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        self.assertIn("2026-08-15", execution.response.answer or "")

    async def test_selected_status_and_size_question_keeps_both_requested_fields(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:7",
                    name="Mountain Fire",
                    status="Being Held",
                    size_hectares=42.5,
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is its current status and size?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")
        self.assertIn("Being Held", answer)
        self.assertIn("42.5 hectares", answer)
        self.assertNotIn("Select a mapped official record", answer)

    async def test_selected_information_update_question_keeps_source_freshness(self) -> None:
        agent = _agent([_fire(result_id="incident:7", name="Mountain Fire")])
        execution = await agent.answer(
            QueryRequest(
                question="When was that information last updated?",
                context=MapContext(selected_live_result_id="incident:7"),
            )
        )

        answer = execution.response.answer or ""
        self.assertEqual(execution.response.selected_live_result_id, "incident:7")
        self.assertIn("2026-08-15", answer)
        self.assertIn("fresh", answer.casefold())
        self.assertNotIn("Select a mapped official record", answer)

    def test_kilometre_rail_allows_radius_phrasing(self) -> None:
        for answer in (
            "Search used a 50 km radius around the community.",
            "Search used a 50 kilometres radius around the community.",
            "Search used a 50 kilometer radius around the community.",
        ):
            with self.subTest(answer=answer):
                errors = output_rail_errors(answer, AgentPacket())
                self.assertNotIn("invented_kilometre", errors)

    def test_distance_rail_accepts_packet_owned_kilometre_aliases(self) -> None:
        packet = AgentPacket(live_results=[_with_distance(_fire(result_id="incident:7"), 12.0)])

        for answer in (
            "The official record is 12 km away.",
            "The official record is 12 kilometre away.",
            "The official record is 12 kilometres away.",
            "The official record is 12 kilometer away.",
            "The official record is 12 kilometers away.",
        ):
            with self.subTest(answer=answer):
                errors = output_rail_errors(answer, packet)
                self.assertNotIn("invented_kilometre", errors)
                self.assertNotIn("unsupported_distance_unit", errors)

    def test_distance_rail_rejects_unowned_or_converted_distances(self) -> None:
        packet = AgentPacket(live_results=[_with_distance(_fire(result_id="incident:7"), 12.0)])

        for answer, error in (
            ("The official record is 13 kilometres away.", "invented_kilometre"),
            ("The official record is 7 miles away.", "unsupported_distance_unit"),
            ("The official record is 7 mi away.", "unsupported_distance_unit"),
            ("The official record is 700 metres away.", "unsupported_distance_unit"),
            ("The official record is 700 meters away.", "unsupported_distance_unit"),
            ("The official record is seven miles away.", "number_word_distance"),
            ("The official record is twelve kilometres away.", "number_word_distance"),
        ):
            with self.subTest(answer=answer):
                self.assertIn(error, output_rail_errors(answer, packet))

    def test_distance_rail_ignores_unit_mentions_without_distance_assertion(self) -> None:
        errors = output_rail_errors(
            "The source uses kilometre, mile, metre, and meter units.", AgentPacket()
        )
        self.assertNotIn("invented_kilometre", errors)
        self.assertNotIn("unsupported_distance_unit", errors)
        self.assertNotIn("number_word_distance", errors)

    def test_unfetched_feed_rail_vetoes_aqhi_claims(self) -> None:
        errors = output_rail_errors("The AQHI is 3 in Kelowna.", AgentPacket())
        self.assertIn("unfetched_live_feed", errors)

    def test_unfetched_feed_rail_allows_official_handoff(self) -> None:
        errors = output_rail_errors(
            "FireLens is not connected to an official live source for air quality. "
            "Open the related official service for the current value: Current B.C. AQHI.",
            AgentPacket(unknown_topics=["air quality"]),
        )
        self.assertNotIn("unfetched_live_feed", errors)

    def test_fire_name_rail_distinguishes_official_centre_labels(self) -> None:
        packet = AgentPacket(
            live_results=[
                _fire(
                    result_id="incident:7",
                    name="Mountain Fire",
                    fire_centre="Coastal Fire Centre",
                )
            ]
        )

        centre_errors = output_rail_errors(
            "Coastal Fire Centre has the most fetched official records.",
            packet,
        )
        invented_errors = output_rail_errors(
            "Cedar Ridge Fire has the most fetched official records.",
            packet,
        )

        self.assertNotIn("unfetched_fire_name", centre_errors)
        self.assertIn("unfetched_fire_name", invented_errors)

    def test_fire_name_rail_does_not_exempt_a_disclaimer_phrase(self) -> None:
        packet = AgentPacket(live_results=[_fire(result_id="incident:7", name="Ridge Fire")])

        errors = output_rail_errors("No fetched official record is named Summit Fire.", packet)

        self.assertIn("unfetched_fire_name", errors)

    async def test_out_of_province_live_ask_redirects_without_bc_rows(self) -> None:
        for question in (
            "Are there wildfires near Calgary right now?",
            "Are there wildfires across Canada right now?",
        ):
            with self.subTest(question=question):
                live = CountingMapService([_fire(result_id="incident:7", name="Mountain Fire")])
                agent = FireLensAgent(
                    cast(Any, SilentStatic()),
                    LiveAnswerCoordinator(cast(Any, live)),
                )
                execution = await agent.answer(QueryRequest(question=question))

                self.assertEqual(execution.response.response_mode, ResponseMode.SCOPE_REDIRECT)
                self.assertFalse(execution.response.live_results)
                self.assertEqual(live.map_calls, 0)
                self.assertEqual(live.nearby_calls, 0)
                self.assertEqual(live.resolve_calls, 0)
                answer = execution.response.answer or ""
                self.assertIn("British Columbia", answer)
                self.assertNotIn("Mountain Fire", answer)

    async def test_unresolved_place_asks_for_a_bc_community(self) -> None:
        class UnresolvedPlaceLive(FixedLiveService):
            async def nearby_page(self, location: Any, *args: Any, **kwargs: Any) -> Any:
                del location, args, kwargs
                raise LiveDataUnavailable(
                    "the place label could not be resolved",
                    kind=LiveDataErrorKind.NOT_FOUND,
                )

            async def resolve_location(self, _location: Any) -> tuple[float, float]:
                raise LiveDataUnavailable(
                    "the place label could not be resolved",
                    kind=LiveDataErrorKind.NOT_FOUND,
                )

        question = "Are there wildfires near Xyzzyville?"
        agent = FireLensAgent(
            cast(Any, SilentStatic()),
            LiveAnswerCoordinator(cast(Any, UnresolvedPlaceLive([]))),
        )
        execution = await agent.answer(QueryRequest(question=question))

        response = execution.response
        self.assertEqual(response.response_mode, ResponseMode.REQUIRES_INPUT)
        assert response.required_input is not None
        self.assertEqual(response.required_input.continuation_question, question)
        self.assertIn("BC community", response.answer or "")
        self.assertFalse(response.unavailable_layers)

    async def test_stale_records_are_not_called_current(self) -> None:
        agent = _agent(
            [
                _fire(
                    result_id="incident:7",
                    name="Mountain Fire",
                    freshness=Freshness.STALE,
                )
            ]
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        answer = execution.response.answer or ""
        self.assertNotIn("Current official information", answer)
        self.assertIn("cached records", answer)
        self.assertIn("Mountain Fire", answer)
        self.assertTrue(
            any("cached and may be outdated" in item for item in execution.response.limitations)
        )

    async def test_general_question_uses_validated_background_service(self) -> None:
        static = RecordingStatic(_background_response())
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(QueryRequest(question="Tell me a story about dragons."))

        self.assertEqual(execution.response.response_mode, ResponseMode.BACKGROUND)
        self.assertEqual(execution.tools, (AgentTool.ANSWER_GENERAL_BACKGROUND,))
        self.assertEqual(len(static.calls), 1)
        request, kwargs = static.calls[0]
        self.assertEqual(request.question, "Tell me a story about dragons.")
        self.assertFalse(kwargs["allow_live"])
        self.assertTrue(kwargs["prefer_reviewed_quotes"])

    async def test_general_wildfire_discussion_uses_luna_background_not_live_records(
        self,
    ) -> None:
        static = RecordingStatic(_background_response())
        live = CountingMapService(
            [_fire(result_id="incident:unrelated", name="Unrelated Fire")]
        )
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        question = "What is the most common mistake to make when wildfire is coming?"

        execution = await agent.answer(QueryRequest(question=question))

        self.assertEqual(execution.response.response_mode, ResponseMode.BACKGROUND)
        self.assertEqual(execution.tools, (AgentTool.ANSWER_GENERAL_BACKGROUND,))
        self.assertEqual(live.map_calls, 0)
        self.assertEqual(live.nearby_calls, 0)
        self.assertEqual(live.resolve_calls, 0)
        self.assertEqual(len(static.calls), 1)
        background_request, kwargs = static.calls[0]
        self.assertEqual(background_request.question, question)
        self.assertFalse(kwargs["allow_live"])
        self.assertTrue(kwargs["prefer_reviewed_quotes"])

    async def test_exclusionary_bag_followup_uses_general_background_not_handoff(
        self,
    ) -> None:
        static = RecordingStatic(_background_response())
        live = CountingMapService(
            [_fire(result_id="incident:unrelated", name="Unrelated Fire")]
        )
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        question = "what are something that's not needed for the bag"
        request = QueryRequest(
            question=question,
            history=[
                ConversationTurn(role="user", content="What belongs in a grab-and-go bag?"),
                ConversationTurn(role="assistant", content="Pack water and food."),
            ],
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.response.response_mode, ResponseMode.BACKGROUND)
        self.assertNotEqual(
            execution.response.reason_code,
            ReasonCode.HIGH_RISK_CLAIM_NOT_STRUCTURED,
        )
        self.assertEqual(execution.tools, (AgentTool.ANSWER_GENERAL_BACKGROUND,))
        self.assertEqual(live.map_calls, 0)
        self.assertEqual(live.nearby_calls, 0)
        self.assertEqual(live.resolve_calls, 0)
        self.assertEqual(len(static.calls), 1)
        background_request, kwargs = static.calls[0]
        self.assertEqual(background_request.question, question)
        self.assertFalse(kwargs["allow_live"])
        self.assertTrue(kwargs["prefer_reviewed_quotes"])

    async def test_answer_mismatch_correction_retries_the_previous_user_question(
        self,
    ) -> None:
        static = RecordingStatic(_background_response())
        live = CountingMapService(
            [_fire(result_id="incident:unrelated", name="Unrelated Fire")]
        )
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, live)),
        )
        original = "What is the most common mistake to make when wildfire is coming?"
        request = QueryRequest(
            question="Your answer has nothing to do with my question.",
            history=[
                ConversationTurn(role="user", content=original),
                ConversationTurn(
                    role="assistant",
                    content="Current official information: unrelated fire records.",
                ),
            ],
        )

        execution = await agent.answer(request)

        self.assertEqual(execution.response.response_mode, ResponseMode.BACKGROUND)
        self.assertEqual(live.map_calls, 0)
        self.assertEqual(live.nearby_calls, 0)
        self.assertEqual(len(static.calls), 1)
        retried_request, _kwargs = static.calls[0]
        self.assertEqual(retried_request.question, original)

    async def test_smoke_question_reaches_reviewed_guidance_service(self) -> None:
        static = RecordingStatic(_kit_response(mode=ResponseMode.GROUNDED))
        agent = FireLensAgent(
            cast(Any, static),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )

        execution = await agent.answer(
            QueryRequest(question="What should I know about wildfire smoke?")
        )

        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(execution.tools, (AgentTool.SEARCH_REVIEWED_GUIDANCE,))
        self.assertEqual(len(static.calls), 1)
        request, kwargs = static.calls[0]
        self.assertEqual(request.question, "What should I know about wildfire smoke?")
        self.assertFalse(kwargs["allow_live"])
        self.assertTrue(kwargs["prefer_reviewed_quotes"])

    async def test_unsupported_live_only_redirects_without_provider_or_substitution(
        self,
    ) -> None:
        cases = (
            (
                "What is the AQHI in Kelowna right now?",
                "Current B.C. AQHI",
                "air quality",
            ),
            (
                "What is the current smoke forecast for Kelowna?",
                "Environment Canada weather",
                "weather or smoke forecast",
            ),
            (
                "Where are the firefighting aircraft right now?",
                "BC Wildfire Service",
                "firefighting aircraft",
            ),
            (
                "Are roads closed because of wildfire near Kelowna right now?",
                "DriveBC road conditions",
                "road conditions",
            ),
            (
                "What is the AQHI in Kelowna right now and tell me a dragon story?",
                "Current B.C. AQHI",
                "air quality",
            ),
        )
        for question, link_title, topic in cases:
            with self.subTest(question=question):
                provider = CapturingProvider()
                live = CountingMapService(
                    [_fire(result_id="incident:9", name="Unrelated Ridge Fire")]
                )
                agent = FireLensAgent(
                    cast(Any, _ProviderStatic(provider)),
                    LiveAnswerCoordinator(cast(Any, live)),
                )

                execution = await agent.answer(QueryRequest(question=question))

                response = execution.response
                self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
                self.assertEqual(response.live_results, [])
                self.assertEqual(provider.calls, 0)
                self.assertEqual(live.map_calls, 0)
                self.assertEqual(live.nearby_calls, 0)
                self.assertIn(topic, (response.answer or "").casefold())
                self.assertEqual(response.related_links[0].title, link_title)
                self.assertNotIn("draft validation", (response.answer or "").casefold())
                self.assertNotIn("Unrelated Ridge Fire", response.answer or "")

    def test_rejected_static_draft_cannot_displace_unsupported_live_handoff(self) -> None:
        packet = AgentPacket(
            static_response=AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="d" * 32,
                response_mode=ResponseMode.SCOPE_REDIRECT,
                answer="The generated background answer did not pass FireLens validation.",
                reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
                limitations=["Current AQHI requires live air-quality data."],
            ),
            unknown_topics=["air quality"],
            related_links=[
                RelatedLink(
                    title="Current B.C. AQHI",
                    url=HttpUrl(
                        "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"
                    ),
                    description="Current official AQHI observations and forecasts.",
                )
            ],
        )

        response = compose_response(
            QueryRequest(question="What is the current AQHI in Kelowna?"),
            packet,
            "The generated background answer did not pass FireLens validation.",
        )

        self.assertEqual(response.response_mode, ResponseMode.SCOPE_REDIRECT)
        self.assertEqual(response.related_links[0].title, "Current B.C. AQHI")
        self.assertNotIn("draft", (response.answer or "").casefold())
        self.assertIn("not connected", (response.answer or "").casefold())

    def test_provider_error_is_a_material_limitation_when_records_loaded(self) -> None:
        record = _fire(result_id="incident:7", name="Mountain Fire")
        packet = AgentPacket(live_results=[record])
        packet.policy.fallback_reason = "provider_error"
        response = compose_response(
            QueryRequest(question="What official fires are near Kelowna?"),
            packet,
            "Current official information: Mountain Fire: Being Held.",
        )
        self.assertIn(
            "Official records loaded successfully. AI explanation is temporarily limited.",
            response.limitations,
        )

    def test_closest_response_binds_the_deterministically_selected_record(self) -> None:
        nearest = _with_distance(
            _fire(result_id="incident:near", name="Mountain Fire"),
            5.5,
        )
        farther = _with_distance(
            _fire(result_id="incident:far", name="Bear Creek Fire"),
            18.0,
        )
        response = compose_response(
            QueryRequest(question="Which official wildfire is closest to Kelowna right now?"),
            AgentPacket(live_results=[farther, nearest]),
            "Provider prose is not publication authority.",
        )

        self.assertEqual(response.selected_live_result_id, nearest.result_id)
        self.assertIn("Mountain Fire", response.answer or "")

    def test_large_province_roster_reports_total_distribution_and_explicit_sample(self) -> None:
        records = [
            _fire(
                result_id=f"incident:{index}",
                name=f"Fire {index}",
                status="Being Held" if index < 7 else "Out of Control",
            )
            for index in range(1, 11)
        ]

        response = compose_response(
            QueryRequest(question="Show current official wildfires across British Columbia."),
            AgentPacket(live_results=records),
            "Provider prose is not publication authority.",
        )

        answer = response.answer or ""
        self.assertIn("10 fetched official records", answer)
        self.assertIn("Status distribution", answer)
        self.assertIn("sample of 8 of 10", answer)
        self.assertIn("Fire 1", answer)
        self.assertNotIn("Fire 9:", answer)

    def test_closest_official_next_check_adds_selected_record_handoff(self) -> None:
        nearest = _with_distance(
            _fire(result_id="incident:near", name="Mountain Fire"),
            5.5,
        )
        farther = _with_distance(
            _fire(result_id="incident:far", name="Bear Creek Fire"),
            18.0,
        )

        response = compose_response(
            QueryRequest(
                question=(
                    "How far is the nearest fire from Penticton, and what official "
                    "information should I check next?"
                )
            ),
            AgentPacket(live_results=[farther, nearest]),
            "Provider prose is not publication authority.",
        )

        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertEqual(response.selected_live_result_id, nearest.result_id)
        self.assertEqual(len(response.related_links), 1)
        self.assertEqual(str(response.related_links[0].url), str(nearest.source_url))
        self.assertIn("Related official information", response.answer or "")
        self.assertIn("selected official record", (response.answer or "").casefold())

    async def test_prefetched_packet_gets_single_write_call_without_tools(self) -> None:
        provider = CapturingProvider()
        agent = FireLensAgent(
            cast(Any, _ProviderStatic(provider)),
            LiveAnswerCoordinator(
                cast(Any, FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")]))
            ),
        )
        execution = await agent.answer(
            QueryRequest(question="What official fires are near Kelowna?")
        )

        self.assertEqual(provider.calls, 0)
        self.assertEqual(provider.tools_seen, [])
        self.assertEqual(execution.response.response_mode, ResponseMode.LIVE)
        self.assertEqual(execution.policy.outer_chat_turns, 0)

    async def test_guidance_prefetch_skips_discarded_outer_write(self) -> None:
        provider = CapturingProvider()

        class KitStaticWithProvider(KitStatic):
            def __init__(self, chat_provider: Any) -> None:
                self.provider = chat_provider

        agent = FireLensAgent(
            cast(Any, KitStaticWithProvider(provider)),
            LiveAnswerCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(question="What belongs in a grab-and-go bag?")
        )

        self.assertEqual(provider.calls, 0)
        self.assertEqual(provider.tools_seen, [])
        self.assertEqual(execution.policy.outer_chat_turns, 0)
        self.assertLessEqual(execution.policy.grounded_generations, 1)
        self.assertEqual(execution.response.response_mode, ResponseMode.GROUNDED)
        self.assertEqual(execution.response.answer, execution.response.claims[0].text)

    def test_pure_static_ready_keeps_original_minimum_acceptance(self) -> None:
        packet = AgentPacket(static_response=_kit_response(mode=ResponseMode.GROUNDED))

        self.assertTrue(pure_static_ready(packet))

    async def test_mixed_packet_skips_discarded_outer_write_and_keeps_sections(self) -> None:
        provider = CapturingProvider()

        class KitStaticWithProvider(KitStatic):
            def __init__(self, chat_provider: Any) -> None:
                self.provider = chat_provider

        agent = FireLensAgent(
            cast(Any, KitStaticWithProvider(provider)),
            LiveAnswerCoordinator(
                cast(
                    Any,
                    FixedLiveService([_fire(result_id="incident:9", name="Ridge Fire")]),
                )
            ),
        )

        execution = await agent.answer(
            QueryRequest(
                question=(
                    "Are there active wildfires in BC currently, and what belongs "
                    "in an emergency kit?"
                )
            )
        )

        response = execution.response
        self.assertEqual(provider.calls, 0)
        self.assertEqual(provider.tools_seen, [])
        self.assertEqual(execution.policy.outer_chat_turns, 0)
        self.assertEqual(response.response_mode, ResponseMode.MIXED)
        self.assertEqual(
            response.answer_sections[1].text,
            "Include water, medication, and copies of important documents.",
        )
        self.assertIn("Ridge Fire", response.answer or "")
        self.assertIn(response.answer_sections[1].text, response.answer or "")
        self.assertEqual([claim.claim_id for claim in response.claims], ["C1"])
        self.assertEqual([item.evidence_id for item in response.evidence], ["E1"])

    async def test_public_ask_seatbelt_does_not_use_legacy_live_composer(self) -> None:
        class ForbiddenCoordinator(LiveAnswerCoordinator):
            async def answer(self, request: QueryRequest, static_result: Any) -> AskResponse:
                del request, static_result
                raise AssertionError("public Ask must not use the legacy live answering path")

        provider = InventingThenRewritingProvider()
        agent = FireLensAgent(
            cast(Any, CountingStatic(provider)),
            ForbiddenCoordinator(cast(Any, FixedLiveService([]))),
        )
        execution = await agent.answer(
            QueryRequest(
                question="What is the current air quality in Kelowna and should I evacuate?"
            )
        )

        self.assertEqual(execution.route, QueryRoute.PROHIBITED)
        self.assertEqual(execution.response.response_mode, ResponseMode.ABSTENTION)
        self.assertEqual(provider.turns, 0)
        self.assertIn("cannot decide", (execution.response.answer or "").casefold())
        self.assertIn("kelowna", (execution.response.answer or "").casefold())
        self.assertGreaterEqual(len(execution.response.related_links), 2)
