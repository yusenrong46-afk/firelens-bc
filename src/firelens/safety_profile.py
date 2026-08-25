"""Compatibility adapter for Safety Profile v1.0 truth classes and publication states.

Existing PublicationKind, EvidenceStatus, and SupportState remain authoritative.
This module only derives profile metadata; it never lets model text assign or
elevate a publication state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class TruthClass(StrEnum):
    SOURCE_FACT = "source_fact"
    DETERMINISTIC_DERIVATION = "deterministic_derivation"
    MODEL_SUMMARY = "model_summary"
    UNKNOWN = "unknown"


class PublicationState(StrEnum):
    VERIFIED = "verified"
    REVIEW = "review"
    REJECTED = "rejected"


_ALLOWED_FRESHNESS_VALUES = frozenset({"fresh", "stale"})


def freshness_token(freshness: Any) -> str | None:
    """Return an allowlisted freshness value after strip/casefold, or None.

    Suffix parsing is forbidden: ``stale.fresh`` and ``Freshness.FRESH`` are not
    exact allowlisted values and cannot be treated as fresh.
    """

    if freshness is None:
        return None
    raw = getattr(freshness, "value", freshness)
    token = str(raw).strip().casefold()
    if token in _ALLOWED_FRESHNESS_VALUES:
        return token
    return None


def live_freshness_is_explicitly_fresh(freshness: Any) -> bool:
    """Live VERIFIED requires an exact allowlisted fresh value, not a default."""

    return freshness_token(freshness) == "fresh"


def bind_proof_profile(
    support_state: str,
    *,
    rejected: bool = False,
    freshness: Any = None,
) -> tuple[TruthClass, PublicationState]:
    """Assign profile metadata from already-deterministic support state."""

    if rejected or support_state == "unknown":
        return TruthClass.UNKNOWN, PublicationState.REJECTED
    if support_state in {"structured_reviewed", "supported"}:
        return TruthClass.SOURCE_FACT, PublicationState.VERIFIED
    if support_state in {"official_live_typed", "live_record"}:
        if live_freshness_is_explicitly_fresh(freshness):
            return TruthClass.SOURCE_FACT, PublicationState.VERIFIED
        return TruthClass.SOURCE_FACT, PublicationState.REVIEW
    if support_state == "official_quote_only":
        return TruthClass.SOURCE_FACT, PublicationState.REVIEW
    if support_state in {"source_linked_explanation", "background"}:
        return TruthClass.MODEL_SUMMARY, PublicationState.REVIEW
    if support_state == "conflict":
        return TruthClass.SOURCE_FACT, PublicationState.REVIEW
    return TruthClass.UNKNOWN, PublicationState.REJECTED


def verified_critical_metadata_present(card: Any) -> bool:
    """Return whether a VERIFIED critical card carries required profile metadata."""

    if getattr(card, "publication_state", None) != PublicationState.VERIFIED:
        return True
    freshness = str(getattr(card, "freshness", "") or "").strip()
    authority = str(getattr(card, "authority", "") or "").strip()
    source = getattr(card, "official_url", None) or getattr(card, "exact_passage", None)
    truth = getattr(card, "truth_class", None)
    return bool(
        truth is not None
        and freshness
        and freshness.casefold() != "freshness not established"
        and authority
        and authority.casefold() != "authority not established"
        and source
    )
