#!/usr/bin/env python3
"""Run the frozen V1 holdout retrieval qualification without tuning."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from firelens.config import FireLensConfig
from firelens.qualification import run_frozen_retrieval_qualification
from firelens.retrieval_review import validate_retrieval_owner_review
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]


def _commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


async def _run(args: argparse.Namespace) -> int:
    owner_review_path = ROOT / args.owner_review
    if not owner_review_path.exists():
        print(
            json.dumps(
                {
                    "qualified": False,
                    "reason": "owner_review_missing",
                    "owner_review": str(owner_review_path),
                    "paid_calls_started": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    owner_review = validate_retrieval_owner_review(ROOT / args.dataset, owner_review_path)
    if not owner_review["qualified"]:
        print(
            json.dumps(
                {
                    "qualified": False,
                    "reason": "owner_review_not_qualified",
                    "approved_case_count": owner_review["approved_case_count"],
                    "case_count": owner_review["case_count"],
                    "paid_calls_started": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    config = FireLensConfig.from_env(ROOT).model_copy(update={"build_commit": _commit()})
    runtime = load_runtime(config)
    try:
        report = await run_frozen_retrieval_qualification(
            runtime,
            dataset_path=ROOT / args.dataset,
            dataset_manifest_path=ROOT / args.manifest,
            output_path=ROOT / args.output,
            owner_review_path=owner_review_path,
            repetitions=args.repetitions,
            max_cost_usd=args.max_cost_usd,
        )
    finally:
        await runtime.aclose()
    print(
        json.dumps(
            {
                "qualified": report["qualified"],
                "owner_approved": report["owner_approved"],
                "case_count_per_repetition": report["case_count_per_repetition"],
                "reported_cost_usd": report["reported_cost_usd"],
                "repeated_rankings_match": report["repeated_rankings_match"],
                "repetitions": [
                    {
                        "recall_at_5": item["recall_at_5"],
                        "mrr_at_5": item["mrr_at_5"],
                        "complete": item["complete"],
                    }
                    for item in report["repetition_reports"]
                ],
                "limitations": report["qualification_limitations"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["qualified"] else 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=0.75)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/evaluation/benchmark_v1_5_sealed_retrieval.manifest.json"),
    )
    parser.add_argument(
        "--owner-review",
        type=Path,
        default=Path("output/benchmark/v1_5_retrieval_owner_review.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_frozen_holdout_retrieval.json"),
    )
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
