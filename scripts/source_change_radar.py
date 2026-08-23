#!/usr/bin/env python3
"""Inspect approved-source hash changes and write a human review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from firelens.source_radar import inspect_source_changes, write_review_packet

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", action="append", nargs=2, metavar=("ID", "PATH"))
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/source_radar/review_packet.json",
    )
    args = parser.parse_args()
    acquired = {source_id: Path(path) for source_id, path in (args.source_id or [])}
    report = inspect_source_changes(ROOT, acquired)
    write_review_packet(report, args.output)
    print(
        json.dumps(
            {key: report[key] for key in ("auto_publish", "changed_source_count")}, indent=2
        )
    )
    raise SystemExit(0 if not report["quarantine_recommended"] else 2)


if __name__ == "__main__":
    main()
