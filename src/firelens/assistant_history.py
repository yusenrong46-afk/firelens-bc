"""Deterministic assistant-history bounding used by public response contracts."""

from __future__ import annotations

from collections.abc import Iterable

ASSISTANT_HISTORY_LIMIT = 6_000


def bounded_assistant_history(text: str) -> str:
    """Return the deterministic representation allowed in a later request."""

    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("assistant history cannot be blank")
    if len(normalized) <= ASSISTANT_HISTORY_LIMIT:
        return normalized
    return normalized[: ASSISTANT_HISTORY_LIMIT - 3].rstrip() + "..."


def render_assistant_history(
    *, authority_prefix: str, answer: str, limitations: Iterable[str]
) -> str:
    """Keep authority and limitations visible while bounding a later-turn transcript."""

    normalized_prefix = " ".join(authority_prefix.split())
    normalized_answer = " ".join(answer.split())
    if not normalized_prefix or not normalized_answer:
        raise ValueError("assistant history requires authority and answer text")
    unique_limitations = list(
        dict.fromkeys(
            normalized
            for limitation in limitations
            if (normalized := " ".join(limitation.split()))
        )
    )
    answer_prefix = normalized_prefix + " Answer: "
    if not unique_limitations:
        return bounded_assistant_history(answer_prefix + normalized_answer)

    limitation_prefix = " Limitations: "
    limitation_text = " | ".join(unique_limitations)
    maximum_limitation_chars = (
        ASSISTANT_HISTORY_LIMIT - len(answer_prefix) - len(limitation_prefix) - len("...")
    )
    if len(limitation_text) > maximum_limitation_chars:
        limitation_text = limitation_text[: maximum_limitation_chars - 3].rstrip() + "..."
    answer_budget = (
        ASSISTANT_HISTORY_LIMIT
        - len(answer_prefix)
        - len(limitation_prefix)
        - len(limitation_text)
    )
    if len(normalized_answer) > answer_budget:
        normalized_answer = normalized_answer[: answer_budget - 3].rstrip() + "..."
    return answer_prefix + normalized_answer + limitation_prefix + limitation_text
