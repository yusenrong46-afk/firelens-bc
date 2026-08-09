"""Journal append operations for the blind-review session coordinator."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from firelens.review_workspace.inputs import canonical_sha256
from firelens.review_workspace.journal import AppendOnlyReviewJournal
from firelens.review_workspace.models import (
    ReviewActor,
    ReviewEventDraft,
    ReviewJournalEvent,
    ReviewSession,
)
from firelens.review_workspace.session_common import ReviewSessionError


def append_review_event(
    journal: AppendOnlyReviewJournal,
    session: ReviewSession,
    actor: ReviewActor,
    event_type: str,
    case_id: str | None,
    presentation_id: str | None,
    payload: dict[str, Any],
    now: datetime,
) -> ReviewJournalEvent:
    """Append one coordinator-timestamped event after monotonicity checks."""

    existing = journal.replay()
    if existing and now <= existing[-1].timestamp:
        raise ReviewSessionError("trusted coordinator timestamps must be strictly increasing")
    idempotency_material = canonical_sha256(
        {
            "session_id": session.session_id,
            "actor_id": actor.actor_id,
            "event_type": event_type,
            "case_id": case_id,
            "presentation_id": presentation_id,
        }
    )
    return journal.append(
        ReviewEventDraft(
            event_type=event_type,
            session_id=session.session_id,
            actor_id=actor.actor_id,
            case_id=case_id,
            idempotency_key="evt-" + idempotency_material[:40],
            presentation_id=presentation_id,
            payload=payload,
            timestamp=now,
        )
    )
