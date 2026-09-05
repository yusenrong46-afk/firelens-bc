"""Provisional, unsealed diagnostics; not a replacement for frozen rc2.2.

These checks use public evidence and explicit fixture truth, not production
classification helpers. Passing them proves only the enumerated invariants.
"""

from __future__ import annotations

from typing import Any


def provenance_issues(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    evidence = {row["evidence_id"]: row for row in payload.get("evidence", [])}
    records = payload.get("live_results", [])
    label = (payload.get("status_banner") or {}).get("availability_label", "").lower()
    if not evidence and not records and not payload.get("requested_layers"):
        if "sources required for this request were available" in label:
            issues.append("unestablished_source_availability")
    claims = {row["claim_id"]: row for row in payload.get("claims", [])}
    for claim in claims.values():
        background = claim.get("evidence_status") == "general_background"
        for support in claim.get("supports", []):
            item = evidence.get(support.get("evidence_id"))
            if item is None:
                issues.append("missing_support_reference")
            elif not support.get("quote") or support["quote"] not in item.get(
                "primary_text", ""
            ):
                issues.append("unsupported_quote")
        if not background and not claim.get("supports"):
            # Structured claims have a separate typed authority contract.
            kind = (claim.get("publication") or {}).get("kind")
            if kind not in {"structured_reviewed", "official_live_typed"}:
                issues.append("claim_without_support")
    for card in payload.get("proof_cards", []):
        claim = claims.get(card.get("claim_id"))
        if claim and claim.get("evidence_status") == "general_background":
            if "reviewed" in card.get("authority", "").lower():
                issues.append("background_claims_reviewed_authority")
    return issues


def unsupported_fixture_issues(payload: dict[str, Any], *, forbidden_fact: str) -> list[str]:
    """A label cannot excuse publishing a fact explicitly false in a fixture."""
    text = " ".join(
        [
            str(payload.get("answer") or ""),
            *[str(c.get("text", "")) for c in payload.get("claims", [])],
        ]
    ).casefold()
    return ["fabricated_fixture_fact"] if forbidden_fact.casefold() in text else []
