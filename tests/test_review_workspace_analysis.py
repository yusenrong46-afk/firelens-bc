from __future__ import annotations

import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from firelens.review_workspace.analysis import (
    verify_review_analysis,
    write_review_analysis,
)
from firelens.review_workspace.exports import write_finalized_evidence_export
from firelens.review_workspace.inputs import (
    BlindCasePayload,
    BlindClaim,
    BlindRubric,
    ImportedReviewCase,
    InputFileIdentity,
    _build_suite,
    canonical_sha256,
)
from firelens.review_workspace.models import ReviewActor, ReviewSession
from firelens.review_workspace.session import (
    BlindReviewSession,
    ClaimAssessment,
    ReviewDecision,
)

START = datetime(2026, 8, 8, 19, 0, tzinfo=UTC)


def _suite(tmp_path: Path, *, retrieval: bool = False):
    source = tmp_path / ("retrieval-input.json" if retrieval else "semantic-input.json")
    source.write_text('{"fixture":true}\n', encoding="utf-8")
    metadata = source.stat()
    identity = InputFileIdentity(
        label="fixture",
        absolute_path=str(source.resolve()),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        size=metadata.st_size,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    cases = []
    for index in range(1 if retrieval else 2):
        payload = BlindCasePayload(
            question=f"PRIVATE QUESTION {index}",
            history=(),
            rubric=BlindRubric(
                required_concepts=("scope",),
                forbidden_claims=("certainty",),
                required_limitations=("investigative only",),
            ),
            answer=None if retrieval else f"PRIVATE ANSWER {index}",
            claims=(
                ()
                if retrieval
                else (BlindClaim(claim_id=f"claim-{index}", text="PRIVATE CLAIM"),)
            ),
            supports=(),
            local_source_context=(),
        )
        case_id = f"case-{index + 1:03d}"
        cases.append(
            ImportedReviewCase(
                case_id=case_id,
                payload=payload,
                payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
                source_id_sha256s=(),
            )
        )
    return _build_suite(
        suite_kind="retrieval" if retrieval else "semantic_holdout",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256="d" * 64,
        input_files=(identity,),
        cases=tuple(cases),
    )


def _session(suite, *, retrieval: bool = False) -> ReviewSession:
    return ReviewSession(
        session_version="firelens_review_session.v1",
        session_id="retrieval-analysis-001" if retrieval else "semantic-analysis-001",
        review_kind="retrieval" if retrieval else "semantic",
        artifact_sha256=suite.suite_sha256,
        protocol_sha256="a" * 64,
        created_at=START,
        case_ids=tuple(case.case_id for case in suite.cases),
        actors=(
            ReviewActor(actor_id="reviewer-a", display_name="Alice Reviewer", role="reviewer"),
            ReviewActor(actor_id="reviewer-b", display_name="Bob Reviewer", role="reviewer"),
            ReviewActor(
                actor_id="adjudicator",
                display_name="Casey Adjudicator",
                role="adjudicator",
            ),
        ),
    )


def _semantic_decision(
    case_id: str,
    *,
    disposition: str = "approve",
    required_concepts_present: bool = True,
    claim_decision: str = "supported",
) -> ReviewDecision:
    index = int(case_id.rsplit("-", 1)[1]) - 1
    return ReviewDecision(
        disposition=disposition,
        required_concepts_present=required_concepts_present,
        forbidden_claims_absent=True,
        required_limitations_present=True,
        claims=(
            ClaimAssessment(
                claim_id=f"claim-{index}",
                decision=claim_decision,
                notes="PRIVATE REVIEWER NOTE MUST NOT ENTER ANALYSIS",
            ),
        ),
        notes="PRIVATE CASE NOTE MUST NOT ENTER ANALYSIS",
    )


def _retrieval_decision() -> ReviewDecision:
    return ReviewDecision(
        disposition="approve",
        question_is_independent=True,
        answerability_correct=True,
        acceptable_evidence_correct=True,
        claims=(),
        notes="PRIVATE RETRIEVAL NOTE MUST NOT ENTER ANALYSIS",
    )


def _finish(
    coordinator: BlindReviewSession,
    decisions: dict[str, dict[str, ReviewDecision]],
) -> None:
    for actor_id in ("reviewer-a", "reviewer-b"):
        while coordinator.progress(actor_id).actor_state != "complete_pending_lock":
            presentation = coordinator.present_next(actor_id)
            coordinator.acknowledge_display(actor_id, presentation.presentation_id)
            coordinator.record_decision(
                actor_id,
                presentation.presentation_id,
                decisions[actor_id][presentation.case_id],
            )
        coordinator.lock_reviewer(actor_id)
    while coordinator.progress("adjudicator").actor_state != "complete_pending_lock":
        presentation = coordinator.present_next("adjudicator")
        coordinator.acknowledge_display("adjudicator", presentation.presentation_id)
        coordinator.record_decision(
            "adjudicator",
            presentation.presentation_id,
            decisions["adjudicator"][presentation.case_id],
        )
    coordinator.finalize_adjudication("adjudicator")


def _semantic_workspace(tmp_path: Path) -> Path:
    suite = _suite(tmp_path)
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 100))
    workspace = tmp_path / "semantic-workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite),
        suite=suite,
        clock=lambda: next(ticks),
    )
    case_one = "case-001"
    case_two = "case-002"
    approve_one = _semantic_decision(case_one)
    decisions = {
        "reviewer-a": {
            case_one: approve_one,
            case_two: _semantic_decision(case_two),
        },
        "reviewer-b": {
            case_one: approve_one,
            case_two: _semantic_decision(
                case_two,
                disposition="reject",
                required_concepts_present=False,
                claim_decision="unsupported",
            ),
        },
        "adjudicator": {
            case_one: approve_one,
            case_two: _semantic_decision(
                case_two,
                disposition="reject",
                required_concepts_present=False,
                claim_decision="unsupported",
            ),
        },
    }
    _finish(coordinator, decisions)
    write_finalized_evidence_export(
        coordinator,
        clock=lambda: START + timedelta(minutes=5),
    )
    return workspace


def test_analysis_recomputes_agreement_without_copying_review_content(
    tmp_path: Path,
) -> None:
    workspace = _semantic_workspace(tmp_path)
    receipt = write_review_analysis(
        workspace,
        clock=lambda: START + timedelta(minutes=6),
    )
    analysis, verified = verify_review_analysis(workspace)

    assert verified == receipt
    assert analysis.qualification_eligible is False
    assert analysis.case_count == 2
    assert analysis.disposition_agreement.agreement_count == 1
    assert analysis.disposition_agreement.agreement_rate == 0.5
    assert analysis.disposition_agreement.cohen_kappa == 0.0
    assert analysis.rubric_agreement.agreement_count == 5
    assert analysis.rubric_agreement.item_count == 6
    assert analysis.claim_agreement.agreement_count == 1
    assert analysis.claim_agreement.item_count == 2
    assert analysis.full_label_agreement_count == 1
    assert analysis.initial_disagreement_case_count == 1
    assert analysis.disagreement_case_ids == ("case-002",)
    assert analysis.adjudicated_finding_case_count == 1
    assert analysis.finding_case_ids == ("case-002",)
    assert analysis.adjudicated_unsupported_claim_count == 1
    assert analysis.adjudicated_unclear_claim_count == 0
    assert analysis.all_adjudicated_cases_clear is False
    assert analysis.cases[1].adjudicator_alignment == "matches_reviewer_b"

    analysis_path = workspace / "exports/review-analysis.json"
    raw = analysis_path.read_text(encoding="utf-8")
    assert "PRIVATE QUESTION" not in raw
    assert "PRIVATE ANSWER" not in raw
    assert "PRIVATE REVIEWER NOTE" not in raw
    assert stat.S_IMODE(analysis_path.stat().st_mode) == 0o600
    assert (
        stat.S_IMODE((workspace / "exports/review-analysis.receipt.json").stat().st_mode)
        == 0o600
    )
    with pytest.raises(FileExistsError, match="overwrite"):
        write_review_analysis(workspace)


def test_retrieval_analysis_handles_no_claim_items(tmp_path: Path) -> None:
    suite = _suite(tmp_path, retrieval=True)
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 100))
    workspace = tmp_path / "retrieval-workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite, retrieval=True),
        suite=suite,
        clock=lambda: next(ticks),
    )
    decisions = {
        actor_id: {"case-001": _retrieval_decision()}
        for actor_id in ("reviewer-a", "reviewer-b", "adjudicator")
    }
    _finish(coordinator, decisions)
    write_finalized_evidence_export(coordinator)
    write_review_analysis(workspace)
    analysis, _receipt = verify_review_analysis(workspace)

    assert analysis.suite_kind == "retrieval"
    assert analysis.claim_agreement.item_count == 0
    assert analysis.claim_agreement.agreement_rate is None
    assert analysis.claim_agreement.cohen_kappa is None
    assert analysis.claim_agreement.kappa_status == "no_items"
    assert analysis.all_adjudicated_cases_clear is True


def test_analysis_mutation_is_rejected_against_source_evidence(tmp_path: Path) -> None:
    workspace = _semantic_workspace(tmp_path)
    write_review_analysis(
        workspace,
        clock=lambda: START + timedelta(minutes=6),
    )
    analysis_path = workspace / "exports/review-analysis.json"
    document = json.loads(analysis_path.read_text(encoding="utf-8"))
    document["initial_disagreement_case_count"] = 0
    analysis_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="differs"):
        verify_review_analysis(workspace)


def test_analysis_clock_cannot_predate_finalized_export(tmp_path: Path) -> None:
    workspace = _semantic_workspace(tmp_path)

    with pytest.raises(ValueError, match="predate"):
        write_review_analysis(
            workspace,
            clock=lambda: START + timedelta(minutes=4),
        )
    assert not (workspace / "exports/review-analysis.json").exists()


def test_analysis_requires_a_verified_finalized_export(tmp_path: Path) -> None:
    workspace = tmp_path / "empty-workspace"
    workspace.mkdir(mode=0o700)

    with pytest.raises(FileNotFoundError):
        write_review_analysis(workspace)
