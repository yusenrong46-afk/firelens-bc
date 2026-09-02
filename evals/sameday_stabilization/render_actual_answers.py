#!/usr/bin/env python3
"""Render focused campaign answers for the same-day report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.jsonl"
OUT = ROOT / "actual_answers.md"

CRITICAL = {
    "FL200-068",
    "FL200-069",
    "FL200-072",
    "FL200-083",
    "FL200-085",
    "FL200-107",
}


def main() -> None:
    rows = [
        json.loads(line)
        for line in RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts = Counter(row.get("status") for row in rows)
    lines = [
        "# Same-day focused FireLens-200 answers",
        "",
        f"Rows: {len(rows)}. Status: {dict(counts)}.",
        "",
    ]
    for row in rows:
        case_id = row.get("case_id")
        marker = " CRITICAL" if case_id in CRITICAL else ""
        lines.extend(
            [
                f"## {case_id}#{row.get('run_number')}{marker} — {row.get('status')}",
                "",
                f"- question: {row.get('question')}",
                f"- mode: {row.get('response_mode')} / {row.get('provenance_class')}",
                f"- reason: {row.get('reason_code')}",
                f"- selected: {row.get('selected_live_result_id')}",
                f"- hard: {row.get('hard_failures')}",
                "",
                str(row.get("visible_answer") or "").strip() or "_empty_",
                "",
            ]
        )
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
