from __future__ import annotations

import pytest
from pydantic import ValidationError

from firelens.contracts import (
    EvidenceConflict,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
)


def _span(
    evidence_id: str = "E1",
    *,
    document_sha256: str = "a" * 64,
    primary_chunk_ids: list[str] | None = None,
    chunk_ids: list[str] | None = None,
    primary_text: str = "Keep water in an emergency kit.",
) -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id=evidence_id,
        primary_chunk_ids=primary_chunk_ids or [f"{evidence_id}-chunk-1"],
        chunk_ids=chunk_ids or [f"{evidence_id}-chunk-1"],
        primary_text=primary_text,
        context_text=primary_text,
        source_id=f"source-{evidence_id}",
        title="Preparedness Guide",
        publisher="PreparedBC",
        canonical_url="https://example.test/guide.pdf",
        page_number=5,
        section_title="Emergency kits",
        locator="PDF page 5",
        temporal_class="stable_guidance",
        authority_class="provincial_government",
        document_sha256=document_sha256,
    )


def _packet(**overrides: object) -> EvidencePacket:
    fields: dict[str, object] = {
        "question": "What belongs in an emergency kit?",
        "corpus_version": "test.v1",
        "items": [_span()],
        "quote_candidates": [
            EvidenceQuoteCandidate(
                quote_id="E1Q1",
                evidence_id="E1",
                text="Keep water in an emergency kit.",
            )
        ],
    }
    fields.update(overrides)
    return EvidencePacket(**fields)


def test_accepts_packet_with_resolvable_identity_references() -> None:
    second = _span(
        "E2",
        document_sha256="b" * 64,
        primary_text="Keep a flashlight in an emergency kit.",
    )

    packet = _packet(
        items=[_span(), second],
        quote_candidates=[
            EvidenceQuoteCandidate(
                quote_id="E1Q1",
                evidence_id="E1",
                text="Keep water in an emergency kit.",
            ),
            EvidenceQuoteCandidate(
                quote_id="E2Q1",
                evidence_id="E2",
                text="Keep a flashlight in an emergency kit.",
            ),
        ],
        conflicts=[
            EvidenceConflict(
                conflict_id="X1",
                quote_ids=["E1Q1", "E2Q1"],
                differing_terms=["water", "flashlight"],
                explanation="The sources prescribe different emergency-kit contents.",
            )
        ],
    )

    assert packet.conflicts[0].quote_ids == ["E1Q1", "E2Q1"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"items": [_span(), _span()]}, "evidence IDs must be unique"),
        (
            {
                "items": [
                    _span(
                        "E1",
                        primary_chunk_ids=["shared-chunk"],
                        chunk_ids=["shared-chunk"],
                    ),
                    _span(
                        "E2",
                        primary_chunk_ids=["shared-chunk"],
                        chunk_ids=["shared-chunk"],
                    ),
                ]
            },
            "chunk IDs must be unique across the evidence packet",
        ),
        (
            {
                "items": [
                    _span(chunk_ids=["chunk-1", "chunk-1"]),
                ]
            },
            "evidence span chunk IDs must be unique",
        ),
        (
            {
                "items": [
                    _span(
                        primary_chunk_ids=["primary-1", "primary-1"],
                        chunk_ids=["primary-1"],
                    )
                ]
            },
            "evidence span primary chunk IDs must be unique",
        ),
        (
            {"items": [_span(primary_chunk_ids=["missing-primary"], chunk_ids=["chunk-1"])]},
            "evidence span primary chunk IDs must be contained",
        ),
        (
            {
                "quote_candidates": [
                    EvidenceQuoteCandidate(
                        quote_id="E1Q1",
                        evidence_id="E1",
                        text="Keep water in an emergency kit.",
                    ),
                    EvidenceQuoteCandidate(
                        quote_id="E1Q1",
                        evidence_id="E1",
                        text="Keep water in an emergency kit.",
                    ),
                ]
            },
            "quote IDs must be unique",
        ),
        (
            {
                "quote_candidates": [
                    EvidenceQuoteCandidate(
                        quote_id="E2Q1",
                        evidence_id="E2",
                        text="Keep water in an emergency kit.",
                    )
                ]
            },
            "quote candidate must reference exactly one evidence span",
        ),
        (
            {
                "quote_candidates": [
                    EvidenceQuoteCandidate(
                        quote_id="E1Q1", evidence_id="E1", text="Invented wording."
                    )
                ]
            },
            "quote candidate text must occur",
        ),
    ],
)
def test_rejects_malformed_evidence_and_quote_references(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _packet(**overrides)


@pytest.mark.parametrize(
    ("conflicts", "message"),
    [
        (
            [
                EvidenceConflict(
                    conflict_id="X1",
                    quote_ids=["E1Q1", "E1Q1"],
                    differing_terms=["one", "two"],
                    explanation="Duplicate quote reference.",
                )
            ],
            "conflict quote IDs must be unique",
        ),
        (
            [
                EvidenceConflict(
                    conflict_id="X1",
                    quote_ids=["E1Q1", "missing"],
                    differing_terms=["one", "two"],
                    explanation="Missing quote reference.",
                )
            ],
            "conflict quote IDs must reference existing quotes",
        ),
        (
            [
                EvidenceConflict(
                    conflict_id="X1",
                    quote_ids=["E1Q1", "E1Q2"],
                    differing_terms=["one", "two"],
                    explanation="Same-document references.",
                )
            ],
            "conflict quotes must reference distinct source documents",
        ),
    ],
)
def test_rejects_malformed_conflict_references(
    conflicts: list[EvidenceConflict], message: str
) -> None:
    quotes = [
        EvidenceQuoteCandidate(
            quote_id="E1Q1", evidence_id="E1", text="Keep water in an emergency kit."
        ),
        EvidenceQuoteCandidate(quote_id="E1Q2", evidence_id="E1", text="water"),
    ]
    with pytest.raises(ValidationError, match=message):
        _packet(quote_candidates=quotes, conflicts=conflicts)


def test_rejects_duplicate_conflict_ids() -> None:
    conflict = EvidenceConflict(
        conflict_id="X1",
        quote_ids=["E1Q1", "E2Q1"],
        differing_terms=["water", "flashlight"],
        explanation="The sources prescribe different emergency-kit contents.",
    )
    second = _span(
        "E2",
        document_sha256="b" * 64,
        primary_text="Keep a flashlight in an emergency kit.",
    )
    quotes = [
        EvidenceQuoteCandidate(
            quote_id="E1Q1", evidence_id="E1", text="Keep water in an emergency kit."
        ),
        EvidenceQuoteCandidate(
            quote_id="E2Q1", evidence_id="E2", text="Keep a flashlight in an emergency kit."
        ),
    ]

    with pytest.raises(ValidationError, match="conflict IDs must be unique"):
        _packet(
            items=[_span(), second], quote_candidates=quotes, conflicts=[conflict, conflict]
        )
