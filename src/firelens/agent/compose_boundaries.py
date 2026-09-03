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
    """Append the turn's boundary sections to an answered live or mixed response.

    The records (or their absence) open the answer; each boundary follows under
    its own label. Only ANSWER-status responses carry them: a clarification or a
    scope redirect already speaks for the whole turn.
    """

    present = {section.kind for section in response.answer_sections}
    boundaries = [section for section in packet.boundaries if section.kind not in present]
    if not boundaries or response.status != ResponseStatus.ANSWER or not response.answer:
        return response
    if response.response_mode not in {ResponseMode.LIVE, ResponseMode.MIXED}:
        return response
    sections = list(response.answer_sections) or [_opening_section(response, response.answer)]
    sections.extend(boundaries)
    answer = canonical_live_or_mixed_answer(
        [(section.kind.value, section.text) for section in sections]
    )
    if answer is None:
        return response
    limitations = list(response.limitations)
    links = list(response.related_links)
    mode = response.response_mode
    for section in boundaries:
        if section.kind == AnswerSectionKind.SAFETY_BOUNDARY:
            limitations.append(SAFETY_BOUNDARY_LIMITATION)
            links.extend(link for link in official_safety_links() if link not in links)
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
