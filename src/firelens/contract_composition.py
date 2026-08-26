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
_GENERAL_BACKGROUND = "general_background"
_OFFICIAL_HANDOFF = "official_handoff"
_REVIEWED_GUIDANCE = "reviewed_guidance"
_UNCERTAINTY = "uncertainty"


def canonical_live_or_mixed_answer(sections: Sequence[tuple[str, str]]) -> str | None:
    """Return one approved top-level answer for validated live or mixed sections."""

    allowed = canonical_live_or_mixed_answers(sections)
    return allowed[0] if allowed else None


def canonical_live_or_mixed_answers(sections: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Return the approved top-level answers for validated live or mixed sections."""

    if not sections:
        return ()
    kinds = [kind for kind, _text in sections]
    texts = [text for _kind, text in sections]
    suffix = ""
    if len(kinds) > 2 and kinds[-1] == _OFFICIAL_HANDOFF:
        suffix = "\n\nRelated official information: " + texts[-1]
        kinds = kinds[:-1]
        texts = texts[:-1]
    rendered = _canonical_core_live_or_mixed_answer(kinds, texts)
    if rendered is None:
        return ()
    return tuple(item + suffix for item in rendered)


def _canonical_core_live_or_mixed_answer(
    kinds: list[str],
    texts: list[str],
) -> tuple[str, ...] | None:
    if kinds == [_CURRENT_RECORDS]:
        return (texts[0],)
    if kinds == [_CURRENT_RECORDS, _REVIEWED_GUIDANCE]:
        return (
            texts[0] + "\n\n" + texts[1],
            texts[0] + "\n\nPreparedness guidance: " + texts[1],
        )
    if kinds == [_CURRENT_RECORDS, _GENERAL_BACKGROUND]:
        return (texts[0] + "\n\nGeneral background: " + texts[1],)
    if kinds in (
        [_CURRENT_RECORDS, _OFFICIAL_HANDOFF],
        [_UNCERTAINTY, _OFFICIAL_HANDOFF],
    ):
        return (texts[0] + "\n\nRelated official information: " + texts[1],)
    if kinds in (
        [_OFFICIAL_HANDOFF, _REVIEWED_GUIDANCE],
        [_UNCERTAINTY, _REVIEWED_GUIDANCE],
    ):
        return (texts[0] + "\n\nPreparedness guidance: " + texts[1],)
    if kinds in (
        [_OFFICIAL_HANDOFF, _GENERAL_BACKGROUND],
        [_UNCERTAINTY, _GENERAL_BACKGROUND],
    ):
        return (texts[0] + "\n\nGeneral background: " + texts[1],)
    if _CONFLICTING_GUIDANCE in kinds:
        conflict = next(
            text
            for kind, text in zip(kinds, texts, strict=True)
            if kind == _CONFLICTING_GUIDANCE
        )
        rendered = _render_sectioned_conflict_answer(
            tuple(zip(kinds, texts, strict=True)), conflict
        )
        return (rendered,) if rendered else None
    return None


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
