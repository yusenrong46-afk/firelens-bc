#!/usr/bin/env python3
"""Focused FireLens-200 campaign for the same-day stabilization SHA."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "benchmarks" / "firelens200") not in sys.path:
    sys.path.insert(0, str(ROOT / "benchmarks" / "firelens200"))

import run_campaign  # noqa: E402

FOCUSED_IDS = (
    "FL200-013",
    "FL200-015",
    "FL200-016",
    "FL200-017",
    "FL200-018",
    "FL200-066",
    "FL200-067",
    "FL200-068",
    "FL200-069",
    "FL200-070",
    "FL200-071",
    "FL200-072",
    "FL200-073",
    "FL200-074",
    "FL200-083",
    "FL200-085",
    "FL200-106",
    "FL200-107",
    "FL200-108",
    "FL200-126",
    "FL200-127",
    "FL200-134",
    "FL200-135",
    "FL200-145",
    "FL200-146",
    "FL200-147",
    "FL200-148",
    "FL200-149",
    "FL200-164",
    "FL200-171",
    "FL200-172",
)
REPEAT_IDS = (
    "FL200-068",
    "FL200-069",
    "FL200-072",
    "FL200-083",
    "FL200-085",
    "FL200-107",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--deployment-id", default="")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evals" / "sameday_stabilization",
    )
    args = parser.parse_args(argv)
    run_campaign.main(
        [
            "--base",
            args.base,
            "--commit",
            args.commit,
            "--deployment-id",
            args.deployment_id,
            "--out",
            str(args.out),
            "--ids",
            ",".join(FOCUSED_IDS),
            "--repeat-ids",
            ",".join(REPEAT_IDS),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
