"""Fail-closed receipt accounting for ProductBench provider runs."""

from __future__ import annotations

import math
from collections.abc import Callable

_RECEIPT_FIELDS = {
    "stage",
    "endpoint",
    "provider_response_id",
    "model",
    "attempts",
    "usage",
    "cost_usd",
    "cost_evidence",
}
_BILLABLE_CALL_FIELDS = (
    "plan",
    "embed",
    "rerank",
    "generate_contexts",
    "generate_grounded",
    "generate_background",
    "chat_turn",
)


def billable_call_count(counts: dict[str, int] | None) -> int | None:
    if counts is None or any(name not in counts for name in _BILLABLE_CALL_FIELDS):
        return None
    values = [counts[name] for name in _BILLABLE_CALL_FIELDS]
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values
    ):
        return None
    return sum(values)


def receipt_delta(
    before: list[dict[str, object]] | None, after: list[dict[str, object]] | None
) -> list[dict[str, object]] | None:
    if (
        before is None
        or after is None
        or len(after) < len(before)
        or after[: len(before)] != before
    ):
        return None
    return after[len(before) :]


def verify_receipts(
    receipts: list[dict[str, object]] | None,
    *,
    logical_calls: int | None,
    canonical_sha256: Callable[[object], str],
) -> tuple[dict[str, object], float, bool]:
    """Verify one case's successful-call receipts and exact returned costs."""

    rows = receipts if receipts is not None else []
    problems: list[str] = []
    if logical_calls is None:
        problems.append("logical_call_count_missing")
    elif len(rows) != logical_calls:
        problems.append("receipt_count_mismatch")
    total = 0.0
    for row in rows:
        if set(row) != _RECEIPT_FIELDS:
            problems.append("receipt_shape_invalid")
            continue
        if (
            not isinstance(row["stage"], str)
            or not row["stage"]
            or not isinstance(row["endpoint"], str)
            or not row["endpoint"]
            or not isinstance(row["provider_response_id"], str)
            or not row["provider_response_id"]
            or not isinstance(row["model"], str)
            or not row["model"]
            or not isinstance(row["attempts"], int)
            or isinstance(row["attempts"], bool)
            or row["attempts"] < 1
            or not isinstance(row["usage"], dict)
        ):
            problems.append("receipt_identity_invalid")
            continue
        cost = row["cost_usd"]
        if (
            isinstance(cost, bool)
            or not isinstance(cost, int | float)
            or not math.isfinite(float(cost))
            or cost < 0
        ):
            problems.append("receipt_cost_missing_or_invalid")
            continue
        exact_cost = float(cost)
        expected_evidence = (
            "provider_usage_cost_explicit_zero" if exact_cost == 0.0 else "provider_usage_cost"
        )
        if row["cost_evidence"] != expected_evidence:
            problems.append("receipt_cost_evidence_invalid")
            continue
        if row["usage"].get("cost") != cost:
            problems.append("receipt_usage_cost_mismatch")
            continue
        total += exact_cost
    verified = not problems
    evidence: dict[str, object] = {
        "logical_provider_calls": logical_calls,
        "receipt_count": len(rows),
        "receipt_sha256": canonical_sha256(rows),
        "receipts": rows,
        "cost_verified": verified,
        "cost_verification_errors": problems,
    }
    return evidence, total, verified
