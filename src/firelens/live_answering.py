"""Application coordination for official live and mixed answers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.contracts import (
    AskResponse,
    LiveMapResponse,
    LiveResultKind,
    QueryRequest,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
)
from firelens.live import LiveDataService, LiveDataUnavailable


class LiveAnswerCoordinator:
    """Own live-source policy and composition independently from HTTP transport."""

    def __init__(self, live_service: LiveDataService) -> None:
        self.live_service = live_service

    @staticmethod
    def static_request(request: QueryRequest) -> QueryRequest | None:
        fragment = static_guidance_fragment(request.question)
        if fragment is None:
            return None
        return QueryRequest(question=fragment, history=request.history)

    @staticmethod
    def _supported_static_partial(
        static_result: AskResponse | None,
        current_information: str,
        *,
        limitations: list[str],
        unavailable_layers: list[LiveResultKind] | None = None,
    ) -> AskResponse | None:
        if not (
            static_result is not None
            and static_result.status == ResponseStatus.ANSWER
            and static_result.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
            and static_result.answer
            and static_result.claims
            and static_result.evidence
            and static_result.validation is not None
            and static_result.validation.accepted
        ):
            return None
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static_result.trace_id,
            response_mode=ResponseMode.PARTIAL,
            answer=(
                "Current official information: "
                + current_information
                + "\n\nPreparedness guidance: "
                + static_result.answer
                + "\n\nUncertainty: the current-information part was not established."
            ),
            claims=static_result.claims,
            evidence=static_result.evidence,
            limitations=[*limitations, *static_result.limitations],
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            validation=static_result.validation,
            unavailable_layers=unavailable_layers or [],
        )

    async def answer(
        self, request: QueryRequest, static_result: AskResponse | None
    ) -> AskResponse:
        layers = live_layers_for_question(request.question)
        unsupported_topics = unsupported_live_topics(request.question)

        if not layers:
            topics = ", ".join(unsupported_topics) or "that live information"
            current_gap = f"FireLens V1.5 does not have an official live source for {topics}."
            partial = self._supported_static_partial(
                static_result,
                current_gap,
                limitations=[
                    "No matching record is not a safety determination.",
                    f"Unsupported live topics: {topics}",
                ],
            )
            if partial is not None:
                return partial
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=(
                    f"FireLens V1.5 does not have an official live source for {topics}. "
                    "It will not substitute wildfire incident records for the requested data."
                ),
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                limitations=["No matching record is not a safety determination."],
            )

        if request.location is None and live_query_requires_location(request.question):
            location_gap = (
                "A city or approximate location must be supplied in the location field; "
                "FireLens does not infer it from conversation text."
            )
            partial = self._supported_static_partial(
                static_result,
                location_gap,
                limitations=["No matching record is not a safety determination."],
            )
            if partial is not None:
                return partial
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=(
                    "Share a city or approximate location for this live query, or open "
                    "the official BC Wildfire Service map. FireLens does not infer location."
                ),
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                limitations=["No matching record is not a safety determination."],
            )

        try:
            live = (
                await self.live_service.nearby_results(request.location, layers=layers)
                if request.location is not None
                else await self.live_service.map_results(layers=layers)
            )
        except LiveDataUnavailable:
            live = LiveMapResponse(
                generated_at=datetime.now(UTC),
                results=[],
                unavailable_layers=list(layers),
                limitations=["Official live sources are currently unavailable."],
            )

        if not live.results:
            answer = (
                "No matching official record was found for this query. This does not mean "
                "the area is safe; check the issuing authority and BC Wildfire Service map."
                if len(live.unavailable_layers) < len(layers)
                else "Official live wildfire sources are unavailable, so FireLens cannot establish current conditions."
            )
            partial = self._supported_static_partial(
                static_result,
                answer,
                limitations=[
                    *live.limitations,
                    "No matching record is not a safety determination.",
                    *(
                        ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                        if unsupported_topics
                        else []
                    ),
                ],
                unavailable_layers=live.unavailable_layers,
            )
            if partial is not None:
                return partial
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=answer,
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                limitations=[
                    *live.limitations,
                    *(
                        ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                        if unsupported_topics
                        else []
                    ),
                ],
                unavailable_layers=live.unavailable_layers,
            )

        shown = live.results[:100]
        summary = "; ".join(
            f"{item.name or item.incident_number or item.result_id}: {item.status}"
            for item in shown[:5]
        )
        live_answer = "Current official information: " + summary
        if (
            static_result is not None
            and static_result.status == ResponseStatus.ANSWER
            and static_result.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
            and static_result.answer
            and static_result.claims
            and static_result.evidence
            and static_result.validation is not None
            and static_result.validation.accepted
        ):
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=static_result.trace_id,
                response_mode=ResponseMode.MIXED,
                answer=live_answer + "\n\nPreparedness guidance: " + static_result.answer,
                claims=static_result.claims,
                evidence=static_result.evidence,
                live_results=shown,
                limitations=[*live.limitations, *static_result.limitations],
                validation=static_result.validation,
                unavailable_layers=live.unavailable_layers,
            )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.LIVE,
            answer=live_answer,
            live_results=shown,
            limitations=[
                *live.limitations,
                *(
                    ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                    if unsupported_topics
                    else []
                ),
            ],
            unavailable_layers=live.unavailable_layers,
        )
