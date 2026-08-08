"""Deterministic, content-free analysis of finalized blind human review evidence.

The analysis reports agreement, disagreement, and adjudicated finding counts. It
does not copy questions, answers, source passages, or reviewer notes, and it does
not convert the review workspace scaffold into release-qualifying evidence.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from firelens.review_workspace.exports import (
    FinalizedEvidenceExportReceipt,
    read_private_canonical,
    verify_finalized_evidence_export,
)
from firelens.review_workspace.journal import create_immutable_json
from firelens.review_workspace.session import (
    FinalizedActorEvidence,
    FinalizedReviewEvidence,
    ReviewDecision,
)

_ANALYSIS_PATH: Literal["exports/review-analysis.json"] = "exports/review-analysis.json"
_ANALYSIS_RECEIPT_PATH: Literal["exports/review-analysis.receipt.json"] = (
    "exports/review-analysis.receipt.json"
)
_EXPORT_RECEIPT_PATH = "exports/finalized-evidence.receipt.json"
_Model = TypeVar("_Model", bound=BaseModel)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgreementMetric(_FrozenModel):
    item_count: int = Field(ge=0, strict=True)
    agreement_count: int = Field(ge=0, strict=True)
    agreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    cohen_kappa: float | None = Field(default=None, ge=-1.0, le=1.0)
    kappa_status: Literal["defined", "no_items", "degenerate_marginals"]


class ReviewActorSummary(_FrozenModel):
    actor_id: str
    display_name: str
    role: Literal["reviewer", "adjudicator"]
    journal_count: int = Field(ge=1, strict=True)
    journal_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CaseReviewAnalysis(_FrozenModel):
    case_id: str
    reviewer_a_disposition: Literal["approve", "reject", "needs_discussion"]
    reviewer_b_disposition: Literal["approve", "reject", "needs_discussion"]
    adjudicator_disposition: Literal["approve", "reject", "needs_discussion"]
    disposition_agreement: bool
    full_label_agreement: bool
    rubric_item_count: int = Field(ge=3, le=3, strict=True)
    rubric_agreement_count: int = Field(ge=0, le=3, strict=True)
    claim_item_count: int = Field(ge=0, strict=True)
    claim_agreement_count: int = Field(ge=0, strict=True)
    adjudicator_alignment: Literal[
        "matches_both",
        "matches_reviewer_a",
        "matches_reviewer_b",
        "independent_resolution",
    ]
    adjudicated_finding_present: bool
    adjudicator_needs_discussion: bool
    decision_event_hashes: dict[str, str] = Field(min_length=3, max_length=3)


class ReviewAnalysis(_FrozenModel):
    analysis_version: Literal["firelens_review_analysis.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    limitation: Literal[
        "This content-free analysis is derived from nonqualifying workspace evidence and is not a release-gate sidecar."
    ]
    generated_at: datetime
    session_id: str
    suite_kind: Literal["conversation", "retrieval", "semantic_holdout"]
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_export_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actors: tuple[ReviewActorSummary, ...] = Field(min_length=3, max_length=3)
    case_count: int = Field(ge=1, strict=True)
    disposition_agreement: AgreementMetric
    rubric_agreement: AgreementMetric
    claim_agreement: AgreementMetric
    full_label_agreement_count: int = Field(ge=0, strict=True)
    initial_disagreement_case_count: int = Field(ge=0, strict=True)
    adjudicator_override_on_agreement_count: int = Field(ge=0, strict=True)
    adjudicated_finding_case_count: int = Field(ge=0, strict=True)
    adjudicator_needs_discussion_case_count: int = Field(ge=0, strict=True)
    adjudicated_unsupported_claim_count: int = Field(ge=0, strict=True)
    adjudicated_unclear_claim_count: int = Field(ge=0, strict=True)
    all_adjudicated_cases_clear: bool
    disagreement_case_ids: tuple[str, ...]
    finding_case_ids: tuple[str, ...]
    cases: tuple[CaseReviewAnalysis, ...] = Field(min_length=1)


class ReviewAnalysisReceipt(_FrozenModel):
    receipt_version: Literal["firelens_review_analysis_receipt.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session_id: str
    analysis_relative_path: Literal["exports/review-analysis.json"]
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_byte_count: int = Field(ge=1, strict=True)
    source_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_export_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review analysis clock must return an offset-aware timestamp")
    return value.astimezone(UTC)


def _agreement_metric(
    left: Iterable[str],
    right: Iterable[str],
) -> AgreementMetric:
    left_labels = tuple(left)
    right_labels = tuple(right)
    if len(left_labels) != len(right_labels):
        raise ValueError("review agreement label rosters differ")
    item_count = len(left_labels)
    agreement_count = sum(
        left_label == right_label
        for left_label, right_label in zip(left_labels, right_labels, strict=True)
    )
    if item_count == 0:
        return AgreementMetric(
            item_count=0,
            agreement_count=0,
            agreement_rate=None,
            cohen_kappa=None,
            kappa_status="no_items",
        )
    observed = agreement_count / item_count
    left_counts = Counter(left_labels)
    right_counts = Counter(right_labels)
    categories = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[category] / item_count) * (right_counts[category] / item_count)
        for category in categories
    )
    if abs(1.0 - expected) < 1e-12:
        kappa = None
        status: Literal["defined", "no_items", "degenerate_marginals"] = "degenerate_marginals"
    else:
        kappa = round((observed - expected) / (1.0 - expected), 12)
        status = "defined"
    return AgreementMetric(
        item_count=item_count,
        agreement_count=agreement_count,
        agreement_rate=round(observed, 12),
        cohen_kappa=kappa,
        kappa_status=status,
    )


def _decisions_by_case(actor: FinalizedActorEvidence) -> dict[str, ReviewDecision]:
    decisions = {row.case_id: row.decision for row in actor.decisions}
    if len(decisions) != len(actor.decisions):
        raise ValueError("finalized review evidence repeats an actor case decision")
    return decisions


def _event_hashes_by_case(actor: FinalizedActorEvidence) -> dict[str, str]:
    return {row.case_id: row.event_hash for row in actor.decisions}


def _label_signature(decision: ReviewDecision) -> tuple[object, ...]:
    return (
        decision.disposition,
        decision.required_concepts_present,
        decision.forbidden_claims_absent,
        decision.required_limitations_present,
        decision.question_is_independent,
        decision.answerability_correct,
        decision.acceptable_evidence_correct,
        tuple((claim.claim_id, claim.decision) for claim in decision.claims),
    )


def _rubric_labels(decision: ReviewDecision, *, retrieval: bool) -> tuple[str, str, str]:
    values = (
        (
            decision.question_is_independent,
            decision.answerability_correct,
            decision.acceptable_evidence_correct,
        )
        if retrieval
        else (
            decision.required_concepts_present,
            decision.forbidden_claims_absent,
            decision.required_limitations_present,
        )
    )
    if any(value is None for value in values):
        raise ValueError("finalized review evidence omits an applicable rubric decision")
    return tuple("true" if value else "false" for value in values)  # type: ignore[return-value]


def _claim_labels(decision: ReviewDecision) -> tuple[tuple[str, str], ...]:
    return tuple((claim.claim_id, claim.decision) for claim in decision.claims)


def _finding_present(decision: ReviewDecision, *, retrieval: bool) -> bool:
    rubric = _rubric_labels(decision, retrieval=retrieval)
    return bool(
        decision.disposition != "approve"
        or any(value != "true" for value in rubric)
        or any(claim.decision != "supported" for claim in decision.claims)
    )


def _build_analysis(
    evidence: FinalizedReviewEvidence,
    *,
    source_evidence_sha256: str,
    source_export_receipt_sha256: str,
    generated_at: datetime,
) -> ReviewAnalysis:
    reviewers = tuple(actor for actor in evidence.actors if actor.actor.role == "reviewer")
    adjudicators = tuple(
        actor for actor in evidence.actors if actor.actor.role == "adjudicator"
    )
    if len(reviewers) != 2 or len(adjudicators) != 1:
        raise ValueError("review analysis requires two reviewers and one adjudicator")
    reviewer_a, reviewer_b = reviewers
    adjudicator = adjudicators[0]
    case_roster = tuple(evidence.session.case_ids)
    actor_maps = {actor.actor.actor_id: _decisions_by_case(actor) for actor in evidence.actors}
    if any(set(decisions) != set(case_roster) for decisions in actor_maps.values()):
        raise ValueError("finalized review evidence case rosters differ")
    event_hash_maps = {
        actor.actor.actor_id: _event_hashes_by_case(actor) for actor in evidence.actors
    }
    retrieval = evidence.suite_kind == "retrieval"
    disposition_left: list[str] = []
    disposition_right: list[str] = []
    rubric_left: list[str] = []
    rubric_right: list[str] = []
    claim_left: list[str] = []
    claim_right: list[str] = []
    cases: list[CaseReviewAnalysis] = []
    disagreement_ids: list[str] = []
    finding_ids: list[str] = []
    override_count = 0
    unsupported_claims = 0
    unclear_claims = 0

    for case_id in case_roster:
        left = actor_maps[reviewer_a.actor.actor_id][case_id]
        right = actor_maps[reviewer_b.actor.actor_id][case_id]
        final = actor_maps[adjudicator.actor.actor_id][case_id]
        left_rubric = _rubric_labels(left, retrieval=retrieval)
        right_rubric = _rubric_labels(right, retrieval=retrieval)
        left_claims = _claim_labels(left)
        right_claims = _claim_labels(right)
        if tuple(item[0] for item in left_claims) != tuple(item[0] for item in right_claims):
            raise ValueError("reviewer claim rosters differ")
        disposition_left.append(left.disposition)
        disposition_right.append(right.disposition)
        rubric_left.extend(left_rubric)
        rubric_right.extend(right_rubric)
        claim_left.extend(item[1] for item in left_claims)
        claim_right.extend(item[1] for item in right_claims)
        left_signature = _label_signature(left)
        right_signature = _label_signature(right)
        final_signature = _label_signature(final)
        full_agreement = left_signature == right_signature
        if not full_agreement:
            disagreement_ids.append(case_id)
        alignment: Literal[
            "matches_both",
            "matches_reviewer_a",
            "matches_reviewer_b",
            "independent_resolution",
        ]
        if final_signature == left_signature == right_signature:
            alignment = "matches_both"
        elif final_signature == left_signature:
            alignment = "matches_reviewer_a"
        elif final_signature == right_signature:
            alignment = "matches_reviewer_b"
        else:
            alignment = "independent_resolution"
        if full_agreement and final_signature != left_signature:
            override_count += 1
        finding = _finding_present(final, retrieval=retrieval)
        if finding:
            finding_ids.append(case_id)
        unsupported_claims += sum(claim.decision == "unsupported" for claim in final.claims)
        unclear_claims += sum(claim.decision == "unclear" for claim in final.claims)
        cases.append(
            CaseReviewAnalysis(
                case_id=case_id,
                reviewer_a_disposition=left.disposition,
                reviewer_b_disposition=right.disposition,
                adjudicator_disposition=final.disposition,
                disposition_agreement=left.disposition == right.disposition,
                full_label_agreement=full_agreement,
                rubric_item_count=3,
                rubric_agreement_count=sum(
                    left_value == right_value
                    for left_value, right_value in zip(left_rubric, right_rubric, strict=True)
                ),
                claim_item_count=len(left_claims),
                claim_agreement_count=sum(
                    left_value == right_value
                    for left_value, right_value in zip(left_claims, right_claims, strict=True)
                ),
                adjudicator_alignment=alignment,
                adjudicated_finding_present=finding,
                adjudicator_needs_discussion=final.disposition == "needs_discussion",
                decision_event_hashes={
                    actor.actor.actor_id: event_hash_maps[actor.actor.actor_id][case_id]
                    for actor in evidence.actors
                },
            )
        )

    return ReviewAnalysis(
        analysis_version="firelens_review_analysis.v1",
        implementation_status="nonqualifying_backend_scaffold",
        qualification_eligible=False,
        limitation=(
            "This content-free analysis is derived from nonqualifying workspace evidence and "
            "is not a release-gate sidecar."
        ),
        generated_at=_as_utc(generated_at),
        session_id=evidence.session.session_id,
        suite_kind=evidence.suite_kind,
        suite_sha256=evidence.suite_sha256,
        dataset_sha256=evidence.dataset_sha256,
        source_evidence_sha256=source_evidence_sha256,
        source_export_receipt_sha256=source_export_receipt_sha256,
        actors=tuple(
            ReviewActorSummary(
                actor_id=actor.actor.actor_id,
                display_name=actor.actor.display_name,
                role=cast(
                    Literal["reviewer", "adjudicator"],
                    actor.actor.role,
                ),
                journal_count=actor.journal_count,
                journal_head_hash=actor.journal_head_hash,
            )
            for actor in evidence.actors
        ),
        case_count=len(case_roster),
        disposition_agreement=_agreement_metric(disposition_left, disposition_right),
        rubric_agreement=_agreement_metric(rubric_left, rubric_right),
        claim_agreement=_agreement_metric(claim_left, claim_right),
        full_label_agreement_count=sum(case.full_label_agreement for case in cases),
        initial_disagreement_case_count=len(disagreement_ids),
        adjudicator_override_on_agreement_count=override_count,
        adjudicated_finding_case_count=len(finding_ids),
        adjudicator_needs_discussion_case_count=sum(
            case.adjudicator_needs_discussion for case in cases
        ),
        adjudicated_unsupported_claim_count=unsupported_claims,
        adjudicated_unclear_claim_count=unclear_claims,
        all_adjudicated_cases_clear=not finding_ids,
        disagreement_case_ids=tuple(disagreement_ids),
        finding_case_ids=tuple(finding_ids),
        cases=tuple(cases),
    )


def _source_receipt_sha256(directory: Path) -> str:
    _receipt, raw = read_private_canonical(
        directory / _EXPORT_RECEIPT_PATH,
        FinalizedEvidenceExportReceipt,
    )
    return hashlib.sha256(raw).hexdigest()


def write_review_analysis(
    directory: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ReviewAnalysisReceipt:
    """Create one immutable analysis and receipt after export verification."""

    analysis_path = directory / _ANALYSIS_PATH
    receipt_path = directory / _ANALYSIS_RECEIPT_PATH
    if analysis_path.exists() or analysis_path.is_symlink():
        raise FileExistsError("refusing to overwrite review analysis")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise FileExistsError("refusing to overwrite review analysis receipt")
    evidence, export_receipt = verify_finalized_evidence_export(directory)
    source_receipt_sha256 = _source_receipt_sha256(directory)
    generated_at = _as_utc(clock())
    if generated_at < export_receipt.exported_at:
        raise ValueError("review analysis cannot predate the finalized evidence export")
    analysis = _build_analysis(
        evidence,
        source_evidence_sha256=export_receipt.evidence_sha256,
        source_export_receipt_sha256=source_receipt_sha256,
        generated_at=generated_at,
    )
    path = create_immutable_json(
        directory,
        _ANALYSIS_PATH,
        analysis,
        max_bytes=16 * 1024 * 1024,
    )
    _stored, raw = read_private_canonical(path, ReviewAnalysis)
    receipt = ReviewAnalysisReceipt(
        receipt_version="firelens_review_analysis_receipt.v1",
        implementation_status="nonqualifying_backend_scaffold",
        qualification_eligible=False,
        session_id=analysis.session_id,
        analysis_relative_path=_ANALYSIS_PATH,
        analysis_sha256=hashlib.sha256(raw).hexdigest(),
        analysis_byte_count=len(raw),
        source_evidence_sha256=export_receipt.evidence_sha256,
        source_export_receipt_sha256=source_receipt_sha256,
        generated_at=analysis.generated_at,
    )
    create_immutable_json(directory, _ANALYSIS_RECEIPT_PATH, receipt)
    verify_review_analysis(directory)
    return receipt


def verify_review_analysis(
    directory: Path,
) -> tuple[ReviewAnalysis, ReviewAnalysisReceipt]:
    """Recompute all metrics and bindings from the finalized evidence export."""

    evidence, export_receipt = verify_finalized_evidence_export(directory)
    source_receipt_sha256 = _source_receipt_sha256(directory)
    analysis, raw = read_private_canonical(
        directory / _ANALYSIS_PATH,
        ReviewAnalysis,
    )
    receipt, _receipt_raw = read_private_canonical(
        directory / _ANALYSIS_RECEIPT_PATH,
        ReviewAnalysisReceipt,
    )
    if analysis.generated_at < export_receipt.exported_at:
        raise ValueError("review analysis predates the finalized evidence export")
    recomputed = _build_analysis(
        evidence,
        source_evidence_sha256=export_receipt.evidence_sha256,
        source_export_receipt_sha256=source_receipt_sha256,
        generated_at=analysis.generated_at,
    )
    if analysis != recomputed:
        raise ValueError("review analysis differs from finalized evidence")
    expected = {
        "session_id": analysis.session_id,
        "analysis_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_byte_count": len(raw),
        "source_evidence_sha256": export_receipt.evidence_sha256,
        "source_export_receipt_sha256": source_receipt_sha256,
        "generated_at": analysis.generated_at,
    }
    for key, value in expected.items():
        if getattr(receipt, key) != value:
            raise ValueError(f"review analysis receipt disagrees with {key}")
    return analysis, receipt
