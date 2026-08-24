"""Deterministic AskResponse composition from this turn's agent packet."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from firelens.agent.packet import AgentPacket
from firelens.answering.intent import live_layers_for_question
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_analysis import compose_official_answer
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
)
from firelens.answering.live_response_support import empty_live_response
from firelens.contracts import (
    AggregateFreshness,
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    QueryRequest,
    ReasonCode,
    RelatedLink,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
    render_claim_texts,
)
from firelens.publication.compiler import public_mixed_answer

_LAYER_UNAVAILABLE = (
    "Some official live layers were unavailable for this request. That is not an all-clear."
)
_STALE_RECORDS_LIMITATION = (
    "A live refresh failed; some official records shown are cached and may be outdated."
)


def safety_response(request: QueryRequest) -> AskResponse:
    del request
    answer = "FireLens cannot provide personalized safety advice or evacuation decisions."
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer=answer,
        reason_code=ReasonCode.PERSONALIZED_SAFETY_DECISION,
        limitations=[answer],
    )


def no_substitute_response(request: QueryRequest) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ABSTENTION,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.ABSTENTION,
        answer=(
            "Select a mapped fire or perimeter before asking about a specific record. "
            "FireLens will not substitute a different nearby record."
        ),
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        selected_live_result_id=request.context.selected_live_result_id,
        limitations=[
            "FireLens did not substitute a different nearby fire.",
            "FireLens did not substitute the nearest fire for an unbound reference.",
            "No matching record is not a safety determination.",
        ],
    )


def handoff_answer(packet: AgentPacket) -> str:
    topics = (
        ", ".join(packet.unknown_topics) if packet.unknown_topics else "that live information"
    )
    if packet.related_links:
        titles = ", ".join(link.title for link in packet.related_links)
        return (
            f"FireLens is not connected to an official live source for {topics}. "
            f"Open the related official service for the current value: {titles}."
        )
    return "FireLens is not connected to an official live source for that information."


def quoted_guidance_response(request: QueryRequest, packet: AgentPacket) -> AskResponse | None:
    """Keep reviewed alert/order definitions when Luna's prose trips the safety rail."""

    static = packet.static_response
    if (
        static is None
        or static.response_mode not in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
        or static.validation is None
        or not static.validation.accepted
        or not static.claims
        or not static.evidence
    ):
        return None
    answer = static.answer
    if not answer:
        return None
    return compose_response(request, packet, answer)


def compose_response(
    request: QueryRequest,
    packet: AgentPacket,
    answer: str,
) -> AskResponse:
    return _with_packet_fields(request, packet, _build_ask_response(request, packet, answer))


def _with_packet_fields(
    request: QueryRequest,
    packet: AgentPacket,
    response: AskResponse,
) -> AskResponse:
    updates: dict[str, Any] = {}
    limitations = list(response.limitations)
    if packet.unavailable_layers:
        updates["unavailable_layers"] = list(packet.unavailable_layers)
        if _LAYER_UNAVAILABLE not in limitations:
            limitations.append(_LAYER_UNAVAILABLE)
            updates["limitations"] = limitations
            # history_text embeds limitations; clear it so the contract
            # validator derives it again instead of serving a stale value
            # that fails response-model revalidation.
            updates["history_text"] = None
    if request.context.selected_live_result_id and not response.selected_live_result_id:
        updates["selected_live_result_id"] = request.context.selected_live_result_id
    if packet.resolved_location is not None and response.resolved_location is None:
        updates["resolved_location"] = packet.resolved_location
    if not updates:
        return response
    if "history_text" in updates:
        return AskResponse.model_validate(
            response.model_copy(update=updates).model_dump(mode="python")
        )
    return response.model_copy(update=updates)


def _missing_selected(request: QueryRequest, packet: AgentPacket) -> bool:
    if (
        "missing_selected_record" in packet.unknown_topics
        or "unbound_selected_record" in packet.unknown_topics
    ):
        return True
    selected_id = request.context.selected_live_result_id
    if not selected_id:
        return False
    if not (
        is_selected_live_request(request)
        or is_unsupported_selected_request(request)
        or is_distance_request(request)
    ):
        return False
    return not any(item.result_id == selected_id for item in packet.live_results)


def _records_heading(freshness: AggregateFreshness | None) -> str:
    if freshness in {AggregateFreshness.STALE, AggregateFreshness.MIXED}:
        return "Official records (cached; refresh failed)"
    return "Current official records"


def _live_limitations(
    freshness: AggregateFreshness | None, base: list[str] | None = None
) -> list[str]:
    limitations = list(base or [])
    if freshness in {AggregateFreshness.STALE, AggregateFreshness.MIXED}:
        limitations.append(_STALE_RECORDS_LIMITATION)
    return list(dict.fromkeys(limitations))


def _unresolved_place_response(request: QueryRequest) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.REQUIRES_INPUT,
        answer=(
            "FireLens could not match that place to a British Columbia community. "
            "Enter a BC community name (for example Kelowna or Prince George) or "
            "share an approximate location to continue."
        ),
        required_input=RequiredInput(
            kind=RequiredInputKind.LOCATION,
            prompt="Enter a BC community FireLens can look up.",
            continuation_question=request.question,
        ),
        selected_live_result_id=request.context.selected_live_result_id,
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        limitations=[
            "The place label did not resolve to a BC community, so no official "
            "records were fetched."
        ],
    )


def _out_of_province_response(packet: AgentPacket) -> AskResponse:
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=(
            "FireLens reads official British Columbia wildfire sources only, so it "
            "cannot report live records for places outside BC. Use that "
            "jurisdiction's official wildfire or emergency service for current "
            "conditions there."
        ),
        reason_code=ReasonCode.SCOPE_REDIRECT,
        related_links=packet.related_links,
        limitations=["FireLens covers official British Columbia layers only."],
    )


def _build_ask_response(
    request: QueryRequest,
    packet: AgentPacket,
    answer: str,
) -> AskResponse:
    static = packet.static_response
    live = packet.live_results
    links = packet.related_links
    if live and is_empty_map_safety_inference(request.question):
        # The false-inference correction is application-owned. A model may not
        # soften it or turn returned records into a personalized safety claim.
        answer = compose_official_answer(
            request,
            live,
            roster_total=packet.roster_total,
            static_answer=static.answer if static is not None else None,
        )
    if _missing_selected(request, packet):
        return no_substitute_response(request)
    if not live and static is None and not links:
        if "unresolved_place" in packet.unknown_topics:
            return _unresolved_place_response(request)
        if "out_of_province_place" in packet.unknown_topics:
            return _out_of_province_response(packet)
        requested_layers = live_layers_for_question(request.question)
        if requested_layers:
            empty = empty_live_response(
                requested_layers=requested_layers,
                unavailable_layers=packet.unavailable_layers,
                resolved_location=packet.resolved_location,
            )
            if "named_fire_not_found" in packet.unknown_topics:
                specific = (
                    answer
                    + " No unrelated nearby record was substituted. This is not an all-clear."
                )
                sections = list(empty.answer_sections)
                if sections:
                    sections[0] = sections[0].model_copy(update={"text": specific})
                handoff = sections[1].text if len(sections) > 1 else ""
                return AskResponse.model_validate(
                    empty.model_copy(
                        update={
                            "answer": specific
                            + (
                                f"\n\nRelated official information: {handoff}"
                                if handoff
                                else ""
                            ),
                            "answer_sections": sections,
                            # The contract derives bounded history from the public
                            # answer. Clear the prior empty-result rendering whenever
                            # the named-fire wording changes.
                            "history_text": None,
                        }
                    ).model_dump(mode="python")
                )
            return empty
    if is_unsupported_selected_request(request) and live:
        selected_id = request.context.selected_live_result_id
        selected = next((item for item in live if item.result_id == selected_id), None)
        if selected is None:
            return no_substitute_response(request)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=answer,
            reason_code=ReasonCode.SCOPE_REDIRECT,
            limitations=[
                "FireLens did not infer a cause or prediction that the selected record does not state."
            ],
            related_links=[
                RelatedLink(
                    title="Selected official record",
                    url=selected.source_url,
                    description="Official source for the selected wildfire record.",
                )
            ],
            selected_live_result_id=selected.result_id,
        )
    if (
        live
        and static is not None
        and static.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
        and static.claims
        and static.evidence
        and static.validation is not None
        and static.validation.accepted
    ):
        freshness = aggregate_live_freshness(live)
        answer = public_mixed_answer(packet, answer)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static.trace_id,
            response_mode=ResponseMode.MIXED,
            answer=answer,
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading=_records_heading(freshness),
                    text=answer,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                    heading="Reviewed preparedness guidance",
                    text=render_claim_texts(static.claims),
                ),
            ],
            claims=static.claims,
            evidence=static.evidence,
            live_results=live,
            aggregate_freshness=freshness,
            limitations=_live_limitations(freshness, list(static.limitations)),
            validation=static.validation,
            selected_live_result_id=request.context.selected_live_result_id,
            resolved_location=packet.resolved_location,
        )
    if live and links:
        freshness = aggregate_live_freshness(live)
        handoff = handoff_answer(packet)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.MIXED,
            answer=f"{answer}\n\nRelated official information: {handoff}",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading=_records_heading(freshness),
                    text=answer,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.OFFICIAL_HANDOFF,
                    heading="Related official information",
                    text=handoff,
                ),
            ],
            live_results=live,
            aggregate_freshness=freshness,
            related_links=links,
            resolved_location=packet.resolved_location,
            selected_live_result_id=request.context.selected_live_result_id,
            limitations=_live_limitations(
                freshness,
                ["This uses official records and is not a safety assessment."],
            ),
        )
    if live:
        freshness = aggregate_live_freshness(live)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.LIVE,
            answer=answer,
            live_results=live,
            aggregate_freshness=freshness,
            selected_live_result_id=request.context.selected_live_result_id,
            resolved_location=packet.resolved_location,
            limitations=_live_limitations(
                freshness,
                ["This uses official records and is not a safety assessment."],
            ),
        )
    if static is not None and links:
        topics = [topic for topic in packet.unknown_topics if topic != "prediction"]
        merged = supported_static_when_live_missing(
            static,
            handoff_answer(packet),
            limitations=[
                "Unsupported live topics: " + ", ".join(topics)
                if topics
                else "FireLens did not invent a live feed it does not ingest."
            ],
            related_links=links,
            resolved_location=packet.resolved_location,
        )
        if merged is not None:
            return merged
    if static is not None:
        if (
            not live
            and "out_of_province_place" in packet.unknown_topics
            and static.status != ResponseStatus.ANSWER
        ):
            # A national or out-of-province live ask found no reviewed answer
            # either; the honest response is the BC-only scope redirect.
            return _out_of_province_response(packet)
        updates: dict[str, Any] = {}
        if request.context.selected_live_result_id and not static.selected_live_result_id:
            updates["selected_live_result_id"] = request.context.selected_live_result_id
        if packet.resolved_location is not None and static.resolved_location is None:
            updates["resolved_location"] = packet.resolved_location
        return static.model_copy(update=updates) if updates else static
    if links:
        handoff = handoff_answer(packet)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=handoff,
            reason_code=ReasonCode.SCOPE_REDIRECT,
            related_links=links,
            resolved_location=packet.resolved_location,
            limitations=["FireLens did not invent a live feed it does not ingest."],
        )
    # Terminal branch: nothing grounded this turn. Never publish free model
    # prose here; the reader gets a deterministic, honest redirect instead.
    if packet.unavailable_layers:
        terminal_answer = (
            "The official live layers needed for this request were unavailable, so "
            "FireLens cannot report current records this turn. That is not an "
            "all-clear; try again shortly or check the official BC Wildfire "
            "Service map."
        )
    else:
        terminal_answer = (
            "That question is outside the grounded sources FireLens reads. "
            "FireLens can report official BC wildfire records — active fires, "
            "perimeters, and fire-related evacuation orders and alerts — and "
            "reviewed preparedness guidance."
        )
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.SCOPE_REDIRECT,
        answer=terminal_answer,
        reason_code=ReasonCode.SCOPE_REDIRECT,
        limitations=["No official record or reviewed passage supported a typed claim."],
    )
