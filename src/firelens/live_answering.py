"""Application coordination for official live and mixed answers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from firelens.answering.intent import (
    live_layers_for_question,
    live_query_requires_location,
    unsupported_live_topics,
)
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.live_distance import location_request
from firelens.answering.live_handoffs import (
    merge_related_links,
    related_live_links,
    unsupported_live_no_result_response,
)
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
    render_live_record_answer,
)
from firelens.answering.live_response_support import (
    freshness_limitation,
    records_section_heading,
    unique_limitations,
)
from firelens.answering.live_static_request import extract_static_request
from firelens.answering.location_intent import coarse_location_from_question
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    PUBLIC_ANSWER_MAX_CHARS,
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    CoarseResolvedLocation,
    LiveMapResponse,
    LiveResultKind,
    LocationInput,
    NearMeResponse,
    QueryPlan,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
    render_claim_texts,
)
from firelens.live import LiveDataService, LiveDataUnavailable


def _section(kind: AnswerSectionKind, heading: str, text: str) -> AnswerSection:
    return AnswerSection(kind=kind, heading=heading, text=text)


class LiveAnswerCoordinator:
    """Own live-source policy and composition independently from HTTP transport."""

    def __init__(self, live_service: LiveDataService) -> None:
        self.live_service = live_service

    is_distance_request = staticmethod(is_distance_request)
    is_selected_live_request = staticmethod(is_selected_live_request)
    is_unsupported_selected_request = staticmethod(is_unsupported_selected_request)

    def handles(self, request: QueryRequest) -> bool:
        """Return whether this bounded coordinator owns the request."""
        from firelens.answering.intent import plan_query

        plan = plan_query(request)
        layers = live_layers_for_question(request.question)
        if plan.route == QueryRoute.PROHIBITED:
            return bool(
                plan.boundary_reason == ReasonCode.PERSONALIZED_SAFETY_DECISION
                and unsupported_live_topics(request.question)
                and not layers
            )
        return (
            self.is_distance_request(request)
            or self.is_selected_live_request(request)
            or self.is_unsupported_selected_request(request)
            or plan.route == QueryRoute.LIVE
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

    async def _prohibited_live_handoff(
        self,
        request: QueryRequest,
        plan: QueryPlan,
    ) -> AskResponse:
        topics = unsupported_live_topics(request.question)
        links = related_live_links(topics)
        location = request.location or coarse_location_from_question(request.question)
        resolved_location: CoarseResolvedLocation | None = None
        if location is not None and links:
            try:
                latitude, longitude = await self.live_service.resolve_location(location)
            except LiveDataUnavailable:
                pass
            else:
                resolved_location = CoarseResolvedLocation(
                    latitude=latitude,
                    longitude=longitude,
                )
        boundary = (
            plan.limitations[0]
            if plan.limitations
            else "FireLens cannot provide this personalized safety decision."
        )
        handoff = (
            "Open the linked official service for current " + ", ".join(topics) + "."
            if links
            else "Use the responsible emergency authority for current direction."
        )
        sections = [_section(AnswerSectionKind.UNCERTAINTY, "Safety boundary", boundary)]
        if links:
            sections.append(
                _section(
                    AnswerSectionKind.OFFICIAL_HANDOFF, "Related official information", handoff
                )
            )
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.ABSTENTION,
            answer=boundary + " " + handoff,
            answer_sections=sections,
            reason_code=(plan.boundary_reason or ReasonCode.PERSONALIZED_SAFETY_DECISION),
            limitations=plan.limitations or [boundary],
            related_links=links,
            resolved_location=resolved_location,
        )

    static_request = staticmethod(extract_static_request)

    async def answer(
        self, request: QueryRequest, static_result: AskResponse | None
    ) -> AskResponse:
        """Legacy live composer. Public Ask uses FireLensAgent, not this method."""
        from firelens.answering.intent import plan_query

        plan = plan_query(request)
        if plan.route == QueryRoute.PROHIBITED:
            return await self._prohibited_live_handoff(request, plan)
        layers = live_layers_for_question(request.question)
        effective_location = request.location or coarse_location_from_question(request.question)
        selected_request = self.is_selected_live_request(request)
        unsupported_selected_request = self.is_unsupported_selected_request(request)
        selected_context_request = selected_request or unsupported_selected_request
        selected_id = request.context.selected_live_result_id
        if not layers and selected_context_request and selected_id is not None:
            selected_kind = selected_id.partition(":")[0]
            layers = {
                "incident": (LiveResultKind.INCIDENT,),
                "perimeter": (LiveResultKind.PERIMETER,),
                "evacuation": (LiveResultKind.EVACUATION,),
            }.get(selected_kind, ())
        unsupported_topics = unsupported_live_topics(request.question)
        unsupported_links = related_live_links(unsupported_topics)
        if not layers:
            topics = ", ".join(unsupported_topics) or "that live information"
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
            partial = supported_static_when_live_missing(
                static_result,
                current_gap,
                limitations=[
                    "No matching record is not a safety determination.",
                    f"Unsupported live topics: {topics}",
                ],
                related_links=unsupported_links,
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
                related_links=unsupported_links,
                resolved_location=resolved_location,
            )
        if (
            effective_location is None
            and live_query_requires_location(request.question)
            and not unsupported_selected_request
        ):
            return location_request(request)
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
            partial = supported_static_when_live_missing(
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
                related_links=unsupported_links,
                resolved_location=resolved_location,
            )
            if partial is not None:
                return partial
            if unsupported_links:
                limitations = unique_limitations(
                    live.limitations,
                    [
                        "No matching record is not a safety determination.",
                        "Unsupported live topics: " + ", ".join(unsupported_topics),
                    ],
                )
                return unsupported_live_no_result_response(
                    current_information=answer,
                    topics=unsupported_topics,
                    links=unsupported_links,
                    limitations=limitations,
                    unavailable_layers=live.unavailable_layers,
                    resolved_location=resolved_location,
                )
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

        if selected_context_request and selected_id is not None:
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
        if unsupported_selected_request:
            selected = shown[0]
            selected_kind = {
                LiveResultKind.INCIDENT: "wildfire incident record",
                LiveResultKind.PERIMETER: "wildfire perimeter record",
                LiveResultKind.EVACUATION: "evacuation record",
            }[selected.kind]
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=uuid4().hex,
                response_mode=ResponseMode.SCOPE_REDIRECT,
                answer=(
                    "The selected official record does not contain the fields needed to "
                    "answer that causal or predictive question. Open the selected official "
                    "record for the fields its publishing authority provides."
                ),
                reason_code=ReasonCode.SCOPE_REDIRECT,
                limitations=[
                    "FireLens did not infer a cause or prediction that the selected record does not state."
                ],
                related_links=[
                    RelatedLink(
                        title=f"Selected official {selected_kind}",
                        url=selected.source_url,
                        description=(
                            f"Official {selected.authority} source for the selected "
                            f"{selected_kind}."
                        )[:240].rstrip(),
                    )
                ],
                selected_live_result_id=selected.result_id,
            )
        aggregate_freshness = aggregate_live_freshness(shown)
        assert aggregate_freshness is not None
        live_answer = render_live_record_answer(request, shown, aggregate_freshness)
        freshness_note = freshness_limitation(aggregate_freshness)
        live_limitations = unique_limitations(
            live.limitations,
            [freshness_note] if freshness_note else [],
        )
        unsupported_handoff = (
            "FireLens is not connected to an official live source for "
            + ", ".join(unsupported_topics)
            + ". Open the linked official service for the current value."
            if unsupported_links
            else ""
        )
        unsupported_suffix = (
            "\n\nRelated official information: " + unsupported_handoff
            if unsupported_handoff
            else ""
        )
        unsupported_sections = (
            [
                _section(
                    AnswerSectionKind.OFFICIAL_HANDOFF,
                    "Related official information",
                    unsupported_handoff,
                )
            ]
            if unsupported_handoff
            else []
        )
        unsupported_limitations = (
            ["Unsupported live topics: " + ", ".join(unsupported_topics)]
            if unsupported_topics
            else []
        )
        if (
            static_result is not None
            and static_result.status == ResponseStatus.ANSWER
            and static_result.response_mode == ResponseMode.CONFLICT
            and static_result.answer
            and static_result.claims
            and static_result.evidence
            and static_result.validation is not None
            and static_result.validation.accepted
        ):
            conflict_text = static_result.answer
            composed_answer = (
                live_answer
                + "\n\nConflicting reviewed sources: "
                + conflict_text
                + unsupported_suffix
            )
            conflict_bound_limitations: list[str] = []
            if len(composed_answer) > PUBLIC_ANSWER_MAX_CHARS:
                conflict_text = (
                    "Reviewed sources conflict, so FireLens cannot combine them into one "
                    "apparently certain answer. Inspect both reviewed sources before acting."
                )
                composed_answer = (
                    live_answer
                    + "\n\nConflicting reviewed sources: "
                    + conflict_text
                    + unsupported_suffix
                )
                conflict_bound_limitations.append(
                    "The conflict summary was shortened to stay within the bounded public "
                    "response contract; the conflicting claims and evidence remain available."
                )
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=static_result.trace_id,
                response_mode=ResponseMode.MIXED,
                answer=composed_answer,
                answer_sections=[
                    _section(
                        AnswerSectionKind.CURRENT_RECORDS,
                        records_section_heading(aggregate_freshness),
                        live_answer,
                    ),
                    _section(
                        AnswerSectionKind.CONFLICTING_GUIDANCE,
                        "Conflicting reviewed sources",
                        conflict_text,
                    ),
                    *unsupported_sections,
                ],
                claims=static_result.claims,
                evidence=static_result.evidence,
                live_results=shown,
                aggregate_freshness=aggregate_freshness,
                limitations=unique_limitations(
                    live_limitations,
                    static_result.limitations,
                    unsupported_limitations,
                    conflict_bound_limitations,
                ),
                related_links=unsupported_links,
                reason_code=ReasonCode.CONFLICTING_EVIDENCE,
                validation=static_result.validation,
                unavailable_layers=live.unavailable_layers,
                selected_live_result_id=selected_id if selected_request else None,
                resolved_location=resolved_location,
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
            static_text = render_claim_texts(static_result.claims)
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=static_result.trace_id,
                response_mode=ResponseMode.MIXED,
                answer=(
                    live_answer
                    + "\n\nPreparedness guidance: "
                    + static_text
                    + unsupported_suffix
                ),
                answer_sections=[
                    _section(
                        AnswerSectionKind.CURRENT_RECORDS,
                        records_section_heading(aggregate_freshness),
                        live_answer,
                    ),
                    _section(
                        AnswerSectionKind.REVIEWED_GUIDANCE,
                        "Reviewed preparedness guidance",
                        static_text,
                    ),
                    *unsupported_sections,
                ],
                claims=static_result.claims,
                evidence=static_result.evidence,
                live_results=shown,
                aggregate_freshness=aggregate_freshness,
                limitations=unique_limitations(
                    live_limitations,
                    static_result.limitations,
                    unsupported_limitations,
                ),
                related_links=unsupported_links,
                validation=static_result.validation,
                unavailable_layers=live.unavailable_layers,
                selected_live_result_id=selected_id if selected_request else None,
                resolved_location=resolved_location,
            )
        if (
            static_result is not None
            and static_result.status == ResponseStatus.ANSWER
            and static_result.response_mode == ResponseMode.BACKGROUND
            and static_result.answer
            and static_result.claims
            and static_result.validation is not None
            and static_result.validation.accepted
        ):
            static_text = render_claim_texts(static_result.claims)
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=static_result.trace_id,
                response_mode=ResponseMode.MIXED,
                answer=(
                    live_answer + "\n\nGeneral background: " + static_text + unsupported_suffix
                ),
                answer_sections=[
                    _section(
                        AnswerSectionKind.CURRENT_RECORDS,
                        records_section_heading(aggregate_freshness),
                        live_answer,
                    ),
                    _section(
                        AnswerSectionKind.GENERAL_BACKGROUND, "General background", static_text
                    ),
                    *unsupported_sections,
                ],
                claims=static_result.claims,
                live_results=shown,
                aggregate_freshness=aggregate_freshness,
                limitations=unique_limitations(
                    live_limitations,
                    [BACKGROUND_LIMITATION],
                    static_result.limitations,
                    unsupported_limitations,
                ),
                related_links=unsupported_links,
                validation=static_result.validation,
                unavailable_layers=live.unavailable_layers,
                selected_live_result_id=selected_id if selected_request else None,
                resolved_location=resolved_location,
            )
        if (
            static_result is not None
            and static_result.status == ResponseStatus.ANSWER
            and static_result.response_mode == ResponseMode.SCOPE_REDIRECT
            and static_result.answer
            and static_result.related_links
        ):
            handoff = static_result.answer + (
                "\n\n" + unsupported_handoff if unsupported_handoff else ""
            )
            handoff_links = merge_related_links(
                live_handoff_links=unsupported_links,
                static_handoff_links=static_result.related_links,
            )
            handoff_limitations: list[str] = []
            composed_answer = live_answer + "\n\nRelated official information: " + handoff
            if len(composed_answer) > PUBLIC_ANSWER_MAX_CHARS:
                handoff = (
                    "FireLens found related official sources for the non-live part of this "
                    "question. Open the links below for the official information."
                )
                if unsupported_handoff:
                    handoff += "\n\n" + unsupported_handoff
                composed_answer = live_answer + "\n\nRelated official information: " + handoff
                handoff_limitations.append(
                    "The related-source handoff was shortened to stay within the bounded "
                    "public response contract."
                )
            return AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id=static_result.trace_id,
                response_mode=ResponseMode.MIXED,
                answer=composed_answer,
                answer_sections=[
                    _section(
                        AnswerSectionKind.CURRENT_RECORDS,
                        records_section_heading(aggregate_freshness),
                        live_answer,
                    ),
                    _section(
                        AnswerSectionKind.OFFICIAL_HANDOFF,
                        "Related official information",
                        handoff,
                    ),
                ],
                related_links=handoff_links,
                live_results=shown,
                aggregate_freshness=aggregate_freshness,
                limitations=unique_limitations(
                    live_limitations,
                    static_result.limitations,
                    unsupported_limitations,
                    handoff_limitations,
                ),
                unavailable_layers=live.unavailable_layers,
                selected_live_result_id=selected_id if selected_request else None,
                resolved_location=resolved_location,
            )
        unresolved_static = []
        if static_result is not None:
            unresolved_static = [
                "The non-live part of this question could not be established; it was not silently omitted."
            ]
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=(ResponseMode.MIXED if unsupported_links else ResponseMode.LIVE),
            answer=live_answer + unsupported_suffix,
            answer_sections=[
                _section(
                    AnswerSectionKind.CURRENT_RECORDS,
                    records_section_heading(aggregate_freshness),
                    live_answer,
                ),
                *unsupported_sections,
            ],
            live_results=shown,
            aggregate_freshness=aggregate_freshness,
            limitations=unique_limitations(
                live_limitations,
                [
                    *unresolved_static,
                    *unsupported_limitations,
                ],
            ),
            related_links=unsupported_links,
            unavailable_layers=live.unavailable_layers,
            selected_live_result_id=selected_id if selected_request else None,
            resolved_location=resolved_location,
        )
