"""Pure construction and verification helpers for finalized review evidence."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from firelens.review_workspace.inputs import ImportedReviewSuite, input_file_roster_sha256
from firelens.review_workspace.models import ReviewActor, ReviewJournalEvent, ReviewSession
from firelens.review_workspace.session_common import (
    _IMPLEMENTATION_STATUS,
    EventHeadReceipt,
    FinalizedActorEvidence,
    FinalizedCaseDecision,
    FinalizedReviewEvidence,
    ReviewDecision,
    ReviewerLockReceipt,
    ReviewSessionError,
    SessionFinalizationReceipt,
    _canonical_private_json,
    _DerivedActorState,
)


def build_finalized_evidence(
    *,
    session: ReviewSession,
    suite: ImportedReviewSuite,
    states: dict[str, _DerivedActorState],
    finalization: SessionFinalizationReceipt,
) -> FinalizedReviewEvidence:
    """Build the canonical nonqualifying evidence snapshot from replayed state."""

    actors: list[FinalizedActorEvidence] = []
    for actor in session.actors:
        state = states[actor.actor_id]
        decision_events = tuple(
            FinalizedCaseDecision(
                case_id=str(event.case_id),
                presentation_id=str(event.presentation_id),
                recorded_at=event.timestamp,
                event_hash=event.event_hash,
                decision=ReviewDecision.model_validate(event.payload["decision"]),
            )
            for event in state.events
            if event.event_type == "case.decision.recorded"
        )
        if len(decision_events) != len(state.order):
            raise ReviewSessionError("finalized actor decision roster is incomplete")
        actors.append(
            FinalizedActorEvidence(
                actor=actor,
                journal_count=len(state.events),
                journal_head_hash=state.events[-1].event_hash,
                decisions=decision_events,
            )
        )
    return FinalizedReviewEvidence(
        evidence_version="firelens_finalized_review_evidence.v1",
        implementation_status=_IMPLEMENTATION_STATUS,
        qualification_eligible=False,
        limitation=(
            "This export preserves finalized blind-review evidence but is not a "
            "release-gate sidecar. Independent storage review and explicit "
            "qualification integration remain required."
        ),
        session=session,
        suite_kind=suite.suite_kind,
        suite_sha256=suite.suite_sha256,
        dataset_sha256=suite.dataset_sha256,
        input_file_roster_sha256=input_file_roster_sha256(suite),
        finalization=finalization,
        actors=tuple(actors),
    )


def event_head_receipt(
    session: ReviewSession,
    suite: ImportedReviewSuite,
    journal_relative_path: str,
    actor: ReviewActor,
    event: ReviewJournalEvent,
) -> EventHeadReceipt:
    """Construct the immutable receipt corresponding to one journal head."""

    return EventHeadReceipt(
        receipt_version="firelens_review_event_head_receipt.v1",
        implementation_status=_IMPLEMENTATION_STATUS,
        qualification_eligible=False,
        session_id=session.session_id,
        actor_id=actor.actor_id,
        journal_relative_path=journal_relative_path,
        sequence=event.sequence,
        journal_count=event.sequence,
        journal_head_hash=event.event_hash,
        event_type=event.event_type,
        event_hash=event.event_hash,
        previous_event_hash=event.previous_event_hash,
        case_id=event.case_id,
        presentation_id=event.presentation_id,
        recorded_at=event.timestamp,
        suite_sha256=suite.suite_sha256,
        input_file_roster_sha256=input_file_roster_sha256(suite),
    )


def receipt_path(actor: ReviewActor, sequence: int) -> str:
    return f"receipts/{actor.actor_id}/{sequence:06d}.json"


def verify_event_receipts(
    directory: Path,
    receipt_name: re.Pattern[str],
    session: ReviewSession,
    suite: ImportedReviewSuite,
    journal_relative_path: str,
    actor: ReviewActor,
    events: tuple[ReviewJournalEvent, ...],
) -> None:
    """Verify that the private receipt roster exactly matches the journal."""

    receipt_directory = directory / "receipts" / actor.actor_id
    observed_sequences: list[int] = []
    if receipt_directory.exists():
        metadata = receipt_directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ReviewSessionError("event receipt directory is unsafe")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ReviewSessionError("event receipt directory must have mode 0700")
        for path in receipt_directory.iterdir():
            match = receipt_name.fullmatch(path.name)
            if match is None or path.is_symlink():
                raise ReviewSessionError("event receipt directory contains an unknown entry")
            observed_sequences.append(int(match.group("sequence")))
    expected_sequences = list(range(1, len(events) + 1))
    if sorted(observed_sequences) != expected_sequences:
        raise ReviewSessionError("journal head/count disagrees with immutable receipt roster")
    for event in events:
        actual = _canonical_private_json(
            directory / receipt_path(actor, event.sequence), EventHeadReceipt
        )
        expected = event_head_receipt(session, suite, journal_relative_path, actor, event)
        if actual != expected:
            raise ReviewSessionError("immutable event receipt differs from journal head")


def verify_reviewer_lock(
    directory: Path,
    session: ReviewSession,
    suite: ImportedReviewSuite,
    actor: ReviewActor,
    event: ReviewJournalEvent,
) -> None:
    """Verify one reviewer-lock receipt against its terminal journal event."""

    actual = _canonical_private_json(
        directory / f"locks/{actor.actor_id}.json", ReviewerLockReceipt
    )
    expected = ReviewerLockReceipt(
        receipt_version="firelens_reviewer_lock_receipt.v1",
        implementation_status=_IMPLEMENTATION_STATUS,
        qualification_eligible=False,
        session_id=session.session_id,
        actor_id=actor.actor_id,
        case_count=len(session.case_ids),
        journal_count=event.sequence,
        journal_head_hash=event.event_hash,
        suite_sha256=suite.suite_sha256,
        input_file_roster_sha256=input_file_roster_sha256(suite),
        locked_at=event.timestamp,
    )
    if actual != expected:
        raise ReviewSessionError("reviewer lock receipt differs from locked journal")


def verify_finalization(directory: Path, expected: SessionFinalizationReceipt) -> None:
    """Verify the immutable session-finalization receipt."""

    actual = _canonical_private_json(
        directory / "session/finalization.json", SessionFinalizationReceipt
    )
    if actual != expected:
        raise ReviewSessionError("session finalization receipt is inconsistent")
