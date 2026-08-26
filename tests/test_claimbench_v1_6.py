from __future__ import annotations

import json
from pathlib import Path

from rag_helpers import make_chunk, write_test_corpus

from firelens.answering.context import build_evidence_packet
from firelens.answering.semantic_invariants import SEMANTIC_MODEL_CHECKER_ENABLED
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.claim_trust import GROUNDED_PUBLIC_WORDING, corpus_claim_trust
from firelens.contracts import (
    ClaimSupport,
    DraftProposalClaim,
    EvidenceStatus,
    GroundedDraft,
    PublicClaim,
)
from firelens.evaluation.claimbench import (
    CLAIMBENCH_RELATIVE,
    MANIFEST_RELATIVE,
    catalog_identity,
    evaluate_catalog,
    load_claimbench,
)
from firelens.evaluation.common import file_sha256
from firelens.evaluation.v1_6_standard import load_v1_6_standard
from firelens.publication.fallback import explanation_authority
from firelens.retrieval.vector import retrieval_hit_from_chunk

ROOT = Path(__file__).resolve().parents[1]


def test_claimbench_catalog_meets_frozen_floors() -> None:
    standard = load_v1_6_standard(ROOT)
    catalog = load_claimbench(ROOT)
    manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    identity = catalog_identity(ROOT)

    faithful = [case for case in catalog.cases if case.kind == "faithful"]
    mutations = [case for case in catalog.cases if case.kind == "mutation"]
    assert len(catalog.cases) >= standard.claimbench.minimum_total_cases
    assert len(faithful) >= standard.claimbench.minimum_faithful_paraphrases
    assert len(mutations) >= standard.claimbench.minimum_unsafe_mutations
    assert identity["sha256"] == manifest["sha256"] == file_sha256(ROOT / CLAIMBENCH_RELATIVE)
    assert len({case.id for case in catalog.cases}) == len(catalog.cases)


def test_claimbench_rejects_mutations_without_mass_abstention() -> None:
    summary = evaluate_catalog(load_claimbench(ROOT))
    standard = load_v1_6_standard(ROOT)

    assert summary["always_abstain"] is False
    assert (
        summary["unsafe_false_accept_rate"] <= standard.claimbench.unsafe_false_accept_rate_max
    )
    assert summary["faithful_false_reject_rate"] == 0.0
    assert (
        summary["critical_field_preservation"]
        == standard.claimbench.critical_field_preservation
    )
    assert summary["partial_salvage_correctness"] == 1.0
    assert SEMANTIC_MODEL_CHECKER_ENABLED is False


def test_public_claim_trust_is_additive() -> None:
    claim = PublicClaim(
        claim_id="C1",
        text="Include water, medication, and copies of important documents.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[
            ClaimSupport(
                evidence_id="E1",
                quote="Include water, medication, and copies of important documents.",
            )
        ],
        trust=corpus_claim_trust(
            authority="recognized_wildfire_preparedness_program",
            review_provenance="native_text",
        ),
        publication=explanation_authority(),
    )
    dumped = claim.model_dump()
    assert dumped["evidence_status"] == "verified_corpus"
    assert dumped["trust"]["source_provenance"] == "approved_static_corpus"
    assert dumped["trust"]["critical_field_preservation"] == "preserved"
    assert "Verified answers" not in GROUNDED_PUBLIC_WORDING
    assert GROUNDED_PUBLIC_WORDING.startswith("Grounded in reviewed official sources")


def test_partial_salvage_keeps_only_faithful_claims(tmp_path: Path) -> None:
    quote = "Do not return until the evacuation order is rescinded."
    chunk = make_chunk("a", quote)
    config = write_test_corpus(tmp_path, [chunk])
    packet = build_evidence_packet(
        "What does the guidance say?",
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="test-corpus.v1",
        config=config,
    )
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[
            DraftProposalClaim(text=quote, evidence_quote_ids=[quote_id]),
            DraftProposalClaim(
                text="Return before the evacuation order is rescinded.",
                evidence_quote_ids=[quote_id],
            ),
        ],
        limitations=packet.limitations,
    )

    assert validate_draft(draft, packet).accepted is False
    salvaged = salvage_valid_grounded_claims(draft, packet)
    assert salvaged is not None
    kept, report = salvaged
    assert report.accepted is True
    assert [claim.text for claim in kept.claims] == [quote]
