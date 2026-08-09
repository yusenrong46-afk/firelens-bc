"""Immutable contracts, genesis rules, and secure receipt parsing for review sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.review_workspace.inputs import (
    BlindCasePayload,
    ImportedReviewSuite,
    canonical_sha256,
    input_file_roster_sha256,
)
from firelens.review_workspace.models import (
    GENESIS_EVENT_HASH,
    ReviewActor,
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
