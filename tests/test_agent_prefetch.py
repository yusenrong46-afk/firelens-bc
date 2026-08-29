from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from firelens.agent import prefetch
from firelens.agent.packet import AgentPacket
from firelens.agent.query_plan import plan_agent_request
from firelens.agent.runtime_tools import _fetch_layers
from firelens.agent.tools import AgentTool
from firelens.contracts import (
    CoarseResolvedLocation,
    LiveResultKind,
    LocationInput,
    QueryRequest,
)

MIXED_QUESTION = "What official fires are near Kelowna, and what belongs in a grab-and-go bag?"


class _GeographyAdapterSpy:
    def __init__(self) -> None:
        self.map_calls = 0
        self.nearby_calls: list[LocationInput] = []
        self.requested_layers: list[tuple[LiveResultKind, ...]] = []

    async def map_results(self, *, layers: tuple[LiveResultKind, ...]) -> Any:
        self.map_calls += 1
        self.requested_layers.append(layers)
        return SimpleNamespace(
            generated_at=datetime(2026, 8, 29, tzinfo=UTC),
            results=[],
            unavailable_layers=[LiveResultKind.EVACUATION],
        )

    async def nearby_page(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...],
        page: int,
        page_size: int,
    ) -> Any:
        assert page == 1
        assert page_size == 100
        self.nearby_calls.append(location)
        self.requested_layers.append(layers)
        return SimpleNamespace(
            generated_at=datetime(2026, 8, 29, tzinfo=UTC),
            results=[],
            unavailable_layers=[LiveResultKind.EVACUATION],
            resolved_location=CoarseResolvedLocation(latitude=49.9, longitude=-119.5),
            pagination=SimpleNamespace(total_results=0),
        )


def test_analysis_scope_preserves_explicit_place_and_partial_layer_state() -> None:
    async def scenario() -> None:
        live = _GeographyAdapterSpy()
        packet = AgentPacket()

        results, resolved, roster_total = await _fetch_layers(
            live,  # type: ignore[arg-type]
            QueryRequest(question="Show distribution of current fires near Outage Ridge"),
            None,
            (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            packet,
        )

        assert results == []
        assert roster_total == 0
        assert resolved == CoarseResolvedLocation(latitude=49.9, longitude=-119.5)
        assert live.map_calls == 0
        assert [location.label for location in live.nearby_calls] == ["Outage Ridge"]
        assert packet.unavailable_layers == [LiveResultKind.EVACUATION]
        assert packet.retrieved_at == datetime(2026, 8, 29, tzinfo=UTC)

    asyncio.run(scenario())


def test_analysis_scope_obeys_explicit_province_and_location_free_defaults() -> None:
    async def scenario() -> None:
        for request, planned_label in (
            (
                QueryRequest(
                    question="Give me a distribution of the current wildfire in BC",
                    location=LocationInput(label="Kelowna"),
                ),
                None,
            ),
            (QueryRequest(question="Show distribution of current fires"), None),
        ):
            live = _GeographyAdapterSpy()
            packet = AgentPacket()
            _results, resolved, _roster_total = await _fetch_layers(
                live,  # type: ignore[arg-type]
                request,
                planned_label,
                (LiveResultKind.INCIDENT,),
                packet,
            )

            assert live.map_calls == 1
            assert live.nearby_calls == []
            assert resolved is None
            assert packet.unavailable_layers == [LiveResultKind.EVACUATION]

    asyncio.run(scenario())


def test_analysis_scope_uses_request_or_planned_non_province_place_without_invention() -> None:
    async def scenario() -> None:
        for request, planned_label, expected_label in (
            (
                QueryRequest(
                    question="Show distribution of current fires",
                    location=LocationInput(label="Okanagan"),
                ),
                None,
                "Okanagan",
            ),
            (
                QueryRequest(question="Show distribution of current fires"),
                "Outage Ridge",
                "Outage Ridge",
            ),
        ):
            live = _GeographyAdapterSpy()
            packet = AgentPacket()
            _results, resolved, _roster_total = await _fetch_layers(
                live,  # type: ignore[arg-type]
                request,
                planned_label,
                (LiveResultKind.INCIDENT,),
                packet,
            )

            assert live.map_calls == 0
            assert [location.label for location in live.nearby_calls] == [expected_label]
            assert resolved == CoarseResolvedLocation(latitude=49.9, longitude=-119.5)

    asyncio.run(scenario())


def test_planned_mixed_tools_start_together_and_merge_in_plan_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        request = QueryRequest(question=MIXED_QUESTION)
        plan = plan_agent_request(request)
        packet = AgentPacket(query_plan=plan)
        started: set[str] = set()
        both_started = asyncio.Event()

        async def fake_execute_tool(
            name: str,
            arguments: dict[str, Any],
            **kwargs: Any,
        ) -> str:
            del arguments
            isolated: AgentPacket = kwargs["packet"]
            started.add(name)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.5)
            if name == AgentTool.LIST_OFFICIAL_FIRES.value:
                # Finish this call last. The public packet must still preserve plan order.
                await asyncio.sleep(0.02)
            else:
                isolated.policy.consume_retrieval_cycle()
                isolated.policy.consume_grounded_generation()
            isolated.tool_names.append(name)
            return "{}"

        monkeypatch.setattr(prefetch, "execute_tool", fake_execute_tool)

        await asyncio.wait_for(
            prefetch.prefetch_evidence(
                request,
                object(),  # type: ignore[arg-type]
                object(),
                packet,
                plan,
            ),
            timeout=1,
        )

        assert started == {
            AgentTool.LIST_OFFICIAL_FIRES.value,
            AgentTool.SEARCH_REVIEWED_GUIDANCE.value,
        }
        assert packet.tool_names == [call.name.value for call in plan.tool_calls]
        assert packet.policy.tool_calls == len(plan.tool_calls)
        assert packet.policy.retrieval_cycles == 1
        assert packet.policy.grounded_generations == 1
        assert len(packet.tool_fingerprints) == len(plan.tool_calls)
        assert packet.policy.outer_chat_turns == 0

    asyncio.run(scenario())


def test_planned_prefetch_cancellation_cancels_every_in_flight_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        request = QueryRequest(question=MIXED_QUESTION)
        plan = plan_agent_request(request)
        packet = AgentPacket(query_plan=plan)
        started = 0
        cancelled = 0
        all_started = asyncio.Event()

        async def blocking_execute_tool(
            _name: str,
            _arguments: dict[str, Any],
            **_kwargs: Any,
        ) -> str:
            nonlocal started, cancelled
            started += 1
            if started == len(plan.tool_calls):
                all_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled += 1
                raise

        monkeypatch.setattr(prefetch, "execute_tool", blocking_execute_tool)
        task = asyncio.create_task(
            prefetch.prefetch_evidence(
                request,
                object(),  # type: ignore[arg-type]
                object(),
                packet,
                plan,
            )
        )
        await asyncio.wait_for(all_started.wait(), timeout=0.5)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancelled == len(plan.tool_calls)
        assert packet.policy.tool_calls == len(plan.tool_calls)
        assert packet.policy.outer_chat_turns == 0

    asyncio.run(scenario())


def test_duplicate_planned_call_is_not_dispatched_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        request = QueryRequest(question=MIXED_QUESTION)
        plan = plan_agent_request(request)
        duplicate_plan = plan.__class__(
            route=plan.route,
            mode=plan.mode,
            live_layers=plan.live_layers,
            geography=plan.geography,
            location_label=plan.location_label,
            static_subrequest=plan.static_subrequest,
            tool_calls=(plan.tool_calls[0], plan.tool_calls[0]),
        )
        packet = AgentPacket(query_plan=duplicate_plan)
        calls = 0

        async def counting_execute_tool(
            _name: str,
            _arguments: dict[str, Any],
            **_kwargs: Any,
        ) -> str:
            nonlocal calls
            calls += 1
            return "{}"

        monkeypatch.setattr(prefetch, "execute_tool", counting_execute_tool)

        await prefetch.prefetch_evidence(
            request,
            object(),  # type: ignore[arg-type]
            object(),
            packet,
            duplicate_plan,
        )

        assert calls == 1
        assert packet.policy.tool_calls == 1
        assert packet.policy.repeated_tool_dispatch == 1
        assert packet.policy.outer_chat_turns == 0

    asyncio.run(scenario())
