"""PRESENT: give every declined or unavailable clause of a mixed turn its own section.

The plan marks the clauses FireLens will not or cannot answer (a personal
safety decision, a comparison with a past it holds no copy of). After the
records and guidance are composed, each such clause is appended under its own
label, so the person sees that the clause was heard and why it has no answer.
"""

from __future__ import annotations

from firelens.agent.packet import AgentPacket
from firelens.answering.clause_boundaries import (
    SAFETY_BOUNDARY_LIMITATION,
    UNAVAILABLE_LIMITATION,
)
from firelens.answering.live_handoffs import official_safety_links
from firelens.answering.live_response_support import records_section_heading
from firelens.contract_composition import canonical_live_or_mixed_answer
from firelens.contracts import (
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    ResponseMode,
    ResponseStatus,
)


def _opening_section(response: AskResponse, answer: str) -> AnswerSection:
    if response.live_results:
        return AnswerSection(
            kind=AnswerSectionKind.CURRENT_RECORDS,
            heading=records_section_heading(response.aggregate_freshness),
            text=answer,
        )
    return AnswerSection(
        kind=AnswerSectionKind.UNCERTAINTY,
        heading="What FireLens could establish",
        text=answer,
    )


def with_boundaries(response: AskResponse, packet: AgentPacket) -> AskResponse:
    """Compose executed records and guidance with their declined clauses."""

    return with_boundary_sections(response, packet.boundaries)


def with_boundary_sections(
    response: AskResponse, sections_to_add: tuple[AnswerSection, ...]
) -> AskResponse:
    """Retain declined clauses on both executed answers and terminal prompts.

    The records (or their absence) open the answer; each boundary follows under
    its own label. A location prompt must not erase an accompanying safety
    request; it has the same boundary contract without authorizing a lookup.
    """

    present = {section.kind for section in response.answer_sections}
    boundaries = [section for section in sections_to_add if section.kind not in present]
    if not boundaries or response.status != ResponseStatus.ANSWER or not response.answer:
        return response
    if response.response_mode not in {
        ResponseMode.GROUNDED,
        ResponseMode.LIVE,
        ResponseMode.MIXED,
        ResponseMode.PARTIAL,
        ResponseMode.REQUIRES_INPUT,
        ResponseMode.SCOPE_REDIRECT,
    }:
        return response
    sections = list(response.answer_sections) or [_opening_section(response, response.answer)]
    if (
        response.response_mode in {ResponseMode.GROUNDED, ResponseMode.PARTIAL}
        and not response.answer_sections
    ):
        sections = [
            AnswerSection(
                kind=AnswerSectionKind.UNCERTAINTY,
                heading="Publication limits",
                text=" ".join(response.limitations),
            ),
            AnswerSection(
                kind=AnswerSectionKind.REVIEWED_GUIDANCE,
                heading="Official source wording",
                text=response.answer,
            ),
        ]
    sections.extend(boundaries)
    answer = canonical_live_or_mixed_answer(
        [(section.kind.value, section.text) for section in sections]
    )
    if answer is None:
        return response
    limitations = list(response.limitations)
    links = list(response.related_links)
    mode = (
        ResponseMode.PARTIAL
        if response.response_mode == ResponseMode.GROUNDED
        else response.response_mode
    )
    for section in boundaries:
        if section.kind == AnswerSectionKind.SAFETY_BOUNDARY:
            limitations.append(SAFETY_BOUNDARY_LIMITATION)
            # The public envelope permits four links. Keep the safety handoff
            # first; every quoted source remains linked through its proof card.
            candidates = [*official_safety_links(), *links]
            links = list({str(link.url): link for link in reversed(candidates)}.values())[::-1][
                :4
            ]
            if response.live_results:
                mode = ResponseMode.MIXED
        elif section.kind == AnswerSectionKind.UNAVAILABLE:
            limitations.append(UNAVAILABLE_LIMITATION)
    return AskResponse.model_validate(
        response.model_copy(
            update={
                "answer": answer,
                "answer_sections": sections,
                "response_mode": mode,
                "limitations": list(dict.fromkeys(limitations)),
                "related_links": links,
                "history_text": None,
            }
        ).model_dump(mode="python")
    )
