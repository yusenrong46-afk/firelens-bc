"""Deterministic preparation of agent-proposed typed claims for human review."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from firelens.answering.typed_compare import typed_preservation_errors
from firelens.contract_base import FrozenStrictModel

RAW_RELATIVE = "data/typed_claims/candidates_pending_v1.yaml"
SEED_RELATIVE = "data/typed_claims/candidate_preparation_seed_v2.yaml"
CORPUS_RELATIVE = "data/processed/firelens_static_corpus.chunks.jsonl"

PreparationDisposition = Literal[
    "review_ready",
    "duplicate_existing",
    "not_claim_bearing",
    "needs_source_repair",
]


def normalized_sha256(text: str) -> str:
    return sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class CandidateTypedFields(FrozenStrictModel):
    subject: str = Field(min_length=2, max_length=200)
    action: str | None = Field(default=None, max_length=80)
    action_polarity: str | None = Field(default=None, max_length=40)
    object: str | None = Field(default=None, max_length=200)
    modality: str | None = Field(default=None, max_length=40)
    urgency: str | None = Field(default=None, max_length=40)
    status_stage: str | None = Field(default=None, max_length=80)
    quantities: list[str] = Field(default_factory=list, max_length=8)
    canonical_units: list[str] = Field(default_factory=list, max_length=8)
    ranges: list[str] = Field(default_factory=list, max_length=4)
    comparator: str | None = Field(default=None, max_length=40)
    conditions: list[str] = Field(default_factory=list, max_length=8)
    exceptions: list[str] = Field(default_factory=list, max_length=8)
    applies_to: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_atomic_relationship(self) -> CandidateTypedFields:
        if not any((self.action, self.status_stage, self.quantities, self.conditions)):
            raise ValueError("typed candidate lacks an atomic relationship")
        return self


class SeedDisposition(FrozenStrictModel):
    parent_candidate_id: str
    disposition: PreparationDisposition
    reason: str = Field(min_length=4, max_length=400)


class SeedProposal(FrozenStrictModel):
    candidate_id: str = Field(pattern=r"^PC2-[A-Z0-9-]+-[0-9]{2}$")
    parent_candidate_id: str
    exact_source_quote: str = Field(min_length=8, max_length=1200)
    proposed_surface: str = Field(min_length=8, max_length=600)
    typed_fields: CandidateTypedFields
    preparation_notes: str = Field(min_length=4, max_length=500)
    quality_flags: list[str] = Field(default_factory=list, max_length=8)


class CandidatePreparationSeed(FrozenStrictModel):
    schema_version: Literal["firelens.typed_claim_preparation_seed.v2"]
    note: str
    dispositions: list[SeedDisposition]
    proposals: list[SeedProposal]


class PreparedCandidate(FrozenStrictModel):
    candidate_id: str
    parent_candidate_id: str
    preparation_status: Literal["review_ready"] = "review_ready"
    review_status: Literal["pending_review"] = "pending_review"
    reviewer: None = None
    reviewed_at: None = None
    risk_tier: Literal["A"] = "A"
    coverage_domain: str
    authority: str
    jurisdiction: str
    source_id: str
    source_span_ids: list[str]
    source_revision: str
    source_document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_span_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposed_surface_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    exact_source_quote: str
    surrounding_context: str
    proposed_surface: str
    typed_fields: CandidateTypedFields
    preparation_notes: str
    quality_flags: list[str]


class PreparedBatch(FrozenStrictModel):
    batch: int = Field(ge=2)
    candidate_ids: list[str] = Field(min_length=1, max_length=12)


class PreparedCandidateArtifact(FrozenStrictModel):
    schema_version: Literal["firelens.typed_claim_candidates.v2"]
    raw_queue_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    note: str
    dispositions: list[SeedDisposition]
    prepared_candidates: list[PreparedCandidate]
    batches: list[PreparedBatch]


def build_prepared_candidates(root: Path) -> PreparedCandidateArtifact:
    raw_path = root / RAW_RELATIVE
    seed_path = root / SEED_RELATIVE
    corpus_path = root / CORPUS_RELATIVE
    raw_payload: dict[str, Any] = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    seed = CandidatePreparationSeed.model_validate(
        yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    )
    raw_rows = list(raw_payload.get("records", []))
    raw_by_id = {str(row["claim_id"]): row for row in raw_rows}
    _validate_dispositions(raw_by_id, seed)
    chunks = _load_chunks(corpus_path)
    prepared = [_prepare_candidate(proposal, raw_by_id, chunks) for proposal in seed.proposals]
    prepared_ids = [row.candidate_id for row in prepared]
    if len(prepared_ids) != len(set(prepared_ids)):
        raise ValueError("prepared candidate IDs must be unique")
    batches = [
        PreparedBatch(batch=2 + index, candidate_ids=prepared_ids[offset : offset + 10])
        for index, offset in enumerate(range(0, len(prepared_ids), 10))
    ]
    if any(len(batch.candidate_ids) < 10 for batch in batches):
        raise ValueError("review-ready candidates must form complete 10-12 card batches")
    return PreparedCandidateArtifact(
        schema_version="firelens.typed_claim_candidates.v2",
        raw_queue_sha256=file_sha256(raw_path),
        corpus_sha256=file_sha256(corpus_path),
        note=(
            "Coding-agent proposals only. Every prepared claim remains pending_review; "
            "only a named human may approve, edit, reject, or defer it."
        ),
        dispositions=seed.dispositions,
        prepared_candidates=prepared,
        batches=batches,
    )


def disposition_counts(artifact: PreparedCandidateArtifact) -> dict[str, int]:
    return dict(Counter(row.disposition for row in artifact.dispositions))


def _validate_dispositions(
    raw_by_id: dict[str, dict[str, Any]], seed: CandidatePreparationSeed
) -> None:
    disposition_ids = [row.parent_candidate_id for row in seed.dispositions]
    if len(disposition_ids) != len(set(disposition_ids)):
        raise ValueError("raw candidates must have exactly one disposition")
    if set(disposition_ids) != set(raw_by_id):
        missing = sorted(set(raw_by_id) - set(disposition_ids))
        extra = sorted(set(disposition_ids) - set(raw_by_id))
        raise ValueError(f"candidate disposition mismatch missing={missing} extra={extra}")
    dispositions = {row.parent_candidate_id: row.disposition for row in seed.dispositions}
    for proposal in seed.proposals:
        if dispositions.get(proposal.parent_candidate_id) != "review_ready":
            raise ValueError("only review_ready parents may have prepared proposals")
    ready_parents = {row.parent_candidate_id for row in seed.proposals}
    expected_ready = {
        row.parent_candidate_id
        for row in seed.dispositions
        if row.disposition == "review_ready"
    }
    if ready_parents != expected_ready:
        raise ValueError("every review_ready parent must produce at least one proposal")


def _load_chunks(path: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        chunk_id = str(row["chunk_id"])
        if chunk_id in chunks:
            raise ValueError(f"duplicate corpus chunk ID {chunk_id}")
        chunks[chunk_id] = row
    return chunks


def _prepare_candidate(
    proposal: SeedProposal,
    raw_by_id: dict[str, dict[str, Any]],
    chunks: dict[str, dict[str, Any]],
) -> PreparedCandidate:
    raw = raw_by_id[proposal.parent_candidate_id]
    span_ids = [str(value) for value in raw["source_span_ids"]]
    bound_chunks = [chunks.get(span_id) for span_id in span_ids]
    if any(row is None for row in bound_chunks):
        raise ValueError(f"{proposal.candidate_id} references a missing corpus chunk")
    present = [row for row in bound_chunks if row is not None]
    document_hashes = {str(row["document_sha256"]) for row in present}
    if len(document_hashes) != 1:
        raise ValueError(f"{proposal.candidate_id} spans multiple source revisions")
    quote = " ".join(proposal.exact_source_quote.split())
    if not any(quote in " ".join(str(row["text"]).split()) for row in present):
        raise ValueError(f"{proposal.candidate_id} quote is not in its admitted source")
    errors = typed_preservation_errors(
        proposal.proposed_surface,
        [proposal.exact_source_quote],
    )
    if errors:
        raise ValueError(f"{proposal.candidate_id} changes source meaning: {errors}")
    return PreparedCandidate(
        candidate_id=proposal.candidate_id,
        parent_candidate_id=proposal.parent_candidate_id,
        coverage_domain=str(raw["coverage_domain"]),
        authority=str(raw["authority"]),
        jurisdiction=str(raw["jurisdiction"]),
        source_id=str(raw["source_id"]),
        source_span_ids=span_ids,
        source_revision=str(raw["source_revision"]),
        source_document_sha256=document_hashes.pop(),
        source_span_sha256=normalized_sha256(proposal.exact_source_quote),
        proposed_surface_sha256=normalized_sha256(proposal.proposed_surface),
        exact_source_quote=proposal.exact_source_quote,
        surrounding_context="\n\n".join(str(row["text"]) for row in present),
        proposed_surface=proposal.proposed_surface,
        typed_fields=proposal.typed_fields,
        preparation_notes=proposal.preparation_notes,
        quality_flags=proposal.quality_flags,
    )
