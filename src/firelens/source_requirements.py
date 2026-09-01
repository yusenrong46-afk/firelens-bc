"""Application-owned source requirements for answer routing."""

from __future__ import annotations

import re
from enum import StrEnum

from firelens.guidance_capabilities import (
    GuidedQuestion,
    exact_guided_question,
    resolve_capability,
)


class SourceRequirement(StrEnum):
    GENERAL_ALLOWED = "general_allowed"
    REVIEWED_PREFERRED = "reviewed_preferred"
    REVIEWED_REQUIRED = "reviewed_required"


_REVIEWED_GUIDANCE_HINT = re.compile(
    r"\b(?:evacuat(?:ion|e)|grab-and-go|go[- ]bag|firesmart|wildfire rank|"
    r"stages? of control|wildfire smoke|n95|respirator|home ignition)\b",
    re.IGNORECASE,
)
_EXPLICIT_REVIEWED_SOURCE = re.compile(
    r"\b(?:official|according\s+to\s+(?:official\s+)?guidance|reviewed|source|"
    r"document|guide)\b",
    re.IGNORECASE,
)


def guided_capability(
    question: str, *, place_label: str | None = None
) -> GuidedQuestion | None:
    return exact_guided_question(question, place_label=place_label)


def source_requirement_for_question(
    question: str,
    *,
    place_label: str | None = None,
) -> SourceRequirement:
    """Return the strictest application-owned requirement for this request."""

    item = guided_capability(question, place_label=place_label)
    if item is not None:
        if item.source_lane == "official_live":
            return SourceRequirement.GENERAL_ALLOWED
        return SourceRequirement.REVIEWED_REQUIRED
    capability = resolve_capability(question, place_label=place_label)
    if capability is not None and capability.source_mode == "corpus":
        return SourceRequirement.REVIEWED_REQUIRED
    if _EXPLICIT_REVIEWED_SOURCE.search(question):
        return SourceRequirement.REVIEWED_REQUIRED
    if _REVIEWED_GUIDANCE_HINT.search(question):
        return SourceRequirement.REVIEWED_PREFERRED
    return SourceRequirement.GENERAL_ALLOWED


def source_lane_for_question(
    question: str,
    *,
    place_label: str | None = None,
) -> str | None:
    item = guided_capability(question, place_label=place_label)
    return item.source_lane if item is not None else None
