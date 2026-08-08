"""Strict, versioned contracts for durable human-review sessions and events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

GENESIS_EVENT_HASH: Literal[
    "0000000000000000000000000000000000000000000000000000000000000000"
] = "0000000000000000000000000000000000000000000000000000000000000000"


class ReviewWorkspaceModel(BaseModel):
    """Base contract that rejects undeclared persisted fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(UTC)


class ReviewActor(ReviewWorkspaceModel):
    """A named human role authorized by a separately governed protocol."""

    actor_id: Identifier
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal[
        "reviewer",
        "adjudicator",
        "accessibility_specialist",
        "product_safety_reviewer",
        "release_adjudicator",
        "facilitator",
        "observer",
    ]

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized


class ReviewSession(ReviewWorkspaceModel):
    """Immutable, hash-bound description of one blinded review session."""

    session_version: Literal["firelens_review_session.v1"]
    session_id: Identifier
    review_kind: Literal[
        "semantic",
        "retrieval",
        "frontend_accessibility",
        "frontend_product_safety",
        "ux",
        "adjudication",
    ]
    artifact_sha256: Sha256
    protocol_sha256: Sha256
    created_at: datetime
    case_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=10_000)
    actors: tuple[ReviewActor, ...] = Field(min_length=1, max_length=100)

    @field_validator("created_at")
    @classmethod
    def created_at_is_aware_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> ReviewSession:
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("session contains duplicate case IDs")
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("session contains duplicate actor IDs")
        return self


class ReviewEventDraft(ReviewWorkspaceModel):
    """Caller-supplied semantic content for one journal append."""

    event_type: Identifier
    session_id: Identifier
    actor_id: Identifier
    case_id: Identifier | None
    idempotency_key: Identifier
    presentation_id: Identifier | None
    payload: dict[str, JsonValue] = Field(max_length=1_000)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_aware_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class ReviewJournalEvent(ReviewWorkspaceModel):
    """One canonical, chained record in the append-only review journal."""

    event_version: Literal["firelens_review_journal_event.v1"]
    sequence: int = Field(ge=1, strict=True)
    event_type: Identifier
    session_id: Identifier
    actor_id: Identifier
    case_id: Identifier | None
    idempotency_key: Identifier
    presentation_id: Identifier | None
    payload: dict[str, JsonValue] = Field(max_length=1_000)
    timestamp: datetime
    previous_event_hash: Sha256
    event_hash: Sha256

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_aware_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    def as_draft(self) -> ReviewEventDraft:
        """Return the semantic request represented by this persisted event."""

        return ReviewEventDraft(
            event_type=self.event_type,
            session_id=self.session_id,
            actor_id=self.actor_id,
            case_id=self.case_id,
            idempotency_key=self.idempotency_key,
            presentation_id=self.presentation_id,
            payload=self.payload,
            timestamp=self.timestamp,
        )
