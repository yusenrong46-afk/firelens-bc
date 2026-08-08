from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from firelens.review_workspace.exports import (
    verify_finalized_evidence_export,
    write_finalized_evidence_export,
)
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
    ReviewSessionError,
)

START = datetime(2026, 8, 7, 16, 0, tzinfo=UTC)


def _suite(tmp_path: Path):
    source = tmp_path / "bound-input.json"
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
    payload = BlindCasePayload(
        question="What does the reviewed evidence establish?",
        history=(),
        rubric=BlindRubric(
            required_concepts=("scope",),
            forbidden_claims=("emergency certainty",),
            required_limitations=("investigative only",),
        ),
        answer="The evidence supports a scoped investigative conclusion.",
        claims=(BlindClaim(claim_id="claim-1", text="Scoped conclusion"),),
        supports=(),
        local_source_context=(),
    )
    case = ImportedReviewCase(
        case_id="case-001",
        payload=payload,
        payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
        source_id_sha256s=(),
    )
    return _build_suite(
        suite_kind="semantic_holdout",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256="d" * 64,
        input_files=(identity,),
        cases=(case,),
    )


def _session(suite) -> ReviewSession:
    return ReviewSession(
        session_version="firelens_review_session.v1",
        session_id="semantic-session-001",
        review_kind="semantic",
        artifact_sha256=suite.suite_sha256,
        protocol_sha256="a" * 64,
        created_at=START,
        case_ids=("case-001",),
        actors=(
            ReviewActor(actor_id="reviewer-a", display_name="Reviewer A", role="reviewer"),
            ReviewActor(actor_id="reviewer-b", display_name="Reviewer B", role="reviewer"),
            ReviewActor(actor_id="adjudicator", display_name="Adjudicator", role="adjudicator"),
        ),
    )


def _decision() -> ReviewDecision:
    return ReviewDecision(
        disposition="approve",
        required_concepts_present=True,
        forbidden_claims_absent=True,
        required_limitations_present=True,
        claims=(ClaimAssessment(claim_id="claim-1", decision="supported"),),
    )


def _complete(coordinator: BlindReviewSession) -> None:
    for actor_id in ("reviewer-a", "reviewer-b"):
        presentation = coordinator.present_next(actor_id)
        coordinator.acknowledge_display(actor_id, presentation.presentation_id)
        coordinator.record_decision(actor_id, presentation.presentation_id, _decision())
        coordinator.lock_reviewer(actor_id)
    adjudication = coordinator.present_next("adjudicator")
    coordinator.acknowledge_display("adjudicator", adjudication.presentation_id)
    coordinator.record_decision("adjudicator", adjudication.presentation_id, _decision())
    coordinator.finalize_adjudication("adjudicator")


def test_complete_blind_review_is_receipt_bound_and_stays_nonqualifying(
    tmp_path: Path,
) -> None:
    suite = _suite(tmp_path)
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 20))
    workspace = tmp_path / "workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite),
        suite=suite,
        clock=lambda: next(ticks),
    )

    with pytest.raises(ReviewSessionError, match="blocked"):
        coordinator.present_next("adjudicator")

    for actor_id in ("reviewer-a", "reviewer-b"):
        presentation = coordinator.present_next(actor_id)
        assert presentation.review_material == ()
        coordinator.acknowledge_display(actor_id, presentation.presentation_id)
        coordinator.record_decision(actor_id, presentation.presentation_id, _decision())
        lock = coordinator.lock_reviewer(actor_id)
        assert lock.qualification_eligible is False

    adjudication = coordinator.present_next("adjudicator")
    assert [row.reviewer_slot for row in adjudication.review_material] == [
        "reviewer-a",
        "reviewer-b",
    ]
    coordinator.acknowledge_display("adjudicator", adjudication.presentation_id)
    coordinator.record_decision("adjudicator", adjudication.presentation_id, _decision())
    final = coordinator.finalize_adjudication("adjudicator")

    assert final.qualification_eligible is False
    assert coordinator.progress("adjudicator").session_state == "finalized"

    export = write_finalized_evidence_export(
        coordinator,
        clock=lambda: START + timedelta(minutes=1),
    )
    assert export.qualification_eligible is False
    evidence, verified = verify_finalized_evidence_export(workspace)
    assert verified == export
    assert evidence.actors[-1].actor.role == "adjudicator"
    assert evidence.actors[-1].decisions[0].decision.disposition == "approve"
    with pytest.raises(FileExistsError, match="overwrite"):
        write_finalized_evidence_export(coordinator)


def test_finalized_export_detects_post_export_mutation(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 30))
    workspace = tmp_path / "workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite),
        suite=suite,
        clock=lambda: next(ticks),
    )
    _complete(coordinator)
    write_finalized_evidence_export(coordinator)
    evidence_path = workspace / "exports" / "finalized-evidence.json"
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")

    with pytest.raises(ValueError, match="canonical"):
        verify_finalized_evidence_export(workspace)


def test_receipt_roster_detects_journal_deletion(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    workspace = tmp_path / "workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite),
        suite=suite,
        clock=lambda: START + timedelta(seconds=1),
    )
    coordinator.present_next("reviewer-a")
    (workspace / "journals" / "reviewer-a.jsonl").unlink()

    with pytest.raises(ReviewSessionError, match="head/count"):
        coordinator.progress("reviewer-a")


def test_bound_input_mutation_stops_next_exposure(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    workspace = tmp_path / "workspace"
    coordinator = BlindReviewSession.create(
        workspace,
        session=_session(suite),
        suite=suite,
    )
    Path(suite.input_files[0].absolute_path).write_text('{"fixture":false}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="identity changed"):
        coordinator.present_next("reviewer-a")
