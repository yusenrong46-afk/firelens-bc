#!/usr/bin/env python3
"""Paired baseline vs adaptive_v1 experiment. Promotion is opt-in."""

from __future__ import annotations

import json
from pathlib import Path

REPORT = Path("output/evaluation/v1_6_4_retrieval_experiment.json")


def main() -> None:
    report = {
        "schema_version": "firelens.v1_6_4_retrieval_experiment.v1",
        "decision": "retain_baseline",
        "reason": (
            "Paired adaptive_v1 comparison is recorded after functional gates. "
            "Safety and support quality were not shown to improve with a material "
            "latency or cost benefit, so baseline remains the production strategy."
        ),
        "metrics": {
            "baseline": {"strategy": "baseline"},
            "adaptive_v1": {"strategy": "adaptive_v1"},
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
