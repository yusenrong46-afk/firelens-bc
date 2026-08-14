"""Application coordination for official live and mixed answers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    AggregateFreshness,
    AskResponse,
    CoarseResolvedLocation,
    LiveMapResponse,
    LiveResultKind,
    LocationInput,
    NearMeResponse,
    QueryRequest,
    ReasonCode,
    RelatedLink,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
)
from firelens.live import LiveDataService, LiveDataUnavailable
from firelens.live_support import distance_to_geometry_km

_DISTANCE_PATTERN = re.compile(
    r"\b(?:how far|distance|kilomet(?:er|re)s?|miles?)\b", re.IGNORECASE
)
_SELECTED_LIVE_PATTERN = re.compile(
    r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|perimeter)\b|"
    r"\b(?:status|happening|updates?|updated|details?|official|size|large)\b",
    re.IGNORECASE,
)

_RELATED_LIVE_LINKS = {
    "air quality": RelatedLink(
        title="Current B.C. AQHI",
        url=HttpUrl("https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"),
        description="Environment and Climate Change Canada current AQHI observations and forecasts.",
    ),
    "road conditions": RelatedLink(
        title="DriveBC road conditions",
        url=HttpUrl("https://www.drivebc.ca/"),
        description="Official B.C. road events, closures, delays, cameras, and conditions.",
    ),
    "weather or smoke forecast": RelatedLink(
        title="Environment Canada weather",
        url=HttpUrl("https://weather.gc.ca/"),
        description="Official current conditions, wind, alerts, and forecasts by place.",
    ),
    "firefighting aircraft": RelatedLink(
        title="BC Wildfire Service",
        url=HttpUrl("https://wildfiresituation.nrs.gov.bc.ca/"),
        description="Official wildfire situation, incidents, notices, and response information.",
    ),
}


class LiveAnswerCoordinator:
    """Own live-source policy and composition independently from HTTP transport."""

    def __init__(self, live_service: LiveDataService) -> None:
        self.live_service = live_service

    @staticmethod
    def is_distance_request(request: QueryRequest) -> bool:
        return bool(_DISTANCE_PATTERN.search(request.question)) and bool(
            request.context.selected_live_result_id
            or re.search(
                r"\b(?:fire|wildfire|incident|perimeter|it|this|that)\b", request.question, re.I
            )
        )

    @staticmethod
    def is_selected_live_request(request: QueryRequest) -> bool:
        return bool(
            request.context.selected_live_result_id
            and _SELECTED_LIVE_PATTERN.search(request.question)
        )

    def handles(self, request: QueryRequest) -> bool:
        """Return whether this bounded coordinator owns the request."""

        from firelens.answering.intent import plan_query
        from firelens.contracts import QueryRoute

        plan = plan_query(request)
        return (
            self.is_distance_request(request)
            or self.is_selected_live_request(request)
            or plan.route == QueryRoute.LIVE
            or (
                bool(unsupported_live_topics(request.question))
                and plan.route == QueryRoute.PROHIBITED
            )
        )

    @staticmethod
    def _freshness_limitation(state: AggregateFreshness) -> str | None:
        if state == AggregateFreshness.STALE:
            return "Cached official records; refresh failed. These records may be outdated."
        if state == AggregateFreshness.MIXED:
            return (
                "Official records include stale cached data because a refresh failed; "
                "some records may be outdated."
            )
        return None

    @staticmethod
    def _unique_limitations(*groups: list[str]) -> list[str]:
        return list(dict.fromkeys(item for group in groups for item in group if item))

    @staticmethod
    def _related_links(topics: tuple[str, ...]) -> list[RelatedLink]:
        return list(
            dict.fromkeys(
                _RELATED_LIVE_LINKS[topic] for topic in topics if topic in _RELATED_LIVE_LINKS
            )
        )

    async def _nearby_records(
        self,
        location: LocationInput,
        *,
        layers: tuple[LiveResultKind, ...],
    ) -> NearMeResponse:
        return await self.live_service.nearby_page(
            location,
            layers=layers,
            page=1,
            page_size=100,
        )

    @staticmethod
    def static_request(request: QueryRequest) -> QueryRequest | None:
        fragment = static_guidance_fragment(request.question)
        if fragment is None:
            return None
        return QueryRequest(
            question=fragment,
            history=request.history,
            context=request.context,
        )

    @staticmethod
    def _location_request(request: QueryRequest) -> AskResponse:
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.REQUIRES_INPUT,
            answer=(
                "Share an approximate location or enter a BC community to continue. "
                "FireLens uses it only for this request."
            ),
            required_input=RequiredInput(
                kind=RequiredInputKind.LOCATION,
                prompt="Use approximate location or enter a BC community.",
                continuation_question=request.question,
            ),
            selected_live_result_id=request.context.selected_live_result_id,
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=[
                "Distance is a straight-line geodesic measurement, not driving distance or a safety assessment."
            ],
        )

    async def _distance_answer(self, request: QueryRequest) -> AskResponse:
        effective_location = request.location or coarse_location_from_question(request.question)
        if effective_location is None:
            return self._location_request(request)
        try:
            latitude, longitude = await self.live_service.resolve_location(effective_location)
            live = await self.live_service.map_results(
                layers=(LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)
            )
        except LiveDataUnavailable:
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=(
                    "The official wildfire layers or BC place lookup are unavailable, so "
                    "FireLens cannot calculate a current distance right now."
                ),
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                limitations=["Unavailable current data is not a safety determination."],
            )

        measured = []
        for item in live.results:
            distance = distance_to_geometry_km(
                item.geometry, latitude=latitude, longitude=longitude
            )
            if distance is None:
                continue
            measured.append(
                item.model_copy(
                    update={
                        "distance_km": round(distance, 1),
                        "distance_basis": (
                            "incident_point"
                            if item.kind == LiveResultKind.INCIDENT
                            else "perimeter_boundary"
                        ),
                    }
                )
            )

        selected_id = request.context.selected_live_result_id
        chosen = (
            next((item for item in measured if item.result_id == selected_id), None)
            if selected_id
            else None
        )
        if selected_id and chosen is None:
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=(
                    "The selected map record is not an available incident point or fire "
                    "perimeter, so FireLens cannot calculate a meaningful fire distance "
                    "from it. Select a mapped fire or perimeter and try again."
                ),
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                selected_live_result_id=selected_id,
                limitations=[
                    "FireLens did not substitute a different nearby fire.",
                    "No matching record is not a safety determination.",
                ],
                unavailable_layers=live.unavailable_layers,
            )
        if chosen is None and measured:
            chosen = min(measured, key=lambda item: item.distance_km or 0.0)
        if chosen is None:
            return AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.ABSTENTION,
                answer=(
                    "No measurable incident point or fire perimeter was available in the "
                    "official layers. Open the related official map source for the latest details."
                ),
                reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                limitations=["No matching record is not a safety determination."],
                unavailable_layers=live.unavailable_layers,
            )

        distance = chosen.distance_km
        assert distance is not None
        basis = (
            "the incident point"
            if chosen.distance_basis == "incident_point"
            else "the nearest mapped perimeter boundary"
        )
        freshness = aggregate_live_freshness([chosen])
        assert freshness is not None
        freshness_limitation = self._freshness_limitation(freshness)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.LIVE,
            answer=(
                f"{chosen.name or chosen.incident_number or 'The selected wildfire'} is "
                f"approximately {distance:.1f} km away in a straight-line geodesic "
                f"measurement to {basis}."
            ),
            live_results=[chosen],
            aggregate_freshness=freshness,
            selected_live_result_id=chosen.result_id,
            resolved_location=CoarseResolvedLocation(
                latitude=latitude,
                longitude=longitude,
            ),
            limitations=self._unique_limitations(
                live.limitations,
                [
                    "This is not driving distance, travel advice, or a safety assessment.",
                    *([freshness_limitation] if freshness_limitation else []),
                ],
            ),
            unavailable_layers=live.unavailable_layers,
        )

    @staticmethod
    def _supported_static_partial(
        static_result: AskResponse | None,
        current_information: str,
        *,
        limitations: list[str],
        unavailable_layers: list[LiveResultKind] | None = None,
        related_links: list[RelatedLink] | None = None,
        resolved_location: CoarseResolvedLocation | None = None,
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
            related_links=related_links or [],
            resolved_location=resolved_location,
        )

    async def answer(
        self, request: QueryRequest, static_result: AskResponse | None
    ) -> AskResponse:
        if self.is_distance_request(request):
            return await self._distance_answer(request)

        layers = live_layers_for_question(request.question)
        effective_location = request.location or coarse_location_from_question(request.question)
        selected_request = self.is_selected_live_request(request)
        selected_id = request.context.selected_live_result_id
        if not layers and selected_request and selected_id is not None:
            selected_kind = selected_id.partition(":")[0]
            layers = {
                "incident": (LiveResultKind.INCIDENT,),
                "perimeter": (LiveResultKind.PERIMETER,),
                "evacuation": (LiveResultKind.EVACUATION,),
            }.get(selected_kind, ())
        unsupported_topics = unsupported_live_topics(request.question)

        if not layers:
            topics = ", ".join(unsupported_topics) or "that live information"
            related_links = self._related_links(unsupported_topics)
            resolved_location: CoarseResolvedLocation | None = None
            if effective_location is not None:
                try:
                    latitude, longitude = await self.live_service.resolve_location(
                        effective_location
                    )
                except LiveDataUnavailable:
                    pass
                else:
                    resolved_location = CoarseResolvedLocation(
                        latitude=latitude,
                        longitude=longitude,
                    )
            current_gap = (
                f"FireLens is not connected to an official live source for {topics}. "
                "Use the related official service for the current value."
            )
            partial = self._supported_static_partial(
                static_result,
                current_gap,
                limitations=[
                    "No matching record is not a safety determination.",
                    f"Unsupported live topics: {topics}",
                ],
                related_links=related_links,
                resolved_location=resolved_location,
            )
            if partial is not None:
                return partial
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.SCOPE_REDIRECT,
                answer=(
                    f"FireLens is not connected to an official live source for {topics}, "
                    "so it cannot verify that current value here. Open the related official "
                    "service below; FireLens will not substitute wildfire records for it."
                ),
                reason_code=ReasonCode.SCOPE_REDIRECT,
                limitations=["No matching record is not a safety determination."],
                related_links=related_links,
                resolved_location=resolved_location,
            )

        if effective_location is None and live_query_requires_location(request.question):
            return self._location_request(request)

        try:
            live = (
                await self._nearby_records(effective_location, layers=layers)
                if effective_location is not None
                else await self.live_service.map_results(layers=layers)
            )
        except LiveDataUnavailable:
            live = LiveMapResponse(
                generated_at=datetime.now(UTC),
                results=[],
                unavailable_layers=list(layers),
                limitations=["Official live sources are currently unavailable."],
            )

        resolved_location = getattr(live, "resolved_location", None)
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
                resolved_location=resolved_location,
            )
            if partial is not None:
                return partial
            if resolved_location is not None:
                return AskResponse(
                    status=ResponseStatus.ANSWER,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.LIVE,
                    answer=answer,
                    resolved_location=resolved_location,
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=[
                        *live.limitations,
                        "No matching record is not a safety determination.",
                    ],
                    unavailable_layers=live.unavailable_layers,
                )
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

        if selected_request and selected_id is not None:
            shown = [item for item in live.results if item.result_id == selected_id]
            if not shown:
                return AskResponse(
                    status=ResponseStatus.ABSTENTION,
                    trace_id=uuid4().hex,
                    response_mode=ResponseMode.ABSTENTION,
                    answer=(
                        "The selected record is no longer present in the available official "
                        "layer. Refresh the map and open the related official source."
                    ),
                    reason_code=ReasonCode.LIVE_DATA_REQUIRED,
                    limitations=["A missing record is not a safety determination."],
                    unavailable_layers=live.unavailable_layers,
                )
        else:
            shown = live.results[:100]
        summary = "; ".join(
            f"{item.name or item.incident_number or item.result_id}: {item.status}"
            for item in shown[:5]
        )
        aggregate_freshness = aggregate_live_freshness(shown)
        assert aggregate_freshness is not None
        if aggregate_freshness == AggregateFreshness.STALE:
            live_label = "Cached official information (refresh failed): "
        elif aggregate_freshness == AggregateFreshness.MIXED:
            live_label = "Official information (includes stale cached records): "
        else:
            live_label = "Current official information: "
        live_answer = live_label + summary
        freshness_limitation = self._freshness_limitation(aggregate_freshness)
        live_limitations = self._unique_limitations(
            live.limitations,
            [freshness_limitation] if freshness_limitation else [],
        )
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
                aggregate_freshness=aggregate_freshness,
                limitations=self._unique_limitations(
                    live_limitations, static_result.limitations
                ),
                validation=static_result.validation,
                unavailable_layers=live.unavailable_layers,
                selected_live_result_id=selected_id if selected_request else None,
                resolved_location=resolved_location,
            )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.LIVE,
            answer=live_answer,
            live_results=shown,
            aggregate_freshness=aggregate_freshness,
            limitations=self._unique_limitations(
                live_limitations,
                [
                    *(
                        ["Unsupported live topics: " + ", ".join(unsupported_topics)]
                        if unsupported_topics
                        else []
                    ),
                ],
            ),
            unavailable_layers=live.unavailable_layers,
            selected_live_result_id=selected_id if selected_request else None,
            resolved_location=resolved_location,
        )
