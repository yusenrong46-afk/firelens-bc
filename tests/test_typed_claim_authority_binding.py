from __future__ import annotations

import json
from pathlib import Path

import yaml

from firelens.contracts import (
    AuthorityClass,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    TemporalClass,
)
from firelens.publication.compiler import select_typed_claim_ids
from firelens.publication.records import clear_authority_caches, get_versioned

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data/typed_claims/high_risk_v1.yaml"
CORPUS = ROOT / "data/processed/firelens_static_corpus.chunks.jsonl"
ORDER_CHUNK_ID = "preparedbc_wildfire_guide:page:11:chunk:2"


def _authority_root(tmp_path: Path) -> Path:
    inventory = tmp_path / "data/typed_claims/high_risk_v1.yaml"
    corpus = tmp_path / "data/processed/firelens_static_corpus.chunks.jsonl"
    inventory.parent.mkdir(parents=True)
    corpus.parent.mkdir(parents=True)
    inventory.write_bytes(INVENTORY.read_bytes())
    corpus.write_bytes(CORPUS.read_bytes())
    return tmp_path


def _rewrite_chunk(root: Path, chunk_id: str, **updates: str) -> None:
    path = root / "data/processed/firelens_static_corpus.chunks.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["chunk_id"] == chunk_id:
            row.update(updates)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_reviewed_claim_uses_admitted_document_and_surface_hashes() -> None:
    record = get_versioned("TC-EVAC-ORDER-001")
    assert record.available_for_structured_support is True
    assert record.source_revision_sha256 == (
        "f82166e0c05cb3f46a42aa4023da7cdd71e3c3fdae64965c8f436426f5702ea3"
    )
    assert record.source_span_sha256 == record.record.source_span_sha256
    assert record.approved_surface_sha256 == record.record.approved_surface_sha256


def test_changed_corpus_document_or_span_invalidates_support(tmp_path: Path) -> None:
    root = _authority_root(tmp_path)
    _rewrite_chunk(root, ORDER_CHUNK_ID, document_sha256="0" * 64)
    assert (
        get_versioned("TC-EVAC-ORDER-001", root=str(root)).available_for_structured_support
        is False
    )

    root = _authority_root(tmp_path / "span")
    _rewrite_chunk(root, ORDER_CHUNK_ID, text="Unrelated replacement text.")
    assert (
        get_versioned("TC-EVAC-ORDER-001", root=str(root)).available_for_structured_support
        is False
    )


def test_changed_approved_surface_without_rebinding_invalidates_support(tmp_path: Path) -> None:
    root = _authority_root(tmp_path)
    path = root / "data/typed_claims/high_risk_v1.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    order = next(row for row in payload["records"] if row["claim_id"] == "TC-EVAC-ORDER-001")
    order["canonical_text"] = "An evacuation order can wait until later."
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    assert (
        get_versioned("TC-EVAC-ORDER-001", root=str(root)).available_for_structured_support
        is False
    )


def test_authority_cache_can_be_cleared_for_reload(tmp_path: Path) -> None:
    root = _authority_root(tmp_path)
    first = get_versioned("TC-EVAC-ORDER-001", root=str(root))
    assert first.available_for_structured_support is True
    assert get_versioned("TC-EVAC-ORDER-001", root=str(root)) is first
    _rewrite_chunk(root, ORDER_CHUNK_ID, document_sha256="0" * 64)
    assert get_versioned("TC-EVAC-ORDER-001", root=str(root)) is first
    clear_authority_caches()
    reloaded = get_versioned("TC-EVAC-ORDER-001", root=str(root))
    assert reloaded is not first
    assert reloaded.available_for_structured_support is False


def test_unrelated_quote_from_same_chunk_does_not_select_order_claim() -> None:
    packet = EvidencePacket(
        question="What should I do with doors and windows?",
        corpus_version="test.v1",
        items=[
            EvidenceSpan(
                evidence_id="E1",
                primary_chunk_ids=[ORDER_CHUNK_ID],
                chunk_ids=[ORDER_CHUNK_ID],
                primary_text="On your way out close doors and windows.",
                context_text="On your way out close doors and windows.",
                source_id="preparedbc_wildfire_guide",
                title="Wildfire Preparedness Guide",
                publisher="PreparedBC",
                canonical_url="https://example.test/guide.pdf",
                page_number=11,
                section_title="Evacuation Order",
                locator="page:11",
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=(
                    "f82166e0c05cb3f46a42aa4023da7cdd71e3c3fdae64965c8f436426f5702ea3"
                ),
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(
                quote_id="E1Q1",
                evidence_id="E1",
                text="On your way out close doors and windows.",
            )
        ],
    )
    assert select_typed_claim_ids(packet) == []
