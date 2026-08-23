"""Fail-closed identity checks for evidence packets.

The packet models remain in :mod:`firelens.contracts`; this module keeps their
cross-reference validation small, explicit, and independently testable without
changing any serialized contract.
"""

from __future__ import annotations

from typing import Any


def validate_evidence_packet_identity(packet: Any) -> None:
    """Reject packet references whose evidence identity cannot be resolved exactly."""

    evidence_ids = [span.evidence_id for span in packet.items]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence IDs must be unique")

    for span in packet.items:
        if len(span.chunk_ids) != len(set(span.chunk_ids)):
            raise ValueError("evidence span chunk IDs must be unique")
        if len(span.primary_chunk_ids) != len(set(span.primary_chunk_ids)):
            raise ValueError("evidence span primary chunk IDs must be unique")
        if not set(span.primary_chunk_ids).issubset(span.chunk_ids):
            raise ValueError("evidence span primary chunk IDs must be contained in chunk IDs")

    packet_chunk_ids = [chunk_id for span in packet.items for chunk_id in span.chunk_ids]
    if len(packet_chunk_ids) != len(set(packet_chunk_ids)):
        raise ValueError("chunk IDs must be unique across the evidence packet")

    quote_ids = [candidate.quote_id for candidate in packet.quote_candidates]
    if len(quote_ids) != len(set(quote_ids)):
        raise ValueError("quote IDs must be unique")

    spans_by_id = {span.evidence_id: span for span in packet.items}
    quotes_by_id: dict[str, Any] = {}
    for candidate in packet.quote_candidates:
        linked_span = spans_by_id.get(candidate.evidence_id)
        if linked_span is None:
            raise ValueError("quote candidate must reference exactly one evidence span")
        if candidate.text not in linked_span.primary_text:
            raise ValueError("quote candidate text must occur in linked primary source text")
        quotes_by_id[candidate.quote_id] = candidate

    conflict_ids = [conflict.conflict_id for conflict in packet.conflicts]
    if len(conflict_ids) != len(set(conflict_ids)):
        raise ValueError("conflict IDs must be unique")

    for conflict in packet.conflicts:
        if len(conflict.quote_ids) != len(set(conflict.quote_ids)):
            raise ValueError("conflict quote IDs must be unique")
        referenced_quotes = [quotes_by_id.get(quote_id) for quote_id in conflict.quote_ids]
        if any(candidate is None for candidate in referenced_quotes):
            raise ValueError("conflict quote IDs must reference existing quotes")
        document_ids = {
            spans_by_id[candidate.evidence_id].document_sha256
            for candidate in referenced_quotes
            if candidate is not None
        }
        if len(document_ids) != len(conflict.quote_ids):
            raise ValueError("conflict quotes must reference distinct source documents")
