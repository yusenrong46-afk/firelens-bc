#!/usr/bin/env python3
"""Adaptive vs baseline retrieval dry-run. Sealed labels are never opened."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from firelens.benchmark import load_benchmark
from firelens.benchmark_support import ranking_metrics
from firelens.config import FireLensConfig
from firelens.evaluation.common import ROOT
from firelens.evaluation.v1_6_standard import load_v1_6_standard

DEV_SPLIT = "development"
EMBED_USD_PER_MILLION_TOKENS = 0.02
RERANK_USD_PER_CALL = 0.02
TOKENS_PER_QUERY = 500
BUFFER = 1.2


def _authorized() -> bool:
    flag = os.environ.get("FIRELENS_PAID_RETRIEVAL_BENCHMARK_AUTHORIZED") == "1"
    raw = os.environ.get("FIRELENS_MAX_RETRIEVAL_BENCHMARK_USD") or ""
    try:
        ceiling = float(raw)
    except ValueError:
        ceiling = 0.0
    return flag and ceiling > 0


def _ceiling() -> float:
    return float(os.environ.get("FIRELENS_MAX_RETRIEVAL_BENCHMARK_USD") or "0")


def development_roster(root: Path) -> list[str]:
    dataset = load_benchmark(
        root / "data/evaluation/benchmark_v1.yaml", require_release_shape=False
    )
    return [
        case.id
        for case in dataset.cases
        if case.split == DEV_SPLIT and case.acceptable_evidence
    ]


def cost_estimate(case_count: int) -> dict[str, float | int]:
    standard = load_v1_6_standard(ROOT)
    max_queries = standard.retrieval_bounds.max_queries
    strategies = 2
    max_embed = case_count * strategies * max_queries
    max_rerank = max_embed
    embed_usd = max_embed * TOKENS_PER_QUERY / 1_000_000 * EMBED_USD_PER_MILLION_TOKENS
    rerank_usd = max_rerank * RERANK_USD_PER_CALL
    maximum_usd = round((embed_usd + rerank_usd) * BUFFER, 4)
    return {
        "development_cases": case_count,
        "strategies": strategies,
        "max_queries_per_strategy": max_queries,
        "max_embedding_calls": max_embed,
        "max_rerank_calls": max_rerank,
        "estimated_maximum_usd": maximum_usd,
        "embed_usd_per_million_tokens": EMBED_USD_PER_MILLION_TOKENS,
        "rerank_usd_per_call": RERANK_USD_PER_CALL,
    }


def metric_self_check() -> dict[str, str]:
    assert callable(ranking_metrics)
    return {"ranking_metrics": "import_ok"}


def dry_run(root: Path) -> dict[str, object]:
    config = FireLensConfig.from_env(root)
    roster = development_roster(root)
    estimate = cost_estimate(len(roster))
    paid = _authorized()
    ceiling = _ceiling()
    would_exceed = bool(paid and float(estimate["estimated_maximum_usd"]) > ceiling)
    command = (
        "FIRELENS_PAID_RETRIEVAL_BENCHMARK_AUTHORIZED=1 "
        f"FIRELENS_MAX_RETRIEVAL_BENCHMARK_USD={max(ceiling, float(estimate['estimated_maximum_usd']))} "
        ".venv/bin/python scripts/v1_6_round2_retrieval.py --paid"
    )
    return {
        "schema_version": "firelens_v1_6_round2_retrieval.v1",
        "mode": "dry_run" if not paid or would_exceed else "authorized_not_executed_here",
        # This function only estimates a paid run; it never opens a provider
        # session. Authorization and budget headroom therefore cannot upgrade
        # the evidence class beyond BLOCKED.
        "evidence_class": "BLOCKED",
        "default_strategy": config.retrieval_strategy,
        "adaptive_default": False,
        "sealed_labels_inspected": False,
        "development_case_count": len(roster),
        "pairing": {"baseline": "baseline", "candidate": "adaptive_v1", "same_corpus": True},
        "metric_self_check": metric_self_check(),
        "cost_estimate": estimate,
        "paid_authorized": paid,
        "approved_ceiling_usd": ceiling,
        "would_exceed_ceiling": would_exceed,
        "provider_metrics": "BLOCKED",
        "h4_decision": "keep_experimental_disabled",
        "paid_command": command,
        "note": (
            "FakeProvider ranking is not H4 evidence. Promote adaptive_v1 only after "
            "paired development thresholds, H8, and sealed 46/47 x3 on an unchanged candidate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--paid", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/reports/V1_6_ROUND2_RETRIEVAL_DRY_RUN.json",
    )
    args = parser.parse_args()
    if args.paid:
        payload = dry_run(ROOT)
        if payload["evidence_class"] != "EXECUTED":
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
        payload["evidence_class"] = "BLOCKED"
        payload["provider_metrics"] = "BLOCKED"
        payload["reason"] = (
            "Paid execution is prepared but this Round-2 command refuses to start "
            "provider calls without a separate confirmed OpenRouter session."
        )
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    payload = dry_run(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
