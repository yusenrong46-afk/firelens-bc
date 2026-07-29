"""Hash-bound owner semantic review contracts and release-gate validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from firelens.benchmark import file_sha256


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimReview(ReviewModel):
    claim_id: str = Field(min_length=1, max_length=80)
    decision: Literal["pending", "supported", "unsupported", "unclear"] = "pending"
    notes: str = Field(default="", max_length=2_000)


class CaseReview(ReviewModel):
    case_id: str = Field(min_length=1, max_length=80)
    required_concepts_present: bool = False
    forbidden_claims_absent: bool = False
    required_limitations_present: bool = False
    decision: Literal["pending", "approve", "reject", "needs_discussion"] = "pending"
    claims: list[ClaimReview] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def unique_claim_ids(self) -> CaseReview:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError(f"duplicate claim review in {self.case_id}")
        return self


class OwnerSemanticReview(ReviewModel):
    review_version: Literal["firelens_owner_semantic_review.v1"]
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str | None = Field(default=None, min_length=1, max_length=200)
    reviewed_at: datetime | None = None
    cases: list[CaseReview] = Field(min_length=1)

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
    def unique_case_ids(self) -> OwnerSemanticReview:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("owner review contains duplicate case IDs")
        return self


def _load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("report_version") != "firelens_conversation_benchmark_report.v1_1":
        raise ValueError("owner review requires a V1.1 conversation benchmark report")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("conversation report has no cases")
    if report.get("case_count") != len(cases):
        raise ValueError("conversation report case count does not match its rows")
    return report


def build_review_template(report_path: Path) -> OwnerSemanticReview:
    report = _load_report(report_path)
    return OwnerSemanticReview(
        review_version="firelens_owner_semantic_review.v1",
        report_sha256=file_sha256(report_path),
        cases=[
            CaseReview(
                case_id=str(case["id"]),
                claims=[
                    ClaimReview(claim_id=str(claim["claim_id"]))
                    for claim in case.get("claims", [])
                ],
            )
            for case in report["cases"]
        ],
    )


def write_review_template(report_path: Path, output_path: Path) -> OwnerSemanticReview:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing owner review: {output_path}")
    review = build_review_template(report_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(
            review.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return review


def validate_owner_review(
    report_path: Path,
    review_path: Path,
    *,
    expected_case_count: int = 50,
) -> dict[str, Any]:
    report = _load_report(report_path)
    review = OwnerSemanticReview.model_validate(
        yaml.safe_load(review_path.read_text(encoding="utf-8"))
    )
    actual_report_sha256 = file_sha256(report_path)
    if review.report_sha256 != actual_report_sha256:
        raise ValueError("owner review does not match the benchmark report hash")

    report_cases = {str(case["id"]): case for case in report["cases"]}
    review_cases = {case.case_id: case for case in review.cases}
    if report_cases.keys() != review_cases.keys():
        missing = sorted(report_cases.keys() - review_cases.keys())
        unknown = sorted(review_cases.keys() - report_cases.keys())
        raise ValueError(f"owner review case mismatch; missing={missing}, unknown={unknown}")

    case_results = []
    unsupported_verified_claim_count = 0
    unclear_claim_count = 0
    for case_id, report_case in report_cases.items():
        case_review = review_cases[case_id]
        report_claims = {
            str(claim["claim_id"]): claim for claim in report_case.get("claims", [])
        }
        claim_reviews = {claim.claim_id: claim for claim in case_review.claims}
        if report_claims.keys() != claim_reviews.keys():
            missing = sorted(report_claims.keys() - claim_reviews.keys())
            unknown = sorted(claim_reviews.keys() - report_claims.keys())
            raise ValueError(
                f"owner review claim mismatch for {case_id}; missing={missing}, unknown={unknown}"
            )
        for claim_id, claim_review in claim_reviews.items():
            if claim_review.decision == "unclear":
                unclear_claim_count += 1
            if (
                claim_review.decision == "unsupported"
                and report_claims[claim_id].get("evidence_status") == "verified_corpus"
            ):
                unsupported_verified_claim_count += 1
        approved = bool(
            case_review.decision == "approve"
            and case_review.required_concepts_present
            and case_review.forbidden_claims_absent
            and case_review.required_limitations_present
            and all(claim.decision == "supported" for claim in case_review.claims)
        )
        case_results.append(
            {
                "case_id": case_id,
                "approved": approved,
                "decision": case_review.decision,
                "claim_count": len(case_review.claims),
            }
        )

    approved_case_count = sum(1 for case in case_results if case["approved"] is True)
    live_provider_report = report.get("execution_mode") == "live_provider"
    expected_case_count_present = len(case_results) == expected_case_count
    qualified = bool(
        review.reviewer
        and review.reviewed_at
        and live_provider_report
        and expected_case_count_present
        and report.get("complete")
        and not report.get("cost_budget_exceeded")
        and approved_case_count == len(case_results)
        and unsupported_verified_claim_count == 0
        and unclear_claim_count == 0
    )
    return {
        "summary_version": "firelens_owner_semantic_review_summary.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "report_sha256": actual_report_sha256,
        "review_sha256": file_sha256(review_path),
        "reviewer_present": bool(review.reviewer),
        "reviewed_at_present": review.reviewed_at is not None,
        "live_provider_report": live_provider_report,
        "expected_case_count": expected_case_count,
        "expected_case_count_present": expected_case_count_present,
        "case_count": len(case_results),
        "approved_case_count": approved_case_count,
        "unsupported_verified_claim_count": unsupported_verified_claim_count,
        "unclear_claim_count": unclear_claim_count,
        "qualified": qualified,
        "cases": case_results,
    }
