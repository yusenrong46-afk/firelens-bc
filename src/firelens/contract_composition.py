"""Pure renderers for deterministic public answer-contract composition."""

from __future__ import annotations

from collections.abc import Sequence

DETERMINISTIC_CONFLICT_TEXT = (
    "The selected approved sources conflict. FireLens is showing both statements and "
    "cannot determine which version governs; check the issuing authority or the most "
    "recent official document before acting."
)
BOUNDED_CONFLICT_TEXT = (
    "Reviewed sources conflict, so FireLens cannot combine them into one apparently "
    "certain answer. Inspect both reviewed sources before acting."
)

_ALLOWED_CONFLICT_TEXTS = frozenset({DETERMINISTIC_CONFLICT_TEXT, BOUNDED_CONFLICT_TEXT})
_CONFLICTING_GUIDANCE = "conflicting_guidance"
_CURRENT_RECORDS = "current_records"
_OFFICIAL_HANDOFF = "official_handoff"
_UNCERTAINTY = "uncertainty"


def is_canonical_conflict_answer(
    answer: str | None,
    sections: Sequence[tuple[str, str]],
) -> bool:
    """Return whether conflict prose exactly matches the approved section grammar."""

    conflict_sections = [text for kind, text in sections if kind == _CONFLICTING_GUIDANCE]
    if not conflict_sections:
        return answer in _ALLOWED_CONFLICT_TEXTS
    if len(conflict_sections) != 1:
        return False
    conflict_text = conflict_sections[0]
    if conflict_text not in _ALLOWED_CONFLICT_TEXTS:
        return False
    return answer == _render_sectioned_conflict_answer(sections, conflict_text)


def _render_sectioned_conflict_answer(
    sections: Sequence[tuple[str, str]],
    conflict_text: str,
) -> str | None:
    kinds = [kind for kind, _text in sections]
    if kinds == [_CONFLICTING_GUIDANCE]:
        return conflict_text
    if kinds[:2] == [_CURRENT_RECORDS, _CONFLICTING_GUIDANCE] and len(sections) in {2, 3}:
        answer = sections[0][1] + "\n\nConflicting reviewed sources: " + conflict_text
        if len(sections) == 2:
            return answer
        if sections[2][0] == _OFFICIAL_HANDOFF:
            return answer + "\n\nRelated official information: " + sections[2][1]
        return None
    if kinds in (
        [_UNCERTAINTY, _CONFLICTING_GUIDANCE],
        [_OFFICIAL_HANDOFF, _CONFLICTING_GUIDANCE],
    ):
        return (
            "Official information: "
            + sections[0][1]
            + "\n\nConflicting reviewed sources: "
            + conflict_text
        )
    return None
