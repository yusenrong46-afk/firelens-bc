"""Validation helpers for private semantic-review input payloads."""

from __future__ import annotations

from typing import Any

from firelens.review_workspace.input_common import (
    ReviewInputError,
    _content,
    _digest,
    _exact_keys,
    _nonempty,
    _string_tuple,
)


def validate_private_input(value: Any, context: str) -> dict[str, Any]:
    """Validate one blinded semantic input without admitting outcome metadata."""

    review_input = _exact_keys(
        value,
        {"input_version", "question", "history", "rubric", "source_context"},
        context,
    )
    if review_input.get("input_version") != "firelens_semantic_holdout_review_input.v1":
        raise ReviewInputError("semantic holdout private-review-input version is unsupported")
    _content(review_input.get("question"), f"{context} question")
    history = review_input.get("history")
    if not isinstance(history, list):
        raise ReviewInputError(f"{context} history must be an array")
    for index, message in enumerate(history):
        row = _exact_keys(message, {"role", "content"}, f"{context} history {index}")
        if row.get("role") not in {"user", "assistant"}:
            raise ReviewInputError(f"{context} history role is unsupported")
        _content(row.get("content"), f"{context} history content")
    rubric = _exact_keys(
        review_input.get("rubric"),
        {
            "expected_route",
            "expected_status",
            "required_concepts",
            "forbidden_claims",
            "required_limitations",
        },
        f"{context} rubric",
    )
    _nonempty(rubric.get("expected_route"), f"{context} expected route")
    _nonempty(rubric.get("expected_status"), f"{context} expected status")
    rubric_lists = [
        _string_tuple(rubric.get(key), f"{context} {key}", sorted_unique=True)
        for key in ("required_concepts", "forbidden_claims", "required_limitations")
    ]
    if not any(rubric_lists):
        raise ReviewInputError(f"{context} rubric must contain semantic criteria")
    source_context = review_input.get("source_context")
    if not isinstance(source_context, list) or not source_context:
        raise ReviewInputError(f"{context} source context is missing")
    context_ids: list[str] = []
    for index, source in enumerate(source_context):
        row = _exact_keys(
            source,
            {"context_id", "source_id_sha256", "locator", "text"},
            f"{context} source context {index}",
        )
        context_ids.append(_nonempty(row.get("context_id"), f"{context} context ID"))
        _digest(row.get("source_id_sha256"), f"{context} source commitment")
        _content(row.get("locator"), f"{context} locator")
        _content(row.get("text"), f"{context} source text")
    if context_ids != sorted(set(context_ids)):
        raise ReviewInputError(f"{context} source context must be sorted and unique")
    return review_input
