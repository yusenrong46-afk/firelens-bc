#!/usr/bin/env python3
"""Create or validate a hash-bound FireLens owner semantic review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from firelens.owner_review import validate_owner_review, write_review_template
from firelens.storage import atomic_text_writer

ROOT = Path(__file__).resolve().parents[1]


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template")
    template.add_argument(
        "--report",
        type=Path,
        default=Path("output/benchmark/v1_1_conversation_live_report.json"),
    )
    template.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_owner_semantic_review.yaml"),
    )
    validate = commands.add_parser("validate")
    validate.add_argument(
        "--report",
        type=Path,
        default=Path("output/benchmark/v1_1_conversation_live_report.json"),
    )
    validate.add_argument(
        "--review",
        type=Path,
        default=Path("output/benchmark/v1_5_owner_semantic_review.yaml"),
    )
    validate.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_owner_semantic_review_summary.json"),
    )
    args = parser.parse_args()

    if args.command == "template":
        review = write_review_template(_path(args.report), _path(args.output))
        print(
            json.dumps(
                {
                    "case_count": len(review.cases),
                    "output": str(_path(args.output)),
                    "report_sha256": review.report_sha256,
                    "status": "template_created",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    summary = validate_owner_review(_path(args.report), _path(args.review))
    with atomic_text_writer(_path(args.output)) as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["qualified"] else 2)


if __name__ == "__main__":
    main()
