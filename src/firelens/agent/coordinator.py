"""One bounded agent over official live, reviewed, and general-answer tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from firelens.agent.tools import AgentTool
from firelens.contracts import (
    AskResponse,
    LiveResultKind,
    QueryRequest,
    QueryRoute,
    ResponseMode,
)
from firelens.live_answering import LiveAnswerCoordinator


class StaticAnswerService(Protocol):
    async def ask(
        self,
        request: QueryRequest,
        *,
        allow_live: bool = True,
    ) -> AskResponse: ...


@dataclass(frozen=True)
class AgentExecution:
    response: AskResponse
    route: QueryRoute
    tools: tuple[AgentTool, ...]


def _static_tool(response: AskResponse) -> AgentTool:
    if response.response_mode in {
        ResponseMode.GROUNDED,
        ResponseMode.PARTIAL,
        ResponseMode.CONFLICT,
    }:
        return AgentTool.SEARCH_REVIEWED_GUIDANCE
    return AgentTool.ANSWER_GENERAL_BACKGROUND


def _live_tools(request: QueryRequest, response: AskResponse) -> tuple[AgentTool, ...]:
    tools: list[AgentTool] = []
    if LiveAnswerCoordinator.is_distance_request(request):
        tools.append(AgentTool.CALCULATE_FIRE_DISTANCE)
    elif LiveAnswerCoordinator.is_selected_live_request(request):
        tools.append(AgentTool.GET_FIRE_DETAILS)
    else:
        kinds = {result.kind for result in response.live_results}
        if LiveResultKind.INCIDENT in kinds or LiveResultKind.PERIMETER in kinds:
            tools.append(AgentTool.LIST_ACTIVE_FIRES)
        if LiveResultKind.EVACUATION in kinds:
            tools.append(AgentTool.GET_EVACUATION_INFORMATION)
    if response.response_mode in {ResponseMode.MIXED, ResponseMode.PARTIAL}:
        tools.append(AgentTool.SEARCH_REVIEWED_GUIDANCE)
    return tuple(dict.fromkeys(tools))


class FireLensAgent:
    """Select and execute only application-owned tools for one public request."""

    def __init__(
        self,
        static_service: StaticAnswerService,
        live_coordinator: LiveAnswerCoordinator,
    ) -> None:
        self.static_service = static_service
        self.live_coordinator = live_coordinator

    async def answer(self, request: QueryRequest) -> AgentExecution:
        if not self.live_coordinator.handles(request):
            response = await self.static_service.ask(request)
            return AgentExecution(
                response=response,
                route=QueryRoute.RELATED,
                tools=(_static_tool(response),),
            )

        static_request = self.live_coordinator.static_request(request)
        static_response = (
            await self.static_service.ask(static_request, allow_live=False)
            if static_request is not None
            else None
        )
        response = await self.live_coordinator.answer(request, static_response)
        return AgentExecution(
            response=response,
            route=QueryRoute.LIVE,
            tools=_live_tools(request, response),
        )
