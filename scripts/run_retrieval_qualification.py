#!/usr/bin/env python3
"""Run the frozen V1 holdout retrieval qualification without tuning."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from firelens.config import FireLensConfig
from firelens.qualification import run_frozen_retrieval_qualification
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[1]


async def _run(args: argparse.Namespace) -> int:
    config = FireLensConfig.from_env(ROOT)
    runtime = load_runtime(config)
    try:
        report = await run_frozen_retrieval_qualification(
            runtime,
            dataset_path=ROOT / "data/evaluation/benchmark_v1.yaml",
            dataset_manifest_path=ROOT / "data/evaluation/benchmark_v1.manifest.json",
            output_path=ROOT / args.output,
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
    return 0 if all(item["complete"] for item in report["repetition_reports"]) else 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=0.75)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_frozen_holdout_retrieval.json"),
    )
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
