"""Internal normalization and identity binding for publication authority."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ValidationError

from firelens.publication_contracts import (
    LIVE_RENDERER_ID,
    PublicationAuthority,
    PublicationKind,
)

AuthoritySupportState = Literal[
    "structured_reviewed",
    "official_live_typed",
    "official_quote_only",
    "source_linked_explanation",
    "background",
    "unknown",
]

_KNOWN_PUBLICATION_KINDS = {kind.value for kind in PublicationKind}
_UNSUPPORTED_PUBLICATION = PublicationAuthority(kind=PublicationKind.UNSUPPORTED)
_KIND_SUPPORT_STATE: dict[str, AuthoritySupportState] = {
    PublicationKind.STRUCTURED_REVIEWED.value: "structured_reviewed",
    PublicationKind.OFFICIAL_LIVE_TYPED.value: "official_live_typed",
    PublicationKind.OFFICIAL_QUOTE_ONLY.value: "official_quote_only",
    PublicationKind.SOURCE_LINKED_EXPLANATION.value: "source_linked_explanation",
    PublicationKind.GENERAL_BACKGROUND.value: "background",
    PublicationKind.UNSUPPORTED.value: "unknown",
}


def _publication_kind(source: Any) -> str:
    publication = getattr(source, "publication", None)
    if publication is None:
        return ""
    kind = getattr(publication, "kind", publication)
    value = kind.value if hasattr(kind, "value") else str(kind)
    return value if value in _KNOWN_PUBLICATION_KINDS else ""


def _publication_support_state(source: Any) -> AuthoritySupportState:
    return _KIND_SUPPORT_STATE.get(_publication_kind(source), "unknown")


def _proof_card_publication_error(card: Any) -> str | None:
    publication = _bound_publication(card)
    support_state = getattr(card, "support_state", None)
    allowed_states: set[str] = {_KIND_SUPPORT_STATE[publication.kind.value]}
    if publication.kind == PublicationKind.OFFICIAL_LIVE_TYPED:
        allowed_states.add("live_record")
    if support_state not in allowed_states:
        return "proof card publication kind must match support state"
    if publication.kind != PublicationKind.OFFICIAL_LIVE_TYPED:
        return None

    derivation = getattr(card, "derivation", None)
    bound_ids = {
        str(source_id) for source_id in getattr(derivation, "input_source_ids", None) or []
    }
    live_id = str(publication.typed_live_fact_id)
    if bound_ids and live_id not in bound_ids:
        return "proof card typed live fact ID must match its bound card identity"
    return None


def _bound_publication(source: Any) -> PublicationAuthority:
    if source is None:
        return _UNSUPPORTED_PUBLICATION
    publication = (
        source
        if isinstance(source, PublicationAuthority)
        else getattr(source, "publication", source)
    )
    if publication is None:
        return _UNSUPPORTED_PUBLICATION
    if isinstance(publication, PublicationAuthority):
        return publication
    kind = getattr(publication, "kind", None)
    if kind is None:
        kind_value = ""
    elif hasattr(kind, "value"):
        kind_value = str(kind.value)
    else:
        kind_value = str(kind)
    if kind_value not in _KNOWN_PUBLICATION_KINDS:
        return _UNSUPPORTED_PUBLICATION
    try:
        if hasattr(publication, "model_dump"):
            return PublicationAuthority.model_validate(publication.model_dump())
        if isinstance(publication, dict):
            return PublicationAuthority.model_validate(publication)
        payload = {
            name: getattr(publication, name)
            for name in PublicationAuthority.model_fields
            if hasattr(publication, name)
        }
        return PublicationAuthority.model_validate(payload)
    except (ValidationError, TypeError, ValueError):
        return _UNSUPPORTED_PUBLICATION


def _live_publication(result: Any) -> PublicationAuthority:
    return PublicationAuthority(
        kind=PublicationKind.OFFICIAL_LIVE_TYPED,
        typed_live_fact_id=str(result.result_id),
        review_status="official_live_record",
        renderer_id=LIVE_RENDERER_ID,
        support_provenance="typed_official_live_fact",
        risk_tier="B",
    )


def _official_live_id_matches(card: Any, *, result: Any, claim: Any) -> bool:
    publication = _bound_publication(card)
    is_live_typed = (
        publication.kind == PublicationKind.OFFICIAL_LIVE_TYPED
        or getattr(card, "support_state", None) == "official_live_typed"
    )
    if not is_live_typed:
        return True
    bound_ids: set[str] = set()
    if result is not None:
        bound_ids.add(str(result.result_id))
    if claim is not None:
        bound_ids.add(str(claim.claim_id))
        claim_live_id = getattr(_bound_publication(claim), "typed_live_fact_id", None)
        if claim_live_id:
            bound_ids.add(str(claim_live_id))
    live_id = getattr(publication, "typed_live_fact_id", None)
    if live_id is not None:
        return str(live_id) in bound_ids
    return str(getattr(card, "claim_id", "")) in bound_ids
