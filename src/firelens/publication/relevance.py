"""Deterministic typed-scope relevance for reviewed publication candidates."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from firelens.answering.context import (
    SUPPORT_TOKEN_OVERLAP_FLOOR,
    support_token_overlap,
)
from firelens.publication.comparison_targets import ALERT_ORDER_ATOMIC_TARGET_SET
from firelens.publication.records import get_versioned

_APPLICABILITY_QUALIFIERS = (
    re.compile(
        r"\bif\s+(?:i|we|you|someone|a person|people)\s+"
        r"(?:am|are|is|have|has)\s+(?P<scope>[^?.,;]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:for|about)\s+(?:a\s+)?(?:person|people|someone|residents?|individuals?)\s+"
        r"(?:who\s+(?:is|are|have|has)|with)\s+(?P<scope>[^?.,;]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bas\s+(?:a|an)\s+(?P<scope>[^?.,;]{1,60}?)\s+"
        r"(?:person|resident|individual)\b",
        re.IGNORECASE,
    ),
)


def most_relevant_competing_typed_claims(
    claim_ids: Sequence[str], targets: Sequence[str]
) -> list[str]:
    """Resolve adjacent reviewed claims by their typed scope, per requested aspect.

    A source packet can legitimately contain several reviewed records. When more
    than one passes broad source-text overlap, retain the best typed-scope match
    for each requested target. Single supported records and exact-score ties are
    preserved, and the existing publication overlap floor remains authoritative.
    """

    if len(claim_ids) <= 1:
        return list(claim_ids)
    scope_by_id = {claim_id: _typed_publication_scope(claim_id) for claim_id in claim_ids}
    focused: set[str] = set()
    for target in targets:
        scored = [
            (claim_id, support_token_overlap(scope_by_id[claim_id], target))
            for claim_id in claim_ids
        ]
        best = max((score for _claim_id, score in scored), default=0.0)
        if best < SUPPORT_TOKEN_OVERLAP_FLOOR:
            continue
        focused.update(claim_id for claim_id, score in scored if score == best)
    if not focused:
        return list(claim_ids)
    return [claim_id for claim_id in claim_ids if claim_id in focused]


def _typed_publication_scope(claim_id: str) -> str:
    record = get_versioned(claim_id).record
    return "\n".join(
        value
        for value in (
            record.subject,
            record.status_stage,
            *record.conditions,
            *record.applies_to,
        )
        if value
    )


def _matches_publication_target(text: str, targets: Sequence[str]) -> bool:
    return any(
        support_token_overlap(text, target) >= SUPPORT_TOKEN_OVERLAP_FLOOR for target in targets
    )


@lru_cache(maxsize=1_024)
def typed_record_matches_publication_target(
    claim_id: str,
    approved_surface_sha256: str,
    source_span_sha256: str,
    targets: tuple[str, ...],
) -> bool:
    current = get_versioned(claim_id)
    if (
        current.approved_surface_sha256 != approved_surface_sha256
        or current.source_span_sha256 != source_span_sha256
    ):
        return False
    # A typed action with applicability conditions needs support for at least
    # one such condition in the requested target. Topic overlap alone cannot
    # authorize a conditional instruction from an adjacent source passage.
    # An exact approved canonical surface remains an atomic self-match: two
    # admitted records deliberately keep their re-entry qualifier in typed
    # metadata while their approved public surface is the instruction alone.
    condition_supported = any(
        support_token_overlap(target, condition) >= SUPPORT_TOKEN_OVERLAP_FLOOR
        for target in targets
        for condition in current.record.conditions
    )
    canonical_surface_requested = any(
        " ".join(target.split()).casefold()
        == " ".join(current.canonical_text.split()).casefold()
        for target in targets
    )
    if current.record.conditions and not (condition_supported or canonical_surface_requested):
        return False
    scope_text = "\n".join(
        value
        for value in (
            current.record.subject,
            current.record.status_stage,
            *current.record.conditions,
            *current.record.applies_to,
        )
        if value
    )
    if any(
        qualifier and support_token_overlap(scope_text, qualifier) < 1.0
        for target in targets
        for qualifier in applicability_qualifiers(target)
    ):
        return False
    atomic_targets = tuple(
        target for target in targets if target in ALERT_ORDER_ATOMIC_TARGET_SET
    )
    if atomic_targets:
        if current.record.subject in atomic_targets:
            return True
        non_atomic = tuple(
            target for target in targets if target not in ALERT_ORDER_ATOMIC_TARGET_SET
        )
        if not non_atomic:
            return False
        return _matches_publication_target(
            f"{current.canonical_text}\n{current.source_span_text}", non_atomic
        )
    return _matches_publication_target(
        f"{current.canonical_text}\n{current.source_span_text}", targets
    )


@lru_cache(maxsize=2_048)
def applicability_qualifiers(target: str) -> tuple[str, ...]:
    """Extract user-stated constraints without adding a domain phrase list."""

    action_boundary = re.compile(
        r"\b(?:do not|don't|should|must|can|could|may|will|would)\b",
        re.IGNORECASE,
    )
    return tuple(
        qualifier
        for pattern in _APPLICABILITY_QUALIFIERS
        if (match := pattern.search(target)) is not None
        if (
            qualifier := " ".join(
                action_boundary.split(match.group("scope"), maxsplit=1)[0].split()
            )
        )
    )
