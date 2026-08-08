"""Immutable blind-review session state machine.

This is a local backend scaffold, not release-qualifying review evidence.  It
wraps each journal append in a protocol transition, writes an immutable receipt
for every observed head/count, and refuses to continue if a journal and its
receipts disagree.  Event time comes only from the coordinator's clock; no
public transition accepts a caller-authored timestamp.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.review_workspace.inputs import (
    BlindCasePayload,
    ImportedReviewCase,
    ImportedReviewSuite,
    canonical_sha256,
    input_file_roster_sha256,
)
from firelens.review_workspace.journal import AppendOnlyReviewJournal, create_immutable_json
from firelens.review_workspace.models import (
    GENESIS_EVENT_HASH,
    ReviewActor,
    ReviewEventDraft,
    ReviewJournalEvent,
    ReviewSession,
)

_IMPLEMENTATION_STATUS: Literal["nonqualifying_backend_scaffold"] = (
    "nonqualifying_backend_scaffold"
)
_RECEIPT_NAME = re.compile(r"^(?P<sequence>[0-9]{6})\.json$")


class ReviewSessionError(ValueError):
    """The requested transition violates the frozen review protocol."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimAssessment(_FrozenModel):
    claim_id: str = Field(min_length=1, max_length=128)
    decision: Literal["supported", "unsupported", "unclear"]
    notes: str = Field(default="", max_length=4_000)


class ReviewDecision(_FrozenModel):
    """One irreversible human case decision for either supported suite family."""

    disposition: Literal["approve", "reject", "needs_discussion"]
    required_concepts_present: bool | None = None
    forbidden_claims_absent: bool | None = None
    required_limitations_present: bool | None = None
    question_is_independent: bool | None = None
    answerability_correct: bool | None = None
    acceptable_evidence_correct: bool | None = None
    claims: tuple[ClaimAssessment, ...] = Field(max_length=1_000)
    notes: str = Field(default="", max_length=8_000)

    @model_validator(mode="after")
    def claim_ids_are_unique(self) -> ReviewDecision:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("review decision repeats claim IDs")
        return self


class AdjudicationMaterial(_FrozenModel):
    reviewer_slot: Literal["reviewer-a", "reviewer-b"]
    decision: ReviewDecision


class ReviewPresentation(_FrozenModel):
    presentation_version: Literal["firelens_blind_review_presentation.v1"]
    session_id: str
    actor_id: str
    case_id: str
    case_position: int = Field(ge=1, strict=True)
    presentation_id: str
    payload: BlindCasePayload
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_material: tuple[AdjudicationMaterial, ...] = Field(max_length=2)
    displayed_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActorCaseOrder(_FrozenModel):
    actor_id: str
    actor_role: Literal["reviewer", "adjudicator"]
    case_ids: tuple[str, ...]
    case_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SessionGenesisReceipt(_FrozenModel):
    receipt_version: Literal["firelens_review_session_genesis.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session: ReviewSession
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_file_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_payload_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor_orders: tuple[ActorCaseOrder, ...] = Field(min_length=3, max_length=3)
    initial_journal_count: Literal[0]
    initial_journal_head: Literal[
        "0000000000000000000000000000000000000000000000000000000000000000"
    ]


class EventHeadReceipt(_FrozenModel):
    receipt_version: Literal["firelens_review_event_head_receipt.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session_id: str
    actor_id: str
    journal_relative_path: str
    sequence: int = Field(ge=1, strict=True)
    journal_count: int = Field(ge=1, strict=True)
    journal_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_type: str
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str | None
    presentation_id: str | None
    recorded_at: datetime
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_file_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewerLockReceipt(_FrozenModel):
    receipt_version: Literal["firelens_reviewer_lock_receipt.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session_id: str
    actor_id: str
    case_count: int = Field(ge=1, strict=True)
    journal_count: int = Field(ge=1, strict=True)
    journal_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_file_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locked_at: datetime


class SessionFinalizationReceipt(_FrozenModel):
    receipt_version: Literal["firelens_review_session_finalization.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    limitation: Literal[
        "Session evidence is not release-qualifying until journal storage and qualification integration are independently hardened."
    ]
    session_id: str
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_file_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finalized_by: str
    finalized_at: datetime
    actor_journal_heads: dict[str, str] = Field(min_length=3, max_length=3)
    actor_journal_counts: dict[str, int] = Field(min_length=3, max_length=3)


class FinalizedCaseDecision(_FrozenModel):
    case_id: str
    presentation_id: str
    recorded_at: datetime
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: ReviewDecision


class FinalizedActorEvidence(_FrozenModel):
    actor: ReviewActor
    journal_count: int = Field(ge=1, strict=True)
    journal_head_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: tuple[FinalizedCaseDecision, ...] = Field(min_length=1)


class FinalizedReviewEvidence(_FrozenModel):
    evidence_version: Literal["firelens_finalized_review_evidence.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    limitation: Literal[
        "This export preserves finalized blind-review evidence but is not a release-gate sidecar. Independent storage review and explicit qualification integration remain required."
    ]
    session: ReviewSession
    suite_kind: Literal["conversation", "retrieval", "semantic_holdout"]
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_file_roster_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finalization: SessionFinalizationReceipt
    actors: tuple[FinalizedActorEvidence, ...] = Field(min_length=3, max_length=3)


class ActorProgress(_FrozenModel):
    session_state: Literal["independent_review", "adjudicating", "finalized"]
    actor_state: Literal[
        "blocked_on_reviewer_locks",
        "awaiting_presentation",
        "awaiting_display_acknowledgement",
        "awaiting_decision",
        "complete_pending_lock",
        "locked",
        "finalized",
    ]
    actor_id: str
    completed_case_count: int = Field(ge=0, strict=True)
    case_count: int = Field(ge=1, strict=True)
    next_case_position: int | None = Field(default=None, ge=1, strict=True)


@dataclass(frozen=True)
class _DerivedActorState:
    actor: ReviewActor
    order: tuple[str, ...]
    events: tuple[ReviewJournalEvent, ...]
    decisions: dict[str, ReviewDecision]
    current_index: int
    open_event: ReviewJournalEvent | None
    acknowledged: bool
    locked_or_finalized: bool


def deterministic_actor_case_order(
    session: ReviewSession,
    suite: ImportedReviewSuite,
    actor: ReviewActor,
) -> tuple[str, ...]:
    """Return an identity-bound order without reading model or ranking outputs."""

    def key(case_id: str) -> tuple[str, str]:
        material = (
            f"{session.session_id}\0{suite.suite_sha256}\0{actor.role}\0"
            f"{actor.actor_id}\0{case_id}"
        ).encode()
        return hashlib.sha256(material).hexdigest(), case_id

    return tuple(sorted(session.case_ids, key=key))


def _case_payload_roster_sha256(suite: ImportedReviewSuite) -> str:
    return canonical_sha256(
        [
            {"case_id": case.case_id, "payload_sha256": case.payload_sha256}
            for case in suite.cases
        ]
    )


def _actor_orders(
    session: ReviewSession, suite: ImportedReviewSuite
) -> tuple[ActorCaseOrder, ...]:
    return tuple(
        ActorCaseOrder(
            actor_id=actor.actor_id,
            actor_role=actor.role,
            case_ids=(order := deterministic_actor_case_order(session, suite, actor)),
            case_order_sha256=canonical_sha256(list(order)),
        )
        for actor in session.actors
        if actor.role in {"reviewer", "adjudicator"}
    )


def _genesis(session: ReviewSession, suite: ImportedReviewSuite) -> SessionGenesisReceipt:
    return SessionGenesisReceipt(
        receipt_version="firelens_review_session_genesis.v1",
        implementation_status=_IMPLEMENTATION_STATUS,
        qualification_eligible=False,
        session=session,
        suite_sha256=suite.suite_sha256,
        dataset_sha256=suite.dataset_sha256,
        input_file_roster_sha256=input_file_roster_sha256(suite),
        case_payload_roster_sha256=_case_payload_roster_sha256(suite),
        actor_orders=_actor_orders(session, suite),
        initial_journal_count=0,
        initial_journal_head=GENESIS_EVENT_HASH,
    )


def _validate_session(session: ReviewSession, suite: ImportedReviewSuite) -> None:
    if session.artifact_sha256 != suite.suite_sha256:
        raise ReviewSessionError("session artifact hash does not match imported review inputs")
    if session.case_ids != tuple(case.case_id for case in suite.cases):
        raise ReviewSessionError("session case roster differs from imported review inputs")
    reviewers = [actor for actor in session.actors if actor.role == "reviewer"]
    adjudicators = [actor for actor in session.actors if actor.role == "adjudicator"]
    if len(session.actors) != 3 or len(reviewers) != 2 or len(adjudicators) != 1:
        raise ReviewSessionError(
            "blind review requires exactly two reviewers and one adjudicator"
        )
    normalized_names = [actor.display_name.casefold() for actor in session.actors]
    if len(normalized_names) != len(set(normalized_names)):
        raise ReviewSessionError("reviewers and adjudicator must be distinct named people")
    if suite.suite_kind == "retrieval" and session.review_kind != "retrieval":
        raise ReviewSessionError("retrieval inputs require a retrieval review session")
    if suite.suite_kind != "retrieval" and session.review_kind != "semantic":
        raise ReviewSessionError("semantic inputs require a semantic review session")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewSessionError("coordinator clock returned a naive timestamp")
    return value.astimezone(UTC)


def _canonical_private_json(path: Path, model: type[_FrozenModel]) -> _FrozenModel:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReviewSessionError(f"missing immutable session artifact: {path.name}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ReviewSessionError("immutable session artifact is not a private regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ReviewSessionError("immutable session artifact must have mode 0600")
        raw = os.read(descriptor, metadata.st_size + 1)
        if len(raw) != metadata.st_size:
            raise ReviewSessionError("immutable session artifact changed while reading")
    finally:
        os.close(descriptor)
    if not raw.endswith(b"\n"):
        raise ReviewSessionError("immutable session artifact is not canonical JSON")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewSessionError("immutable session artifact is invalid JSON") from exc
    rendered = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if rendered != raw:
        raise ReviewSessionError("immutable session artifact is not canonical JSON")
    return model.model_validate(value)


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
            actors: list[FinalizedActorEvidence] = []
            for actor in self.session.actors:
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
                session=self.session,
                suite_kind=self.suite.suite_kind,
                suite_sha256=self.suite.suite_sha256,
                dataset_sha256=self.suite.dataset_sha256,
                input_file_roster_sha256=input_file_roster_sha256(self.suite),
                finalization=finalization,
                actors=tuple(actors),
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
        journal = self._journal(actor)
        existing = journal.replay()
        now = self._now()
        if existing and now <= existing[-1].timestamp:
            raise ReviewSessionError(
                "trusted coordinator timestamps must be strictly increasing"
            )
        idempotency_material = canonical_sha256(
            {
                "session_id": self.session.session_id,
                "actor_id": actor.actor_id,
                "event_type": event_type,
                "case_id": case_id,
                "presentation_id": presentation_id,
            }
        )
        return journal.append(
            ReviewEventDraft(
                event_type=event_type,
                session_id=self.session.session_id,
                actor_id=actor.actor_id,
                case_id=case_id,
                idempotency_key="evt-" + idempotency_material[:40],
                presentation_id=presentation_id,
                payload=payload,
                timestamp=now,
            )
        )

    def _event_receipt(self, actor: ReviewActor, event: ReviewJournalEvent) -> EventHeadReceipt:
        return EventHeadReceipt(
            receipt_version="firelens_review_event_head_receipt.v1",
            implementation_status=_IMPLEMENTATION_STATUS,
            qualification_eligible=False,
            session_id=self.session.session_id,
            actor_id=actor.actor_id,
            journal_relative_path=self._journal_path(actor),
            sequence=event.sequence,
            journal_count=event.sequence,
            journal_head_hash=event.event_hash,
            event_type=event.event_type,
            event_hash=event.event_hash,
            previous_event_hash=event.previous_event_hash,
            case_id=event.case_id,
            presentation_id=event.presentation_id,
            recorded_at=event.timestamp,
            suite_sha256=self.suite.suite_sha256,
            input_file_roster_sha256=input_file_roster_sha256(self.suite),
        )

    def _receipt_path(self, actor: ReviewActor, sequence: int) -> str:
        return f"receipts/{actor.actor_id}/{sequence:06d}.json"

    def _write_event_receipt(self, actor: ReviewActor, event: ReviewJournalEvent) -> None:
        create_immutable_json(
            self.directory,
            self._receipt_path(actor, event.sequence),
            self._event_receipt(actor, event),
        )

    def _verify_event_receipts(
        self, actor: ReviewActor, events: tuple[ReviewJournalEvent, ...]
    ) -> None:
        receipt_directory = self.directory / "receipts" / actor.actor_id
        observed_sequences: list[int] = []
        if receipt_directory.exists():
            metadata = receipt_directory.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ReviewSessionError("event receipt directory is unsafe")
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                raise ReviewSessionError("event receipt directory must have mode 0700")
            for path in receipt_directory.iterdir():
                match = _RECEIPT_NAME.fullmatch(path.name)
                if match is None or path.is_symlink():
                    raise ReviewSessionError(
                        "event receipt directory contains an unknown entry"
                    )
                observed_sequences.append(int(match.group("sequence")))
        expected_sequences = list(range(1, len(events) + 1))
        if sorted(observed_sequences) != expected_sequences:
            raise ReviewSessionError(
                "journal head/count disagrees with immutable receipt roster"
            )
        for event in events:
            actual = _canonical_private_json(
                self.directory / self._receipt_path(actor, event.sequence), EventHeadReceipt
            )
            if actual != self._event_receipt(actor, event):
                raise ReviewSessionError("immutable event receipt differs from journal head")

    def _verify_reviewer_lock(self, actor: ReviewActor, event: ReviewJournalEvent) -> None:
        actual = _canonical_private_json(
            self.directory / f"locks/{actor.actor_id}.json", ReviewerLockReceipt
        )
        expected = ReviewerLockReceipt(
            receipt_version="firelens_reviewer_lock_receipt.v1",
            implementation_status=_IMPLEMENTATION_STATUS,
            qualification_eligible=False,
            session_id=self.session.session_id,
            actor_id=actor.actor_id,
            case_count=len(self.session.case_ids),
            journal_count=event.sequence,
            journal_head_hash=event.event_hash,
            suite_sha256=self.suite.suite_sha256,
            input_file_roster_sha256=input_file_roster_sha256(self.suite),
            locked_at=event.timestamp,
        )
        if actual != expected:
            raise ReviewSessionError("reviewer lock receipt differs from locked journal")

    def _verify_finalization(self, expected: SessionFinalizationReceipt) -> None:
        actual = _canonical_private_json(
            self.directory / "session/finalization.json", SessionFinalizationReceipt
        )
        if actual != expected:
            raise ReviewSessionError("session finalization receipt is inconsistent")
