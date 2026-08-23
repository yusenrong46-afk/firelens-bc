"""Build content-free pre-release performance evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def build_pre_release_report(
    *,
    root: Path,
    current: dict[str, Any],
    comparison: dict[str, Any],
    warmup: int,
    measured: int,
) -> dict[str, Any]:
    """Bind representative-workload measurements to Git and H8 review state."""
    compared_routes = (comparison.get("compare") or {}).get("route_p95", {})
    regressed_routes = [
        route_id for route_id, row in compared_routes.items() if row.get("regressed_over_10pct")
    ]

    def git_value(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    return {
        "evidence_class": "EXECUTED",
        "identity": {
            "branch": git_value("rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git_value("rev-parse", "HEAD"),
            "tree": git_value("rev-parse", "HEAD^{tree}"),
        },
        "label": "representative_workload_average",
        "not_fleet_average": True,
        "warmup_per_route": warmup,
        "measured_per_route": measured,
        "compare": comparison.get("compare"),
        "v1_5_status": comparison["v1_5_status"],
        "current_average_generate_calls": current["representative_average_generate_calls"],
        "pure_static_generate_calls": current.get("pure_static_generate_calls"),
        "h8_review": {
            "regressed_routes_over_10pct": regressed_routes,
            "requires_accepted_evidence": bool(regressed_routes),
            "status": (
                "NEEDS_HUMAN_TRADEOFF_ACCEPTANCE"
                if regressed_routes
                else "MEASURED_NO_ROUTE_REGRESSION"
            ),
        },
        "current_routes": {
            key: {
                "p50_ms": row["p50_ms"],
                "p95_ms": row["p95_ms"],
                "mean_generate_calls": row["mean_generate_calls"],
                "failures": row["failures"],
            }
            for key, row in current["routes"].items()
        },
    }
