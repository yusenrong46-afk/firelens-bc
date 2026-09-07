"""Current owner-adopted source revision, alongside retained historical bindings."""

import json
from hashlib import sha256
from pathlib import Path

import pytest

from firelens.publication.compiler import compile_structured_claim
from firelens.publication.records import get_versioned, versioned_records

ROOT = Path(__file__).resolve().parents[1]
DECISION = json.loads((ROOT / "docs/reports/PREPAREDBC_REVISION_DECISIONS.json").read_text())


@pytest.mark.parametrize(
    "approved", DECISION["approved_claims"], ids=lambda row: row["claim_id"]
)
def test_adopted_claim_has_current_technical_binding_and_public_revision(approved):
    claim = get_versioned(approved["claim_id"])
    assert claim.available_for_structured_support
    assert claim.record.source_document_sha256 == DECISION["document_sha256"]
    for field in (
        "subject",
        "action",
        "action_polarity",
        "object",
        "conditions",
        "canonical_text",
        "source_span_text",
    ):
        actual = getattr(claim.record, field)
        assert actual == approved[field]
    compiled = compile_structured_claim(typed_claim_id=claim.claim_id, public_claim_id="C1")
    assert compiled.evidence[0].document_sha256 == DECISION["document_sha256"]
    assert compiled.claim.text == approved["canonical_text"]


def test_retired_document_and_withdrawn_claim_are_not_current_evidence():
    with pytest.raises(ValueError, match="unknown typed claim"):
        get_versioned("TC-GENERAL-036-01")
    rows = [
        json.loads(line)
        for line in (ROOT / "data/processed/firelens_static_corpus.chunks.jsonl")
        .read_text()
        .splitlines()
    ]
    assert all(row["document_sha256"] != DECISION["previous_document_sha256"] for row in rows)
    for claim in versioned_records():
        assert claim.record.source_document_sha256 != DECISION["previous_document_sha256"]
    old = get_versioned("TC-GENERAL-036-01", root=str(ROOT / DECISION["historical_snapshot"]))
    assert old.available_for_structured_support


def test_historical_snapshot_bytes_remain_verifiable_and_unaffected_chunks_identical():
    history = ROOT / DECISION["historical_snapshot"]
    manifest = json.loads((history / "MANIFEST.json").read_text())
    for name, digest in manifest["files"].items():
        assert sha256((history / name).read_bytes()).hexdigest() == digest, name
    name = "data/processed/firelens_static_corpus.chunks.jsonl"

    def unaffected(path):
        return [
            line
            for line in path.read_text().splitlines()
            if json.loads(line)["source_id"] != DECISION["source_id"]
        ]

    assert unaffected(ROOT / name) == unaffected(history / name)
