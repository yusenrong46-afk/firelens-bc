"""Deterministic rendering of reviewed Tier A/B claims.

Critical fields come from the typed record. The model does not own them.
"""

from __future__ import annotations

from firelens.answering.typed_compare import compare_snapshots
from firelens.answering.typed_records import TypedClaimRecord
from firelens.answering.typed_snapshot import extract_snapshot


def render_typed_claim(record: TypedClaimRecord) -> str:
    """Return the reviewed canonical sentence. No model rewrite of critical fields."""

    if not record.production_supported():
        raise ValueError(f"{record.claim_id} is not a production-supported typed claim")
    return record.canonical_text.strip()


def canonicalize_claim_text(
    claim_text: str, quote: str, records: list[TypedClaimRecord]
) -> str:
    """Replace generated Tier A/B prose with the reviewed render when compatible."""

    if not records:
        return claim_text
    if " ".join(claim_text.split()).casefold() == " ".join(quote.split()).casefold():
        return claim_text
    claim_snap = extract_snapshot(claim_text)
    quote_snap = extract_snapshot(quote)
    if compare_snapshots(claim_snap, quote_snap):
        return claim_text
    for record in records:
        rendered = render_typed_claim(record)
        if not compare_snapshots(extract_snapshot(rendered), quote_snap):
            if claim_snap.risk_tier.value in {"A", "B"}:
                return rendered
    return claim_text
