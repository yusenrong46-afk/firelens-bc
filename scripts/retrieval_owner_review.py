#!/usr/bin/env python3
"""Create or validate the hash-bound sealed-retrieval owner review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from firelens.retrieval_review import (
    validate_retrieval_owner_review,
    write_retrieval_review_packet,
    write_retrieval_review_template,
)
from firelens.storage import atomic_text_writer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = Path("data/evaluation/benchmark_v1_5_sealed_retrieval.yaml")
DEFAULT_REVIEW = Path("output/benchmark/v1_5_retrieval_owner_review.yaml")


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template")
    template.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    template.add_argument("--output", type=Path, default=DEFAULT_REVIEW)
    packet = commands.add_parser("packet")
    packet.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    packet.add_argument(
        "--corpus-chunks",
        type=Path,
        default=Path("data/processed/firelens_static_corpus.chunks.jsonl"),
    )
    packet.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_retrieval_owner_review.md"),
    )
    validate = commands.add_parser("validate")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    validate.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    validate.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_retrieval_owner_review_summary.json"),
    )
    args = parser.parse_args()

    if args.command == "template":
        review = write_retrieval_review_template(_path(args.dataset), _path(args.output))
        print(
            json.dumps(
                {
                    "case_count": len(review.cases),
                    "dataset_sha256": review.dataset_sha256,
                    "output": str(_path(args.output)),
                    "status": "template_created",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "packet":
        write_retrieval_review_packet(
            _path(args.dataset), _path(args.corpus_chunks), _path(args.output)
        )
        print(
            json.dumps(
                {"output": str(_path(args.output)), "status": "packet_created"},
                indent=2,
                sort_keys=True,
            )
        )
        return

    summary = validate_retrieval_owner_review(_path(args.dataset), _path(args.review))
    with atomic_text_writer(_path(args.output)) as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["qualified"] else 2)


if __name__ == "__main__":
    main()
