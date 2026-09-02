"""Backend-owned presentation and provenance identity for one AskResponse."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from firelens.answering.live_sample import INLINE_SAMPLE_LIMIT, sample_record_ids
from firelens.live_contracts import LiveResultKind


class PresentationShell(StrEnum):
    CHAT = "chat"
    ANALYSIS = "analysis"
    SPATIAL = "spatial"
    PENDING = "pending"


class ProvenanceClass(StrEnum):
    OFFICIAL_LIVE = "official_live"
    REVIEWED_GUIDANCE = "reviewed_guidance"
    GENERAL_KNOWLEDGE = "general_knowledge"
    MIXED = "mixed"
    CLARIFICATION = "clarification"


class SuggestionOmissionReason(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    REFUSAL = "refusal"
    EMERGENCY_HANDOFF = "emergency_handoff"
    UNCLEAR_INPUT = "unclear_input"
    NO_SAFE_NEXT_STEP = "no_safe_next_step"
    NONE_REGISTERED = "none_registered"


def derive_provenance_class(response: Any) -> str:
    mode = getattr(getattr(response, "response_mode", None), "value", None) or str(
        getattr(response, "response_mode", "")
    )
    reason = getattr(getattr(response, "reason_code", None), "value", None) or (
        str(getattr(response, "reason_code", "") or "") or None
    )
    if reason in {"unclear_input", "missing_source_antecedent"}:
        return ProvenanceClass.CLARIFICATION
    if mode == "live":
        return ProvenanceClass.OFFICIAL_LIVE
    if mode in {"grounded", "partial", "conflict"}:
        return ProvenanceClass.REVIEWED_GUIDANCE
    if mode == "background":
        return ProvenanceClass.GENERAL_KNOWLEDGE
    if mode == "mixed":
        return ProvenanceClass.MIXED
    return ProvenanceClass.CLARIFICATION


def derive_presentation_shell(response: Any) -> str:
    mode = getattr(getattr(response, "response_mode", None), "value", None) or str(
        getattr(response, "response_mode", "")
    )
    if mode in {"requires_input", "abstention", "capability", "scope_redirect"}:
        return PresentationShell.CHAT
    if mode == "mixed":
        return PresentationShell.CHAT
    incidents = [
        item
        for item in getattr(response, "live_results", []) or []
        if getattr(item, "kind", None) == LiveResultKind.INCIDENT
    ]
    if getattr(response, "selected_live_result_id", None):
        return PresentationShell.CHAT
    if mode == "live" and getattr(response, "resolved_location", None) is not None:
        return PresentationShell.SPATIAL
    if mode == "live" and len(incidents) > 1:
        return PresentationShell.ANALYSIS
    return PresentationShell.CHAT


def derive_suggestion_omission(response: Any) -> str | None:
    if getattr(response, "suggested_questions", None):
        return None
    reason = getattr(getattr(response, "reason_code", None), "value", None) or (
        str(getattr(response, "reason_code", "") or "") or None
    )
    mode = getattr(getattr(response, "response_mode", None), "value", None) or str(
        getattr(response, "response_mode", "")
    )
    if reason == "unclear_input":
        return SuggestionOmissionReason.UNCLEAR_INPUT
    if reason in {
        "personalized_safety_decision",
        "personalized_medical_advice",
        "policy_manipulation",
    }:
        return SuggestionOmissionReason.REFUSAL
    if mode in {"scope_redirect", "abstention"}:
        return SuggestionOmissionReason.EMERGENCY_HANDOFF
    if mode == "requires_input":
        return SuggestionOmissionReason.UNCLEAR_INPUT
    return SuggestionOmissionReason.NONE_REGISTERED


def attach_result_identity(response: Any) -> None:
    """Fill public result-set and presentation fields from owned response data."""

    live = list(getattr(response, "live_results", []) or [])
    if not getattr(response, "requested_layers", None) and live:
        response.requested_layers = list(dict.fromkeys(item.kind for item in live))
    if getattr(response, "roster_total", None) is None and live:
        response.roster_total = len(live)
    if not getattr(response, "sample_record_ids", None) and live:
        response.sample_record_ids = sample_record_ids(live, limit=INLINE_SAMPLE_LIMIT)
    response.provenance_class = derive_provenance_class(response)
    response.presentation_shell = derive_presentation_shell(response)
    if (
        not getattr(response, "suggested_questions", None)
        and getattr(response, "suggestion_omission_reason", None) is None
    ):
        response.suggestion_omission_reason = derive_suggestion_omission(response)
