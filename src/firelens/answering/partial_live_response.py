"""Legacy coordinator coverage composition using the shared deterministic owner."""

from uuid import uuid4

from firelens.answering.live_composition import supported_static_when_live_missing
from firelens.answering.live_response_support import empty_live_response, partial_records_answer
from firelens.contract_composition import canonical_live_or_mixed_answer
from firelens.contracts import (
    AnswerSection,
    AnswerSectionKind,
    AskResponse,
    LiveMapResponse,
    LiveResultKind,
    NearMeResponse,
    QueryRequest,
    ResponseMode,
    ResponseStatus,
    aggregate_live_freshness,
)


def partial_live_response(
    request: QueryRequest,
    live: LiveMapResponse | NearMeResponse,
    static: AskResponse | None,
    layers: tuple[LiveResultKind, ...],
) -> AskResponse:
    resolved = getattr(live, "resolved_location", None)
    records = list(live.results)
    if request.context.selected_live_result_id:
        records = [r for r in records if r.result_id == request.context.selected_live_result_id]
    empty = empty_live_response(
        requested_layers=layers,
        unavailable_layers=live.unavailable_layers,
        partial_layers=live.partial_layers,
        resolved_location=resolved,
        retrieved_at=live.generated_at,
        place=request.location.label if request.location else None,
    )
    text = (
        partial_records_answer(records, bool(live.unavailable_layers))
        if records
        else empty.answer
    )
    merged = supported_static_when_live_missing(
        static,
        text or "",
        limitations=list(live.limitations),
        unavailable_layers=live.unavailable_layers,
        related_links=empty.related_links,
        resolved_location=resolved,
    )
    if not records:
        base = merged or empty
        return AskResponse.model_validate(
            base.model_copy(
                update={
                    "partial_layers": live.partial_layers,
                    "selected_live_result_id": request.context.selected_live_result_id,
                    "roster_total": None,
                    "status_banner": empty.status_banner,
                    "history_text": None,
                }
            ).model_dump()
        )
    sections = [
        AnswerSection(
            kind=AnswerSectionKind.CURRENT_RECORDS,
            heading="Validated official records; incomplete coverage",
            text=text or "",
        )
    ]
    if merged:
        sections.extend(merged.answer_sections[1:])
    return AskResponse(
        status=ResponseStatus.ANSWER,
        trace_id=uuid4().hex,
        response_mode=ResponseMode.MIXED if merged and merged.claims else ResponseMode.LIVE,
        answer=canonical_live_or_mixed_answer([(s.kind.value, s.text) for s in sections]),
        answer_sections=sections,
        live_results=records,
        aggregate_freshness=aggregate_live_freshness(records),
        claims=merged.claims if merged else [],
        evidence=merged.evidence if merged else [],
        validation=merged.validation if merged else None,
        reason_code=merged.reason_code if merged else None,
        limitations=list(
            dict.fromkeys([*live.limitations, *(merged.limitations if merged else [])])
        ),
        partial_layers=live.partial_layers,
        unavailable_layers=live.unavailable_layers,
        related_links=empty.related_links,
        requested_layers=list(layers),
        selected_live_result_id=request.context.selected_live_result_id,
        resolved_location=resolved,
    )
