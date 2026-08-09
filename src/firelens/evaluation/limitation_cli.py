"""Limitation probe for FireLens BC — evaluation only; does not modify app code.

Builds throwaway corpora under output/naive_user_probe/, asks cases through the
existing StaticRAGService, and writes scored JSON results.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from firelens.answering.generate import BACKGROUND_SYSTEM_PROMPT
from firelens.answering.generate import SYSTEM_PROMPT as GENERATION_SYSTEM_PROMPT
from firelens.answering.planner import SYSTEM_PROMPT as PLANNER_SYSTEM_PROMPT
from firelens.benchmark import _usage_cost, _usage_total
from firelens.config import FireLensConfig
from firelens.contracts import ConversationTurn, QueryRequest
from firelens.evaluation.limitation_cases import (
    ProbeCase,
    build_generalization_cases,
    build_jailbreak_cases,
    build_naive_cases,
    dump_yaml_cases,
)
from firelens.evaluation.limitation_runtime import (
    _materialize_profile,
    score_case,
)
from firelens.retrieval.embeddings import sha256_file
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output" / "naive_user_probe"
DATA_EVAL = ROOT / "data" / "evaluation"
SUITE_PATHS = {
    "naive": DATA_EVAL / "naive_user_probe.v1.yaml",
    "jailbreak": DATA_EVAL / "rag_jailbreak_probe.v1.yaml",
    "generalization": DATA_EVAL / "rag_generalization_probe.v1.yaml",
}


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


async def run_suite(
    cases: list[ProbeCase],
    *,
    limit: int | None,
    max_cost_usd: float | None,
) -> dict[str, Any]:
    base = FireLensConfig.from_env(ROOT)
    selected = cases[:limit] if limit is not None else cases

    # Group by profile for fewer runtime loads.
    by_profile: dict[str, list[ProbeCase]] = {}
    for case in selected:
        by_profile.setdefault(case.corpus_profile, []).append(case)

    results: list[dict[str, Any]] = []
    started = time.time()
    reported_cost_usd = 0.0
    budget_exceeded = False

    for profile, profile_cases in by_profile.items():
        if max_cost_usd is not None and reported_cost_usd >= max_cost_usd:
            budget_exceeded = True
            break
        print(f"[probe] materializing corpus profile={profile} cases={len(profile_cases)}")
        config = await _materialize_profile(profile, base)
        admission_manifest = json.loads(config.corpus_manifest_path.read_text(encoding="utf-8"))
        runtime = load_runtime(config)
        if runtime.service is None:
            for case in profile_cases:
                results.append(
                    {
                        "id": case.id,
                        "suite": case.suite,
                        "bucket": case.bucket,
                        "question": case.question,
                        "corpus_profile": profile,
                        "passed": False,
                        "error": "; ".join(runtime.problems) or "runtime not ready",
                    }
                )
            await runtime.aclose()
            continue
        try:
            for case in profile_cases:
                if max_cost_usd is not None and reported_cost_usd >= max_cost_usd:
                    budget_exceeded = True
                    break
                print(f"[probe] {case.id} ({case.bucket})")
                t0 = time.time()
                request = QueryRequest(
                    question=case.question,
                    history=[
                        ConversationTurn(
                            role=cast(Literal["user", "assistant"], h["role"]),
                            content=h["content"],
                        )
                        for h in case.history
                    ],
                )
                try:
                    execution = await runtime.service.execute_ask(request)
                    response = execution.response
                    scored = score_case(
                        case,
                        response,
                        execution=execution,
                        admission_manifest=admission_manifest,
                    )
                    provider_usage: dict[str, Any] = {
                        "retrieval": execution.retrieval.provider_usage,
                        "generation": [item.usage for item in execution.generations],
                    }
                    scored.update(
                        {
                            "provider_models": {
                                **execution.retrieval.provider_models,
                                **{
                                    item.stage: item.model
                                    for item in execution.generations
                                    if item.model is not None
                                },
                            },
                            "provider_attempts": {
                                **execution.retrieval.provider_attempts,
                                **{item.stage: item.attempts for item in execution.generations},
                            },
                            "provider_tokens": {
                                field: _usage_total(provider_usage, field)
                                for field in (
                                    "prompt_tokens",
                                    "completion_tokens",
                                    "total_tokens",
                                )
                            },
                            "reported_cost_usd": _usage_cost(provider_usage),
                        }
                    )
                    reported_cost_usd += float(scored["reported_cost_usd"])
                except Exception as exc:  # noqa: BLE001 - probe must continue
                    scored = {
                        "passed": False,
                        "error": str(exc),
                        "response_mode": None,
                        "status": "error",
                    }
                scored.update(
                    {
                        "id": case.id,
                        "suite": case.suite,
                        "bucket": case.bucket,
                        "question": case.question,
                        "expected_modes": list(case.expected_modes),
                        "corpus_profile": profile,
                        "notes": case.notes,
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                    }
                )
                results.append(scored)
                print(
                    f"  -> mode={scored.get('response_mode')} passed={scored.get('passed')} "
                    f"{scored.get('latency_ms')}ms"
                )
        finally:
            await runtime.aclose()

    by_bucket: dict[str, dict[str, int]] = {}
    for row in results:
        bucket = row["bucket"]
        stats = by_bucket.setdefault(bucket, {"total": 0, "passed": 0})
        stats["total"] += 1
        stats["passed"] += int(bool(row.get("passed")))

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "qualification_manifest": {
            "commit": _git_commit(),
            "corpus": {
                "chunks_sha256": sha256_file(base.corpus_path),
                "manifest_sha256": sha256_file(base.corpus_manifest_path),
                "vector_manifest_sha256": sha256_file(base.vector_manifest_path),
            },
            "datasets": {
                suite: {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256_file(path),
                    "case_count": sum(1 for case in selected if case.suite == suite),
                }
                for suite, path in SUITE_PATHS.items()
                if any(case.suite == suite for case in selected)
            },
            "prompts": {
                "planner_system_sha256": _text_sha256(PLANNER_SYSTEM_PROMPT),
                "grounded_generation_system_sha256": _text_sha256(GENERATION_SYSTEM_PROMPT),
                "background_generation_system_sha256": _text_sha256(BACKGROUND_SYSTEM_PROMPT),
            },
            "models": {
                "embedding": base.embedding_model,
                "rerank": base.rerank_model,
                "generation_and_planning": base.generation_model,
                "provider_base_url": base.openrouter_base_url,
            },
            "retrieval": {
                "strategy": base.retrieval_text_strategy.value,
                "bm25_top_k": base.bm25_top_k,
                "vector_top_k": base.vector_top_k,
                "fused_top_k": base.fused_top_k,
                "rerank_top_k": base.rerank_top_k,
                "rrf_k": base.rrf_k,
            },
        },
        "requested_case_count": len(selected),
        "case_count": len(results),
        "complete": len(results) == len(selected) and not budget_exceeded,
        "passed": sum(1 for r in results if r.get("passed")),
        "failed": sum(1 for r in results if not r.get("passed")),
        "elapsed_sec": round(time.time() - started, 1),
        "provider_tokens": {
            field: sum(int(row.get("provider_tokens", {}).get(field, 0)) for row in results)
            for field in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "cost_budget_usd": max_cost_usd,
        "cost_budget_exceeded": budget_exceeded,
        "reported_cost_usd": reported_cost_usd,
        "by_bucket": by_bucket,
        "results": results,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=1.25,
        help="Stop before the next case once reported OpenRouter cost reaches this ceiling",
    )
    parser.add_argument(
        "--case-ids",
        default="",
        help="Optional comma-separated case IDs for a focused calibration run",
    )
    parser.add_argument(
        "--suites",
        default="naive,jailbreak,generalization",
        help="Comma-separated suites to run",
    )
    parser.add_argument(
        "--dump-only",
        action="store_true",
        help="Only write YAML case files; do not call the model",
    )
    args = parser.parse_args()
    if args.max_cost_usd <= 0:
        parser.error("--max-cost-usd must be greater than zero")

    OUT.mkdir(parents=True, exist_ok=True)
    naive = build_naive_cases()
    jail = build_jailbreak_cases()
    gen = build_generalization_cases()
    dump_yaml_cases(naive, DATA_EVAL / "naive_user_probe.v1.yaml")
    dump_yaml_cases(jail, DATA_EVAL / "rag_jailbreak_probe.v1.yaml")
    dump_yaml_cases(gen, DATA_EVAL / "rag_generalization_probe.v1.yaml")
    print(f"wrote cases: naive={len(naive)} jailbreak={len(jail)} generalization={len(gen)}")
    if args.dump_only:
        return

    wanted = {s.strip() for s in args.suites.split(",") if s.strip()}
    cases: list[ProbeCase] = []
    if "naive" in wanted:
        cases.extend(naive)
    if "jailbreak" in wanted:
        cases.extend(jail)
    if "generalization" in wanted:
        cases.extend(gen)
    case_ids = {case_id.strip() for case_id in args.case_ids.split(",") if case_id.strip()}
    if case_ids:
        cases = [case for case in cases if case.id in case_ids]
        missing = case_ids - {case.id for case in cases}
        if missing:
            parser.error("unknown or excluded case IDs: " + ", ".join(sorted(missing)))

    summary = asyncio.run(run_suite(cases, limit=args.limit, max_cost_usd=args.max_cost_usd))
    out_path = OUT / "results.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"saved {out_path} passed={summary['passed']}/{summary['case_count']}")
    if not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
