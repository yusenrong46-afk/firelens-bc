"""Shared loaders for Round-3 semantic development suites. Not production code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rag_helpers import make_chunk, write_test_corpus

from firelens.answering.context import build_evidence_packet
from firelens.answering.semantic_invariants import preservation_errors
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.contracts import DraftProposalClaim, GroundedDraft
from firelens.retrieval.vector import retrieval_hit_from_chunk

ROOT = Path(__file__).resolve().parents[1]
FABLE_ADVERSARY = ROOT / "data/evaluation/fable5_round2_adversary.yaml"
ROUND3_DEV = ROOT / "data/evaluation/round3_semantic_dev.yaml"


def load_case_file(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"no cases in {path}")
    return cases


def checker_row(case: dict[str, Any]) -> dict[str, Any]:
    errors = preservation_errors(case["claim"], [case["quote"]])
    accepted = not errors
    expected_accept = case["expect"] == "accept"
    return {
        "id": case["id"],
        "expect": case["expect"],
        "accepted": accepted,
        "correct": accepted == expected_accept,
        "errors": errors,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    faithful = [row for row in rows if row["expect"] == "accept"]
    mutations = [row for row in rows if row["expect"] == "reject"]
    unsafe = [row["id"] for row in mutations if row["accepted"]]
    over = [row["id"] for row in faithful if not row["accepted"]]
    return {
        "total": len(rows),
        "faithful": len(faithful),
        "mutations": len(mutations),
        "correct": sum(1 for row in rows if row["correct"]),
        "unsafe_false_accepts": unsafe,
        "faithful_false_rejects": over,
        "unsafe_false_accept_rate": (len(unsafe) / len(mutations) if mutations else 1.0),
        "faithful_false_reject_rate": (len(over) / len(faithful) if faithful else 1.0),
        "always_abstain": bool(rows) and all(not row["accepted"] for row in rows),
    }


def publish_claim(tmp_path: Path, quote: str, claim: str) -> tuple[bool, list[str], bool]:
    """Return (published, errors, salvage_leaked_rejected_claim)."""

    chunk = make_chunk("round3-span", quote)
    config = write_test_corpus(tmp_path, [chunk])
    packet = build_evidence_packet(
        "What does the official guidance say?",
        [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
        [chunk],
        corpus_version="round3-dev.v1",
        config=config,
    )
    quote_id = packet.quote_candidates[0].quote_id
    draft = GroundedDraft(
        answer_type="grounded",
        claims=[DraftProposalClaim(text=claim, evidence_quote_ids=[quote_id])],
        limitations=packet.limitations,
    )
    report = validate_draft(draft, packet)
    leaked = False
    if not report.accepted:
        mixed = GroundedDraft(
            answer_type="grounded",
            claims=[
                DraftProposalClaim(text=quote, evidence_quote_ids=[quote_id]),
                DraftProposalClaim(text=claim, evidence_quote_ids=[quote_id]),
            ],
            limitations=packet.limitations,
        )
        salvaged = salvage_valid_grounded_claims(mixed, packet)
        if salvaged is not None and claim in [item.text for item in salvaged[0].claims]:
            leaked = True
    return report.accepted, list(report.errors), leaked
