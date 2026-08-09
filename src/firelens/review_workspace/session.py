"""Immutable blind-review session state machine.

This is a local backend scaffold, not release-qualifying review evidence.  It
wraps each journal append in a protocol transition, writes an immutable receipt
for every observed head/count, and refuses to continue if a journal and its
receipts disagree.  Event time comes only from the coordinator's clock; no
public transition accepts a caller-authored timestamp.
"""

# Compatibility imports preserve the public facade during the module split.
# ruff: noqa: I001

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from firelens.review_workspace.inputs import (
    ImportedReviewCase,
    ImportedReviewSuite,
    canonical_sha256,
    input_file_roster_sha256,
)
from firelens.review_workspace.journal import AppendOnlyReviewJournal, create_immutable_json
from firelens.review_workspace.models import (
    GENESIS_EVENT_HASH,
    ReviewActor,
    ReviewJournalEvent,
    ReviewSession,
)
from firelens.review_workspace.session_common import (
    _IMPLEMENTATION_STATUS,
    _RECEIPT_NAME,
    ActorProgress as _ActorProgress,
    AdjudicationMaterial as _AdjudicationMaterial,
    ClaimAssessment as _ClaimAssessment,
    EventHeadReceipt as _EventHeadReceipt,
    FinalizedActorEvidence as _FinalizedActorEvidence,
    FinalizedCaseDecision as _FinalizedCaseDecision,
    FinalizedReviewEvidence as _FinalizedReviewEvidence,
    ReviewDecision as _ReviewDecision,
    ReviewerLockReceipt as _ReviewerLockReceipt,
    ReviewPresentation as _ReviewPresentation,
    ReviewSessionError as _ReviewSessionError,
    SessionFinalizationReceipt as _SessionFinalizationReceipt,
    SessionGenesisReceipt as _SessionGenesisReceipt,
    _DerivedActorState,
    _canonical_private_json,
    _genesis,
    _utc,
    _validate_session,
    deterministic_actor_case_order as _deterministic_actor_case_order,
)
from firelens.review_workspace.session_evidence import (
    build_finalized_evidence,
    event_head_receipt,
    receipt_path,
    verify_event_receipts,
    verify_finalization,
    verify_reviewer_lock,
)
from firelens.review_workspace.session_journal import append_review_event

ActorProgress = _ActorProgress
AdjudicationMaterial = _AdjudicationMaterial
ClaimAssessment = _ClaimAssessment
EventHeadReceipt = _EventHeadReceipt
FinalizedActorEvidence = _FinalizedActorEvidence
FinalizedCaseDecision = _FinalizedCaseDecision
FinalizedReviewEvidence = _FinalizedReviewEvidence
ReviewDecision = _ReviewDecision
ReviewerLockReceipt = _ReviewerLockReceipt
ReviewPresentation = _ReviewPresentation
ReviewSessionError = _ReviewSessionError
SessionFinalizationReceipt = _SessionFinalizationReceipt
SessionGenesisReceipt = _SessionGenesisReceipt
deterministic_actor_case_order = _deterministic_actor_case_order


class BlindReviewSession:
    """A local, receipt-bound coordinator for one three-person review session."""

    def __init__(
        self,
        directory: Path,
        *,
        session: ReviewSession,
        suite: ImportedReviewSuite,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        _validate_session(session, suite)
        self.directory = directory
        self.session = session
        self.suite = suite
        self._clock = clock or (lambda: datetime.now(UTC))
        self._actors = {actor.actor_id: actor for actor in session.actors}
        self._expected_genesis = _genesis(session, suite)

    @classmethod
    def create(
        cls,
        directory: Path,
        *,
        session: ReviewSession,
        suite: ImportedReviewSuite,
        clock: Callable[[], datetime] | None = None,
    ) -> BlindReviewSession:
        """Create an immutable genesis receipt; never overwrite an existing session."""

        _validate_session(session, suite)
        suite.recheck_input_files()
        coordinator = cls(directory, session=session, suite=suite, clock=clock)
        create_immutable_json(
            directory,
            "session/genesis.json",
            coordinator._expected_genesis,
        )
        coordinator._verify_genesis()
        return coordinator

    @classmethod
    def resume(
        cls,
        directory: Path,
        *,
        session: ReviewSession,
        suite: ImportedReviewSuite,
        clock: Callable[[], datetime] | None = None,
    ) -> BlindReviewSession:
        coordinator = cls(directory, session=session, suite=suite, clock=clock)
        with coordinator._guard():
            coordinator._verify_genesis()
            coordinator._states()
        return coordinator

    def progress(self, actor_id: str) -> ActorProgress:
        with self._guard():
            self._verify_genesis()
            states = self._states()
            actor = self._actor(actor_id)
            state = states[actor_id]
            final = states[self._adjudicator().actor_id].locked_or_finalized
            both_locked = all(
                states[item.actor_id].locked_or_finalized for item in self._reviewers()
            )
            session_state: Literal["independent_review", "adjudicating", "finalized"]
            if final:
                session_state = "finalized"
            elif both_locked:
                session_state = "adjudicating"
            else:
                session_state = "independent_review"
            actor_state: Literal[
                "blocked_on_reviewer_locks",
                "awaiting_presentation",
                "awaiting_display_acknowledgement",
                "awaiting_decision",
                "complete_pending_lock",
                "locked",
                "finalized",
            ]
            if actor.role == "adjudicator" and not both_locked:
                actor_state = "blocked_on_reviewer_locks"
            elif state.locked_or_finalized:
                actor_state = "finalized" if actor.role == "adjudicator" else "locked"
            elif state.current_index == len(state.order):
                actor_state = "complete_pending_lock"
            elif state.open_event is None:
                actor_state = "awaiting_presentation"
            elif not state.acknowledged:
                actor_state = "awaiting_display_acknowledgement"
            else:
                actor_state = "awaiting_decision"
            return ActorProgress(
                session_state=session_state,
                actor_state=actor_state,
                actor_id=actor_id,
                completed_case_count=state.current_index,
                case_count=len(state.order),
                next_case_position=(
                    state.current_index + 1 if state.current_index < len(state.order) else None
                ),
            )

    def present_next(self, actor_id: str) -> ReviewPresentation:
        """Expose only the next deterministic case, once, after rechecking every input."""

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            state = states[actor_id]
            if actor.role == "adjudicator":
                self._require_reviewer_locks(states)
            if state.locked_or_finalized or state.current_index == len(state.order):
                raise ReviewSessionError("actor has no remaining case to present")
            if state.open_event is not None:
                raise ReviewSessionError(
                    "current case was already exposed; re-exposure is refused"
                )
            presentation = self._presentation(actor, state.current_index, states)
            event = self._append_event(
                actor,
                event_type="presentation.opened",
                case_id=presentation.case_id,
                presentation_id=presentation.presentation_id,
                payload={
                    "case_position": presentation.case_position,
                    "displayed_payload_sha256": presentation.displayed_payload_sha256,
                    "payload_sha256": presentation.payload_sha256,
                    "suite_sha256": self.suite.suite_sha256,
                    "input_file_roster_sha256": input_file_roster_sha256(self.suite),
                },
            )
            self._write_event_receipt(actor, event)
            return presentation

    def current_presentation(self, actor_id: str) -> ReviewPresentation:
        """Re-render only the actor's already-open case after a client restart.

        This does not append or advance the journal. The original open event and
        later display acknowledgement remain the authoritative evidence. Input
        identities and deterministic presentation identity are rechecked before
        any content is returned.
        """

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            if actor.role == "adjudicator":
                self._require_reviewer_locks(states)
            state = states[actor_id]
            if state.open_event is None or state.current_index >= len(state.order):
                raise ReviewSessionError("actor has no open presentation to recover")
            presentation = self._presentation(actor, state.current_index, states)
            if (
                state.open_event.case_id != presentation.case_id
                or state.open_event.presentation_id != presentation.presentation_id
                or state.open_event.payload.get("displayed_payload_sha256")
                != presentation.displayed_payload_sha256
            ):
                raise ReviewSessionError("open presentation differs from current inputs")
            return presentation

    def acknowledge_display(self, actor_id: str, presentation_id: str) -> ReviewJournalEvent:
        """Record an explicit display acknowledgement after the presentation opened."""

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            if actor.role == "adjudicator":
                self._require_reviewer_locks(states)
            state = states[actor_id]
            opened = self._require_open(state, presentation_id)
            if state.acknowledged:
                raise ReviewSessionError("presentation display was already acknowledged")
            event = self._append_event(
                actor,
                event_type="presentation.display_acknowledged",
                case_id=opened.case_id,
                presentation_id=presentation_id,
                payload={
                    "displayed_payload_sha256": opened.payload["displayed_payload_sha256"]
                },
            )
            self._write_event_receipt(actor, event)
            return event

    def record_decision(
        self,
        actor_id: str,
        presentation_id: str,
        decision: ReviewDecision,
    ) -> ReviewJournalEvent:
        """Append one irreversible decision after open and display acknowledgement."""

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            if actor.role == "adjudicator":
                self._require_reviewer_locks(states)
            state = states[actor_id]
            opened = self._require_open(state, presentation_id)
            if not state.acknowledged:
                raise ReviewSessionError("decision requires display acknowledgement")
            case = self.suite.case(str(opened.case_id))
            self._validate_decision(case, decision)
            event = self._append_event(
                actor,
                event_type="case.decision.recorded",
                case_id=opened.case_id,
                presentation_id=presentation_id,
                payload={"decision": decision.model_dump(mode="json")},
            )
            self._write_event_receipt(actor, event)
            return event

    def lock_reviewer(self, actor_id: str) -> ReviewerLockReceipt:
        """Lock a complete reviewer journal before the adjudicator may open any case."""

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            if actor.role != "reviewer":
                raise ReviewSessionError("only independent reviewers have reviewer locks")
            state = states[actor_id]
            if state.locked_or_finalized:
                raise ReviewSessionError("reviewer journal is already locked")
            if state.current_index != len(state.order) or state.open_event is not None:
                raise ReviewSessionError("reviewer must decide every case before locking")
            prior_head = state.events[-1].event_hash if state.events else GENESIS_EVENT_HASH
            event = self._append_event(
                actor,
                event_type="reviewer.journal.locked",
                case_id=None,
                presentation_id=None,
                payload={
                    "case_count": len(state.order),
                    "journal_head_before_event": prior_head,
                    "suite_sha256": self.suite.suite_sha256,
                },
            )
            self._write_event_receipt(actor, event)
            receipt = ReviewerLockReceipt(
                receipt_version="firelens_reviewer_lock_receipt.v1",
                implementation_status=_IMPLEMENTATION_STATUS,
                qualification_eligible=False,
                session_id=self.session.session_id,
                actor_id=actor.actor_id,
                case_count=len(state.order),
                journal_count=event.sequence,
                journal_head_hash=event.event_hash,
                suite_sha256=self.suite.suite_sha256,
                input_file_roster_sha256=input_file_roster_sha256(self.suite),
                locked_at=event.timestamp,
            )
            create_immutable_json(
                self.directory,
                f"locks/{actor.actor_id}.json",
                receipt,
            )
            self._verify_reviewer_lock(actor, event)
            return receipt

    def finalize_adjudication(self, actor_id: str) -> SessionFinalizationReceipt:
        """Finalize after all adjudications and a fresh identity recheck."""

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            actor = self._actor(actor_id)
            if actor.role != "adjudicator":
                raise ReviewSessionError("only the distinct adjudicator may finalize")
            self._require_reviewer_locks(states)
            state = states[actor_id]
            if state.locked_or_finalized:
                raise ReviewSessionError("adjudication was already finalized")
            if state.current_index != len(state.order) or state.open_event is not None:
                raise ReviewSessionError(
                    "adjudicator must decide every case before finalization"
                )
            prior_head = state.events[-1].event_hash if state.events else GENESIS_EVENT_HASH
            event = self._append_event(
                actor,
                event_type="adjudication.finalized",
                case_id=None,
                presentation_id=None,
                payload={
                    "case_count": len(state.order),
                    "journal_head_before_event": prior_head,
                    "suite_sha256": self.suite.suite_sha256,
                },
            )
            self._write_event_receipt(actor, event)
            final_states = self._states()
            receipt = SessionFinalizationReceipt(
                receipt_version="firelens_review_session_finalization.v1",
                implementation_status=_IMPLEMENTATION_STATUS,
                qualification_eligible=False,
                limitation=(
                    "Session evidence is not release-qualifying until journal storage and "
                    "qualification integration are independently hardened."
                ),
                session_id=self.session.session_id,
                suite_sha256=self.suite.suite_sha256,
                input_file_roster_sha256=input_file_roster_sha256(self.suite),
                finalized_by=actor.actor_id,
                finalized_at=event.timestamp,
                actor_journal_heads={
                    key: value.events[-1].event_hash for key, value in final_states.items()
                },
                actor_journal_counts={
                    key: len(value.events) for key, value in final_states.items()
                },
            )
            create_immutable_json(self.directory, "session/finalization.json", receipt)
            self._verify_finalization(receipt)
            return receipt

    def finalized_evidence(self) -> FinalizedReviewEvidence:
        """Return a fully replayed, receipt-bound snapshot after finalization.

        The snapshot is intentionally nonqualifying.  It gives an independent
        storage reviewer a canonical object to retain and inspect without
        silently converting this backend scaffold into release evidence.
        """

        with self._guard():
            self._verify_genesis()
            self.suite.recheck_input_files()
            states = self._states()
            adjudicator = self._adjudicator()
            if not states[adjudicator.actor_id].locked_or_finalized:
                raise ReviewSessionError("review evidence requires finalized adjudication")
            finalization = _canonical_private_json(
                self.directory / "session/finalization.json",
                SessionFinalizationReceipt,
            )
            if not isinstance(finalization, SessionFinalizationReceipt):
                raise ReviewSessionError("finalization receipt uses the wrong contract")
            self._verify_finalization(finalization)
            return build_finalized_evidence(
                session=self.session,
                suite=self.suite,
                states=states,
                finalization=finalization,
            )

    def _actor(self, actor_id: str) -> ReviewActor:
        try:
            return self._actors[actor_id]
        except KeyError as exc:
            raise ReviewSessionError("unknown review actor") from exc

    def _reviewers(self) -> tuple[ReviewActor, ReviewActor]:
        reviewers = tuple(actor for actor in self.session.actors if actor.role == "reviewer")
        if len(reviewers) != 2:
            raise ReviewSessionError("session reviewer roster is invalid")
        return reviewers[0], reviewers[1]

    def _adjudicator(self) -> ReviewActor:
        return next(actor for actor in self.session.actors if actor.role == "adjudicator")

    def _journal_path(self, actor: ReviewActor) -> str:
        return f"journals/{actor.actor_id}.jsonl"

    def _journal(self, actor: ReviewActor) -> AppendOnlyReviewJournal:
        return AppendOnlyReviewJournal(
            self.directory,
            session_id=self.session.session_id,
            relative_path=self._journal_path(actor),
        )

    @contextmanager
    def _guard(self) -> Iterator[None]:
        root = self.directory.resolve(strict=True)
        metadata = root.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ReviewSessionError("review session root must be a real directory")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ReviewSessionError("review session root must have mode 0700")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        root_fd = os.open(root, directory_flags)
        lock_flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        lock_fd: int | None = None
        try:
            lock_fd = os.open(".session.lock", lock_flags, 0o600, dir_fd=root_fd)
            os.fchmod(lock_fd, 0o600)
            lock_metadata = os.fstat(lock_fd)
            if (
                not stat.S_ISREG(lock_metadata.st_mode)
                or lock_metadata.st_nlink != 1
                or stat.S_IMODE(lock_metadata.st_mode) != 0o600
            ):
                raise ReviewSessionError("session coordination lock is unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(root_fd)

    def _verify_genesis(self) -> None:
        actual = _canonical_private_json(
            self.directory / "session/genesis.json", SessionGenesisReceipt
        )
        if actual != self._expected_genesis:
            raise ReviewSessionError("immutable session genesis differs from current inputs")

    def _states(self) -> dict[str, _DerivedActorState]:
        states: dict[str, _DerivedActorState] = {}
        for reviewer in self._reviewers():
            states[reviewer.actor_id] = self._derive_actor(reviewer, states)
        adjudicator = self._adjudicator()
        states[adjudicator.actor_id] = self._derive_actor(adjudicator, states)
        return states

    def _derive_actor(
        self,
        actor: ReviewActor,
        prior_states: dict[str, _DerivedActorState],
    ) -> _DerivedActorState:
        events = self._journal(actor).replay()
        self._verify_event_receipts(actor, events)
        order = deterministic_actor_case_order(self.session, self.suite, actor)
        decisions: dict[str, ReviewDecision] = {}
        current_index = 0
        open_event: ReviewJournalEvent | None = None
        acknowledged = False
        locked = False
        for event in events:
            if event.actor_id != actor.actor_id or event.session_id != self.session.session_id:
                raise ReviewSessionError("journal event uses the wrong actor or session")
            if locked:
                raise ReviewSessionError("journal contains events after its irreversible lock")
            if event.event_type == "presentation.opened":
                if open_event is not None or current_index >= len(order):
                    raise ReviewSessionError(
                        "journal contains an invalid repeated presentation"
                    )
                expected = self._presentation(actor, current_index, prior_states)
                if (
                    event.case_id != expected.case_id
                    or event.presentation_id != expected.presentation_id
                    or event.payload
                    != {
                        "case_position": expected.case_position,
                        "displayed_payload_sha256": expected.displayed_payload_sha256,
                        "payload_sha256": expected.payload_sha256,
                        "suite_sha256": self.suite.suite_sha256,
                        "input_file_roster_sha256": input_file_roster_sha256(self.suite),
                    }
                ):
                    raise ReviewSessionError(
                        "journal presentation differs from deterministic input"
                    )
                open_event = event
                acknowledged = False
            elif event.event_type == "presentation.display_acknowledged":
                if (
                    open_event is None
                    or acknowledged
                    or event.case_id != open_event.case_id
                    or event.presentation_id != open_event.presentation_id
                    or event.payload
                    != {
                        "displayed_payload_sha256": open_event.payload[
                            "displayed_payload_sha256"
                        ]
                    }
                ):
                    raise ReviewSessionError(
                        "journal contains an invalid display acknowledgement"
                    )
                acknowledged = True
            elif event.event_type == "case.decision.recorded":
                if (
                    open_event is None
                    or not acknowledged
                    or event.case_id != open_event.case_id
                    or event.presentation_id != open_event.presentation_id
                    or set(event.payload) != {"decision"}
                ):
                    raise ReviewSessionError("journal decision is out of protocol order")
                decision = ReviewDecision.model_validate(event.payload["decision"])
                case = self.suite.case(str(event.case_id))
                self._validate_decision(case, decision)
                decisions[case.case_id] = decision
                current_index += 1
                open_event = None
                acknowledged = False
            elif event.event_type == "reviewer.journal.locked":
                if actor.role != "reviewer":
                    raise ReviewSessionError("adjudicator journal contains a reviewer lock")
                if current_index != len(order) or open_event is not None:
                    raise ReviewSessionError("reviewer journal locked before all decisions")
                expected_payload = {
                    "case_count": len(order),
                    "journal_head_before_event": event.previous_event_hash,
                    "suite_sha256": self.suite.suite_sha256,
                }
                if (
                    event.case_id is not None
                    or event.presentation_id is not None
                    or event.payload != expected_payload
                ):
                    raise ReviewSessionError("reviewer lock event is inconsistent")
                self._verify_reviewer_lock(actor, event)
                locked = True
            elif event.event_type == "adjudication.finalized":
                if actor.role != "adjudicator":
                    raise ReviewSessionError(
                        "reviewer journal contains adjudication finalization"
                    )
                if current_index != len(order) or open_event is not None:
                    raise ReviewSessionError("adjudication finalized before all decisions")
                expected_payload = {
                    "case_count": len(order),
                    "journal_head_before_event": event.previous_event_hash,
                    "suite_sha256": self.suite.suite_sha256,
                }
                if (
                    event.case_id is not None
                    or event.presentation_id is not None
                    or event.payload != expected_payload
                ):
                    raise ReviewSessionError("adjudication finalization event is inconsistent")
                locked = True
            else:
                raise ReviewSessionError(
                    "journal contains an event type outside the session protocol"
                )
        if actor.role == "adjudicator" and events:
            if len(prior_states) != 2 or not all(
                state.locked_or_finalized for state in prior_states.values()
            ):
                raise ReviewSessionError(
                    "adjudicator journal started before both reviewer locks"
                )
        return _DerivedActorState(
            actor=actor,
            order=order,
            events=events,
            decisions=decisions,
            current_index=current_index,
            open_event=open_event,
            acknowledged=acknowledged,
            locked_or_finalized=locked,
        )

    def _presentation(
        self,
        actor: ReviewActor,
        index: int,
        states: dict[str, _DerivedActorState],
    ) -> ReviewPresentation:
        order = deterministic_actor_case_order(self.session, self.suite, actor)
        case_id = order[index]
        case = self.suite.case(case_id)
        material: tuple[AdjudicationMaterial, ...] = ()
        if actor.role == "adjudicator":
            reviewer_states = [
                states[item.actor_id]
                for item in sorted(self._reviewers(), key=lambda row: row.actor_id)
            ]
            if len(reviewer_states) != 2 or not all(
                state.locked_or_finalized for state in reviewer_states
            ):
                raise ReviewSessionError(
                    "adjudicator is blocked until both reviewer journals lock"
                )
            material = tuple(
                AdjudicationMaterial(
                    reviewer_slot="reviewer-a" if slot == 0 else "reviewer-b",
                    decision=state.decisions[case_id],
                )
                for slot, state in enumerate(reviewer_states)
            )
        displayed_hash = canonical_sha256(
            {
                "payload": case.payload.model_dump(mode="json"),
                "review_material": [item.model_dump(mode="json") for item in material],
            }
        )
        presentation_material = (
            f"{self.session.session_id}\0{actor.actor_id}\0{case_id}\0{index + 1}\0"
            f"{displayed_hash}"
        ).encode()
        presentation_id = "P-" + hashlib.sha256(presentation_material).hexdigest()[:40]
        return ReviewPresentation(
            presentation_version="firelens_blind_review_presentation.v1",
            session_id=self.session.session_id,
            actor_id=actor.actor_id,
            case_id=case_id,
            case_position=index + 1,
            presentation_id=presentation_id,
            payload=case.payload,
            payload_sha256=case.payload_sha256,
            review_material=material,
            displayed_payload_sha256=displayed_hash,
        )

    def _validate_decision(self, case: ImportedReviewCase, decision: ReviewDecision) -> None:
        expected_claim_ids = [claim.claim_id for claim in case.payload.claims]
        actual_claim_ids = [claim.claim_id for claim in decision.claims]
        semantic_checks = (
            decision.required_concepts_present,
            decision.forbidden_claims_absent,
            decision.required_limitations_present,
        )
        retrieval_checks = (
            decision.question_is_independent,
            decision.answerability_correct,
            decision.acceptable_evidence_correct,
        )
        if self.suite.suite_kind == "retrieval":
            if any(value is not None for value in semantic_checks):
                raise ReviewSessionError("retrieval decisions cannot use semantic check fields")
            if any(value is None for value in retrieval_checks):
                raise ReviewSessionError("retrieval decisions require all three label checks")
            if actual_claim_ids:
                raise ReviewSessionError("retrieval decisions cannot contain claim assessments")
        else:
            if any(value is None for value in semantic_checks):
                raise ReviewSessionError("semantic decisions require all three rubric checks")
            if any(value is not None for value in retrieval_checks):
                raise ReviewSessionError("semantic decisions cannot use retrieval label checks")
            if actual_claim_ids != expected_claim_ids:
                raise ReviewSessionError(
                    "semantic decision claim roster differs from presentation"
                )

    def _require_open(
        self, state: _DerivedActorState, presentation_id: str
    ) -> ReviewJournalEvent:
        if state.open_event is None or state.open_event.presentation_id != presentation_id:
            raise ReviewSessionError("transition does not target the current open presentation")
        return state.open_event

    def _require_reviewer_locks(self, states: dict[str, _DerivedActorState]) -> None:
        if not all(states[actor.actor_id].locked_or_finalized for actor in self._reviewers()):
            raise ReviewSessionError("adjudicator is blocked until both reviewer journals lock")

    def _now(self) -> datetime:
        return _utc(self._clock())

    def _append_event(
        self,
        actor: ReviewActor,
        *,
        event_type: str,
        case_id: str | None,
        presentation_id: str | None,
        payload: dict[str, Any],
    ) -> ReviewJournalEvent:
        return append_review_event(
            self._journal(actor),
            self.session,
            actor,
            event_type,
            case_id,
            presentation_id,
            payload,
            self._now(),
        )

    def _write_event_receipt(self, actor: ReviewActor, event: ReviewJournalEvent) -> None:
        create_immutable_json(
            self.directory,
            receipt_path(actor, event.sequence),
            event_head_receipt(
                self.session, self.suite, self._journal_path(actor), actor, event
            ),
        )

    def _verify_event_receipts(
        self, actor: ReviewActor, events: tuple[ReviewJournalEvent, ...]
    ) -> None:
        verify_event_receipts(
            self.directory,
            _RECEIPT_NAME,
            self.session,
            self.suite,
            self._journal_path(actor),
            actor,
            events,
        )

    def _verify_reviewer_lock(self, actor: ReviewActor, event: ReviewJournalEvent) -> None:
        verify_reviewer_lock(self.directory, self.session, self.suite, actor, event)

    def _verify_finalization(self, expected: SessionFinalizationReceipt) -> None:
        verify_finalization(self.directory, expected)
