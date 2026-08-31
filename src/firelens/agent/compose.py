"""Deterministic AskResponse composition from this turn's agent packet."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from firelens.agent.live_scope import packet_scope_limitations
from firelens.agent.live_selection import (
    selected_live_result_id,
    selected_official_handoff,
)
from firelens.agent.packet import AgentPacket
from firelens.answering.intent import live_layers_for_question
from firelens.answering.intent_safety import is_empty_map_safety_inference
from firelens.answering.live_analysis import (
    compose_official_answer,
    official_display_name,
)
from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.live_distance import distance_answer
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.live_request_intent import (
    is_distance_request,
    is_selected_live_request,
    is_unsupported_selected_request,
    selected_location_matches_record,
)
from firelens.answering.live_response_support import (
    empty_live_response,
    records_section_heading,
)
from firelens.contract_composition import canonical_live_or_mixed_answer
from firelens.contracts import (
    BACKGROUND_LIMITATION,
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

_STALE_RECORDS_LIMITATION = (
    "A live refresh failed; some official records shown are cached and may be outdated."
)


def _requested_live_layers(request: QueryRequest, packet: AgentPacket) -> tuple[Any, ...]:
    """Use the already-authorized plan rather than reclassifying at publication time."""

    plan = packet.query_plan
    if plan is not None:
        return tuple(plan.live_layers)
    return live_layers_for_question(request.question)


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
    degraded = "Official records loaded successfully. AI explanation is temporarily limited."
    if (
        packet.live_results
        and packet.policy.fallback_reason in {"provider_error", "rewrite_provider_error"}
        and degraded not in limitations
    ):
        limitations.append(degraded)
        updates["limitations"] = limitations
        updates["history_text"] = None
    if packet.unavailable_layers:
        updates["unavailable_layers"] = list(packet.unavailable_layers)
        names = ", ".join(
            dict.fromkeys(layer.value.replace("_", " ") for layer in packet.unavailable_layers)
        )
        layer_unavailable = (
            f"Some official layers are unavailable: {names}. That is not an all-clear."
        )
        if layer_unavailable not in limitations:
            limitations.append(layer_unavailable)
            updates["limitations"] = limitations
            updates["history_text"] = None
    scope_limitations = [*packet.live_limitations, *packet_scope_limitations(request, packet)]
    for limitation in scope_limitations:
        if limitation not in limitations:
            limitations.append(limitation)
            updates["limitations"] = limitations
            # `history_text` is a derived public-contract field. Any visible
            # limitation changes the answer history representation too.
            updates["history_text"] = None
    if request.context.selected_live_result_id and not response.selected_live_result_id:
        updates["selected_live_result_id"] = request.context.selected_live_result_id
    elif (
        not response.selected_live_result_id
        and len(packet.live_results) == 1
        and extracted_located_fire_name(request.question) is not None
    ):
        updates["selected_live_result_id"] = packet.live_results[0].result_id
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
    return not any(
        item.result_id == selected_id for item in packet.live_results
    ) or not selected_location_matches_record(request, packet.live_results)


def _packet_live_answer(
    request: QueryRequest,
    packet: AgentPacket,
    *,
    static_answer: str | None = None,
) -> str:
    """Compose live text without turning an unavailable layer into a zero result."""

    if packet.live_results and packet.unavailable_layers:
        unavailable = [layer.value.replace("_", " ") for layer in packet.unavailable_layers]
        names = (
            unavailable[0]
            if len(unavailable) == 1
            else ", ".join(unavailable[:-1]) + f" and {unavailable[-1]}"
        )
        layer_label = "layer was" if len(unavailable) == 1 else "layers were"
        summary = "; ".join(
            f"{official_display_name(item)}: {item.status}" for item in packet.live_results[:8]
        )
        return (
            f"FireLens could not verify {names} records because the official {names} "
            f"{layer_label} unavailable. Available official records in this response: "
            f"{summary}."
        )
    return compose_official_answer(
        request,
        packet.live_results,
        roster_total=packet.roster_total,
        static_answer=static_answer,
    )


def _published_live_text(
    request: QueryRequest,
    packet: AgentPacket,
    *,
    static_answer: str | None = None,
) -> str:
    if is_distance_request(request) and packet.live_results:
        composed = distance_answer(request, packet.live_results)
        if composed:
            return composed
    return _packet_live_answer(request, packet, static_answer=static_answer)


def _live_limitations(
    freshness: AggregateFreshness | None, base: list[str] | None = None
) -> list[str]:
    limitations = list(base or [])
    if freshness in {AggregateFreshness.STALE, AggregateFreshness.MIXED}:
        limitations.append(_STALE_RECORDS_LIMITATION)
    return list(dict.fromkeys(limitations))


def _unestablished_static_limitations(packet: AgentPacket) -> list[str]:
    static = packet.static_response
    established_modes = {
        ResponseMode.GROUNDED,
        ResponseMode.PARTIAL,
        ResponseMode.CONFLICT,
        ResponseMode.BACKGROUND,
    }
    if static is None or (
        static.response_mode in established_modes
        and static.claims
        and static.validation is not None
        and static.validation.accepted
    ):
        return []
    return [
        "The requested non-live clause was not established from reviewed FireLens "
        "evidence and was not silently replaced."
    ]


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
    selected_handoff = selected_official_handoff(request, live)
    links = list(packet.related_links)
    if selected_handoff is not None and all(
        str(link.url) != str(selected_handoff.url) for link in links
    ):
        links.insert(0, selected_handoff)
    if live and (packet.unavailable_layers or is_empty_map_safety_inference(request.question)):
        # The false-inference correction is application-owned. A model may not
        # soften it or turn returned records into a personalized safety claim.
        answer = _packet_live_answer(
            request,
            packet,
            static_answer=static.answer if static is not None else None,
        )
    if _missing_selected(request, packet):
        return no_substitute_response(request)
    if not live and static is None and not links:
        if "unresolved_place" in packet.unknown_topics:
            return _unresolved_place_response(request)
        if "out_of_province_place" in packet.unknown_topics:
            return _out_of_province_response(packet)
        requested_layers = _requested_live_layers(request, packet)
        if requested_layers:
            empty = empty_live_response(
                requested_layers=requested_layers,
                unavailable_layers=packet.unavailable_layers,
                resolved_location=packet.resolved_location,
                retrieved_at=packet.retrieved_at,
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
            answer=_published_live_text(request, packet),
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
        and static.response_mode == ResponseMode.BACKGROUND
        and static.claims
        and not static.evidence
        and static.validation is not None
        and static.validation.accepted
    ):
        freshness = aggregate_live_freshness(live)
        live_text = _published_live_text(
            request,
            packet,
            static_answer=None,
        )
        background_text = render_claim_texts(static.claims)
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static.trace_id,
            response_mode=ResponseMode.MIXED,
            answer=f"{live_text}\n\nGeneral background: {background_text}",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading=records_section_heading(freshness),
                    text=live_text,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.GENERAL_BACKGROUND,
                    heading="General background",
                    text=background_text,
                ),
            ],
            claims=static.claims,
            evidence=[],
            live_results=live,
            aggregate_freshness=freshness,
            limitations=_live_limitations(
                freshness,
                [*static.limitations, BACKGROUND_LIMITATION],
            ),
            validation=static.validation,
            selected_live_result_id=selected_live_result_id(request, live),
            resolved_location=packet.resolved_location,
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
        live_text = _published_live_text(
            request,
            packet,
            static_answer=None,
        )
        guidance = render_claim_texts(static.claims)
        sections = [
            AnswerSection(
                kind=AnswerSectionKind.CURRENT_RECORDS,
                heading=records_section_heading(freshness),
                text=live_text,
            ),
            AnswerSection(
                kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                heading="Reviewed preparedness guidance",
                text=guidance,
            ),
        ]
        answer = (
            canonical_live_or_mixed_answer(
                [(section.kind.value, section.text) for section in sections]
            )
            or live_text
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static.trace_id,
            response_mode=ResponseMode.MIXED,
            answer=answer,
            answer_sections=sections,
            claims=static.claims,
            evidence=static.evidence,
            live_results=live,
            aggregate_freshness=freshness,
            limitations=_live_limitations(freshness, list(static.limitations)),
            validation=static.validation,
            selected_live_result_id=selected_live_result_id(request, live),
            resolved_location=packet.resolved_location,
        )
    if live and links:
        freshness = aggregate_live_freshness(live)
        live_text = _published_live_text(request, packet)
        handoff = (
            "Open the selected official record for its official source details and "
            "published source-update timestamp: Selected official record."
            if selected_handoff is not None
            else handoff_answer(packet)
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=uuid4().hex,
            response_mode=ResponseMode.MIXED,
            answer=f"{live_text}\n\nRelated official information: {handoff}",
            answer_sections=[
                AnswerSection(
                    kind=AnswerSectionKind.CURRENT_RECORDS,
                    heading=records_section_heading(freshness),
                    text=live_text,
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
            selected_live_result_id=selected_live_result_id(request, live),
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
            answer=_published_live_text(request, packet),
            live_results=live,
            aggregate_freshness=freshness,
            selected_live_result_id=selected_live_result_id(request, live),
            resolved_location=packet.resolved_location,
            limitations=_live_limitations(
                freshness,
                [
                    "This uses official records and is not a safety assessment.",
                    *_unestablished_static_limitations(packet),
                ],
            ),
        )
    if static is not None and not live:
        requested = _requested_live_layers(request, packet)
        if requested:
            empty = empty_live_response(
                requested_layers=requested,
                unavailable_layers=packet.unavailable_layers,
                resolved_location=packet.resolved_location,
                retrieved_at=packet.retrieved_at,
            )
            current = (
                empty.answer_sections[0].text if empty.answer_sections else (empty.answer or "")
            )
            merged = supported_static_when_live_missing(
                static,
                current,
                limitations=list(empty.limitations),
                unavailable_layers=list(packet.unavailable_layers),
                related_links=list(empty.related_links) or list(links),
                resolved_location=packet.resolved_location,
            )
            if merged is not None:
                return merged
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
    if static is not None and not links:
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
