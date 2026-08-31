"""Pure ProductBench v2 report assembly."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from firelens.evaluation import productbench_v2_accounting


def build(
    manifest: dict[str, Any],
    tier: str,
    results: list[dict[str, Any]],
    *,
    max_cost_usd: float,
    provider_boundary: str,
    identity: Callable[[dict[str, Any]], dict[str, Any]],
    reported_cost_usd: float = 0.0,
    offline_execution: dict[str, Any] | None = None,
    provider_call_counts: dict[str, int] | None = None,
    cost_verified: bool | None = None,
    provider_budget: dict[str, object] | None = None,
) -> dict[str, Any]:
    expected = manifest["tiers"][tier]
    complete = [item["id"] for item in results] == expected
    cost_known = bool(
        isinstance(max_cost_usd, int | float)
        and not isinstance(max_cost_usd, bool)
        and math.isfinite(float(max_cost_usd))
        and max_cost_usd >= 0
        and isinstance(reported_cost_usd, int | float)
        and not isinstance(reported_cost_usd, bool)
        and math.isfinite(float(reported_cost_usd))
        and reported_cost_usd >= 0
    )
    ceiling_exceeded = not cost_known or reported_cost_usd > max_cost_usd
    numeric_call_counts = (
        dict(provider_call_counts)
        if provider_call_counts is not None
        and all(
            isinstance(value, int) and value >= 0 for value in provider_call_counts.values()
        )
        else {}
    )
    total_calls = productbench_v2_accounting.billable_call_count(numeric_call_counts)
    report: dict[str, Any] = {
        "schema_version": "firelens.productbench_report.v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": identity(manifest),
        "provider_boundary": provider_boundary,
        "execution_complete": complete and not ceiling_exceeded and cost_verified is not False,
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "case_count": len(results),
        "cost": {
            "max_cost_usd": max_cost_usd,
            "reported_cost_usd": reported_cost_usd,
            "ceiling_exceeded": ceiling_exceeded,
        },
        "provider_activity": {
            "call_counts": numeric_call_counts,
            "total_calls": sum(numeric_call_counts.values())
            if total_calls is None
            else total_calls,
        },
        "results": results,
    }
    if offline_execution is not None:
        report["offline_execution"] = offline_execution
    if cost_verified is not None:
        report["cost"]["cost_unverified"] = not cost_verified
    if provider_budget is not None:
        report["provider_budget"] = provider_budget
    return report
