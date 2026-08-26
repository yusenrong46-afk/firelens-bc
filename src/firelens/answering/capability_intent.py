"""Deterministic recognition for FireLens capability and trust questions."""

from __future__ import annotations

import re

from firelens.answering.intent_safety import TRUST_EXPLANATION_PATTERN

_CAPABILITY_PATTERNS = (
    r"^(?:hi|hello|hey|good (?:morning|afternoon|evening))[!., ]*$",
    r"\bwhat (?:can|could) i ask (?:you|firelens)(?: about)?\b",
    r"\bwhat (?:can|could) (?:you|firelens) (?:do|help(?: me)? with)\b",
    r"\bwhat does firelens (?:do|cover|offer)\b",
    r"\b(?:what|which) (?:documents|sources|topics).{0,80}\b(?:collection|know|use|cover)\b",
    r"\b(?:show|give) me (?:a few )?(?:example|sample|suggested) questions\b",
    r"\bhelp me (?:use|understand) firelens\b",
    r"\b(?:do you know anything|what do you know) about\b",
    r"\bwhat (?:parts|areas|aspects|kinds).{0,60}\bfirelens (?:explain|cover|answer)\b",
    r"\bhow do (?:your|firelens) citations work\b",
    r"\bhow does firelens\b.{0,60}\b(?:map|maps|work|data|citations)\b",
    TRUST_EXPLANATION_PATTERN,
    r"\bwhat is (?:actually )?inside (?:the )?(?:source )?collection\b",
    r"\b(?:do not|don't) know what is in the collection\b",
    r"\b(?:where|how) should i start\b.{0,40}\b(?:firelens|collection|guidance)\b",
    r"\b(?:kinds|types) of firelens questions\b",
    r"^(?:what\s+now|then\s+what|help|help\s+me|where\s+do\s+i\s+start)[?!. ]*$",
)


def is_capability_question(question: str) -> bool:
    """Return whether a question asks how to understand or use FireLens."""

    return any(re.search(pattern, question) for pattern in _CAPABILITY_PATTERNS)
