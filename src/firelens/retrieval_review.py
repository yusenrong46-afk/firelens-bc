"""Hash-bound owner adjudication for sealed retrieval relevance labels."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from firelens.benchmark import file_sha256, load_benchmark


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrievalCaseReview(ReviewModel):
    case_id: str = Field(min_length=1, max_length=80)
    question_is_independent: bool = False
    answerability_correct: bool = False
    acceptable_evidence_correct: bool = False
    decision: Literal["pending", "approve", "reject", "needs_discussion"] = "pending"
    notes: str = Field(default="", max_length=4_000)


class RetrievalOwnerReview(ReviewModel):
    review_version: Literal["firelens_retrieval_owner_review.v1"]
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str | None = Field(default=None, min_length=1, max_length=200)
    reviewed_at: datetime | None = None
    cases: list[RetrievalCaseReview] = Field(min_length=1)

    @field_validator("reviewer")
    @classmethod
    def reviewer_must_name_a_person(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("reviewer must not be blank")
        return normalized

    @model_validator(mode="after")
    def unique_case_ids(self) -> RetrievalOwnerReview:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("retrieval owner review contains duplicate case IDs")
        return self


def build_retrieval_review_template(dataset_path: Path) -> RetrievalOwnerReview:
    dataset = load_benchmark(dataset_path, require_release_shape=False)
    answerable_holdout = [
        case for case in dataset.cases if case.split == "holdout" and case.acceptable_evidence
    ]
    if not answerable_holdout:
        raise ValueError("retrieval review requires answerable holdout cases")
    return RetrievalOwnerReview(
        review_version="firelens_retrieval_owner_review.v1",
        dataset_sha256=file_sha256(dataset_path),
        cases=[RetrievalCaseReview(case_id=case.id) for case in answerable_holdout],
    )


def write_retrieval_review_template(
    dataset_path: Path, output_path: Path
) -> RetrievalOwnerReview:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing retrieval review: {output_path}")
    review = build_retrieval_review_template(dataset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(review.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return review


def write_retrieval_review_packet(
    dataset_path: Path,
    corpus_chunks_path: Path,
    output_path: Path,
) -> None:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite retrieval review packet: {output_path}")
    dataset = load_benchmark(dataset_path, require_release_shape=False)
    chunks = {
        row["chunk_id"]: row
        for row in (
            json.loads(line)
            for line in corpus_chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    lines = [
        "# FireLens V1.5 sealed retrieval label review",
        "",
        "Review every question without running or inspecting retrieval results. Confirm that the "
        "question was independently authored after configuration freeze, that it is answerable "
        "from the governed corpus, and that every listed original chunk is acceptable evidence. "
        "Record the decisions only in the hash-bound YAML sidecar.",
        "",
        f"Dataset SHA-256: `{file_sha256(dataset_path)}`",
        "",
    ]
    for case in dataset.cases:
        if case.split != "holdout" or not case.acceptable_evidence:
            continue
        lines.extend(
            [
                f"## {case.id}",
                "",
                f"**Question:** {case.question}",
                "",
                f"**Required concepts:** {', '.join(case.required_concepts) or 'none'}",
                "",
                f"**Forbidden claims:** {', '.join(case.forbidden_claims) or 'none'}",
                "",
            ]
        )
        for gold in case.acceptable_evidence:
            for chunk_id in gold.chunk_ids:
                chunk = chunks.get(chunk_id)
                if chunk is None:
                    raise ValueError(f"review packet references unknown chunk: {chunk_id}")
                lines.extend(
                    [
                        f"### Evidence `{chunk_id}`",
                        "",
                        f"- Source: {chunk['title']} (`{chunk['source_id']}`)",
                        f"- Locator: {chunk.get('locator') or 'not supplied'}",
                        f"- Authority: {chunk['authority_class']}",
                        "",
                        str(chunk["text"]),
                        "",
                    ]
                )
        lines.extend(
            [
                "- [ ] question independently authored after configuration freeze",
                "- [ ] answerability label correct",
                "- [ ] acceptable evidence label correct",
                "- [ ] approve  [ ] reject  [ ] needs discussion",
                "",
                "---",
                "",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def validate_retrieval_owner_review(
    dataset_path: Path,
    review_path: Path,
    *,
    expected_case_count: int = 47,
) -> dict[str, object]:
    dataset = load_benchmark(dataset_path, require_release_shape=False)
    review = RetrievalOwnerReview.model_validate(
        yaml.safe_load(review_path.read_text(encoding="utf-8"))
    )
    actual_dataset_sha256 = file_sha256(dataset_path)
    if review.dataset_sha256 != actual_dataset_sha256:
        raise ValueError("retrieval owner review does not match the dataset hash")

    dataset_case_ids = {
        case.id
        for case in dataset.cases
        if case.split == "holdout" and case.acceptable_evidence
    }
    review_case_ids = {case.case_id for case in review.cases}
    if dataset_case_ids != review_case_ids:
        missing = sorted(dataset_case_ids - review_case_ids)
        unknown = sorted(review_case_ids - dataset_case_ids)
        raise ValueError(
            f"retrieval owner review case mismatch; missing={missing}, unknown={unknown}"
        )

    results = [
        {
            "case_id": case.case_id,
            "approved": bool(
                case.decision == "approve"
                and case.question_is_independent
                and case.answerability_correct
                and case.acceptable_evidence_correct
            ),
            "decision": case.decision,
        }
        for case in review.cases
    ]
    approved_case_count = sum(bool(case["approved"]) for case in results)
    expected_case_count_present = len(results) == expected_case_count
    qualified = bool(
        review.reviewer
        and review.reviewed_at
        and expected_case_count_present
        and approved_case_count == len(results)
    )
    return {
        "summary_version": "firelens_retrieval_owner_review_summary.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": actual_dataset_sha256,
        "review_sha256": file_sha256(review_path),
        "reviewer": review.reviewer,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "reviewer_present": bool(review.reviewer),
        "reviewed_at_present": review.reviewed_at is not None,
        "case_count": len(results),
        "expected_case_count": expected_case_count,
        "expected_case_count_present": expected_case_count_present,
        "approved_case_count": approved_case_count,
        "qualified": qualified,
        "cases": results,
    }
