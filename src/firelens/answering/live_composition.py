"""Deterministic composition for partial live plus validated static answers."""

from __future__ import annotations

from firelens.answering.live_handoffs import merge_related_links
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    PUBLIC_ANSWER_MAX_CHARS,
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    CoarseResolvedLocation,
    LiveResultKind,
    ReasonCode,
    RelatedLink,
    ResponseMode,
    ResponseStatus,
    render_claim_texts,
)


def _unique_limitations(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))


def supported_static_when_live_missing(
    static_result: AskResponse | None,
    current_information: str,
    *,
    limitations: list[str],
    unavailable_layers: list[LiveResultKind] | None = None,
    related_links: list[RelatedLink] | None = None,
    resolved_location: CoarseResolvedLocation | None = None,
) -> AskResponse | None:
    """Retain accepted static content while marking the live half unavailable."""

    bounded_links = merge_related_links(
        live_handoff_links=related_links or [],
        static_handoff_links=[],
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
            "Current official information: "
            + current_information
            + "\n\nConflicting reviewed sources: "
            + conflict_text
        )
        bound_limitations: list[str] = []
        if len(composed_answer) > PUBLIC_ANSWER_MAX_CHARS:
            conflict_text = (
                "Reviewed sources conflict, so FireLens cannot combine them into one "
                "apparently certain answer. Inspect both reviewed sources before acting."
            )
            composed_answer = (
                "Current official information: "
                + current_information
                + "\n\nConflicting reviewed sources: "
                + conflict_text
            )
            bound_limitations.append(
                "The conflict summary was shortened to stay within the bounded public "
                "response contract; the conflicting claims and evidence remain available."
            )
        current_kind = (
            AnswerSectionKind.OFFICIAL_HANDOFF
            if bounded_links
            else AnswerSectionKind.UNCERTAINTY
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static_result.trace_id,
            response_mode=ResponseMode.CONFLICT,
            answer=composed_answer,
            answer_sections=[
                AnswerSection(
                    kind=current_kind,
                    heading=(
                        "Related official information"
                        if bounded_links
                        else "Current information unavailable"
                    ),
                    text=current_information,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.CONFLICTING_GUIDANCE,
                    heading="Conflicting reviewed sources",
                    text=conflict_text,
                ),
            ],
            claims=static_result.claims,
            evidence=static_result.evidence,
            limitations=_unique_limitations(
                limitations,
                static_result.limitations,
                bound_limitations,
            ),
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            validation=static_result.validation,
            unavailable_layers=unavailable_layers or [],
            related_links=bounded_links,
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
        current_kind = (
            AnswerSectionKind.OFFICIAL_HANDOFF
            if bounded_links
            else AnswerSectionKind.UNCERTAINTY
        )
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=static_result.trace_id,
            response_mode=ResponseMode.BACKGROUND,
            answer=(
                "Current official information: "
                + current_information
                + "\n\nGeneral background: "
                + static_text
            ),
            answer_sections=[
                AnswerSection(
                    kind=current_kind,
                    heading=(
                        "Related official information"
                        if bounded_links
                        else "Current information unavailable"
                    ),
                    text=current_information,
                ),
                AnswerSection(
                    kind=AnswerSectionKind.GENERAL_BACKGROUND,
                    heading="General background",
                    text=static_text,
                ),
            ],
            claims=static_result.claims,
            limitations=_unique_limitations(
                limitations,
                [BACKGROUND_LIMITATION],
                static_result.limitations,
            ),
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            validation=static_result.validation,
            unavailable_layers=unavailable_layers or [],
            related_links=bounded_links,
            resolved_location=resolved_location,
        )
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
    static_text = render_claim_texts(static_result.claims)
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=static_result.trace_id,
        response_mode=ResponseMode.PARTIAL,
        answer=(
            "Current official information: "
            + current_information
            + "\n\nPreparedness guidance: "
            + static_text
            + "\n\nUncertainty: the current-information part was not established."
        ),
        answer_sections=[
            AnswerSection(
                kind=(
                    AnswerSectionKind.OFFICIAL_HANDOFF
                    if bounded_links
                    else AnswerSectionKind.UNCERTAINTY
                ),
                heading=(
                    "Related official information"
                    if bounded_links
                    else "Current information unavailable"
                ),
                text=current_information,
            ),
            AnswerSection(
                kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                heading="Reviewed preparedness guidance",
                text=static_text,
            ),
        ],
        claims=static_result.claims,
        evidence=static_result.evidence,
        limitations=[*limitations, *static_result.limitations],
        reason_code=ReasonCode.LIVE_DATA_REQUIRED,
        validation=static_result.validation,
        unavailable_layers=unavailable_layers or [],
        related_links=bounded_links,
        resolved_location=resolved_location,
    )
