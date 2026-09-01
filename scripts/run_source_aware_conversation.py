#!/usr/bin/env python3
"""Run the source-aware conversation evaluation without network or models."""

from __future__ import annotations

import argparse
from pathlib import Path

from firelens.evaluation.source_aware_conversation import DATASET_PATH, run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/evaluation/source_aware_conversation_offline.json"),
    )
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args()
    # The runner intentionally reads the canonical dataset and refuses a
    # mutable alternate contract through the public CLI.
    if args.dataset.resolve() != DATASET_PATH.resolve():
        parser.error("--dataset cannot replace the canonical unsealed dataset")
    return run(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
