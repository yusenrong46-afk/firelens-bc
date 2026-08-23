"""Development cases: free-form Tier A/B text cannot become structured-supported."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from rag_helpers import make_chunk, write_test_corpus
from test_structured_publication_architecture import (
    SUPPORTED_KINDS,
    _is_structured_supported,
    _publication_kind,
)

from firelens.answering.context import build_evidence_packet
from firelens.answering.grounded import GroundedAnswerEngine
from firelens.contracts import DraftProposalClaim, EvidenceStatus, GroundedDraft
from firelens.providers.fake import FakeProvider
from firelens.retrieval.vector import retrieval_hit_from_chunk

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/evaluation/structured_publication_dev.yaml"


def _cases() -> list[dict[str, Any]]:
    payload = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("structured publication development cases are missing")
    return cases


def _case_provider(packet: Any, quote_id: str, claim_text: str) -> FakeProvider:
    class CaseProvider(FakeProvider):
        async def generate_grounded(self, messages, *, output_schema):  # type: ignore[no-untyped-def]
            result = await super().generate_grounded(messages, output_schema=output_schema)
            draft = GroundedDraft(
                answer_type="grounded",
                claims=[DraftProposalClaim(text=claim_text, evidence_quote_ids=[quote_id])],
                limitations=packet.limitations,
            )
            return result.model_copy(update={"draft": draft})

    return CaseProvider(dimensions=8)


def test_free_form_tier_ab_cannot_obtain_supported_status(tmp_path: Path) -> None:
    failures: list[str] = []
    for case in _cases():
        chunk = make_chunk(f"dev-{case['id']}", str(case["quote"]).strip())
        config = write_test_corpus(tmp_path / case["id"], [chunk])
        packet = build_evidence_packet(
            "What does the official guidance say?",
            [retrieval_hit_from_chunk(chunk, rerank_rank=1)],
            [chunk],
            corpus_version="structured-dev.v1",
            config=config,
        )
        quote_id = packet.quote_candidates[0].quote_id
        claim_text = " ".join(str(case["claim"]).split())

        response = asyncio.run(
            GroundedAnswerEngine(_case_provider(packet, quote_id, claim_text)).answer(
                "What does the official guidance say?",
                packet,
                trace_id=f"trace-{case['id']}",
            )
        ).response
        published = []
        for claim in response.claims:
            authority = getattr(claim, "publication", None)
            compiled = (
                authority is not None
                and getattr(authority, "typed_claim_id", None)
                and _publication_kind(claim) in SUPPORTED_KINDS
                and claim.text != claim_text
            )
            if compiled:
                continue
            if _is_structured_supported(claim) or (
                claim.evidence_status == EvidenceStatus.VERIFIED_CORPUS
                and claim.text == claim_text
            ):
                published.append(claim)
        if published:
            failures.append(case["id"])
    assert not failures, "free-form Tier A/B sentences obtained supported status: " + ", ".join(
        failures
    )
