"""Replay the exploratory product-question catalog through the real local API stack."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.evaluation.product_question_cases import (
    ProductQuestionCase,
    build_product_question_cases,
)
from firelens.live import LiveDataService
from firelens.runtime import load_runtime

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "output/product-question-audit"
CATALOG_PATH = ROOT / "data/evaluation/product_question_probe.v1.json"
_DEAD_END_COPY = (
    "selected evidence does not directly support",
    "try a more specific question",
    "official current information required",
)


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _catalog_payload(cases: list[ProductQuestionCase]) -> dict[str, object]:
    rows = [case.as_dict() for case in cases]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "dataset_version": "product_question_probe.v1",
        "dataset_role": "exploratory_development_not_sealed_qualification",
        "case_count": len(rows),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "cases": rows,
    }


def dump_catalog(cases: list[ProductQuestionCase], path: Path = CATALOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_catalog_payload(cases), indent=2) + "\n", encoding="utf-8")


async def _key_usage(config: FireLensConfig) -> float | None:
    if config.openrouter_api_key is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/key",
                headers={
                    "Authorization": (f"Bearer {config.openrouter_api_key.get_secret_value()}")
                },
            )
        if response.status_code != 200:
            return None
        usage = response.json().get("data", {}).get("usage")
        return float(usage) if isinstance(usage, int | float) else None
    except (httpx.HTTPError, TypeError, ValueError):
        return None


def _score(
    case: ProductQuestionCase,
    *,
    status_code: int,
    response: dict[str, Any],
    selected_result_id: str | None,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    mode = response.get("response_mode")
    answer = response.get("answer")
    if status_code != 200:
        issues.append(f"http_{status_code}")
    if response.get("status") != "answer":
        issues.append("non_answer_status")
    if mode not in case.expected_modes:
        issues.append(f"unexpected_mode:{mode}")
    if not isinstance(answer, str) or not answer.strip():
        issues.append("missing_answer")
    elif any(copy in answer.casefold() for copy in _DEAD_END_COPY):
        issues.append("dead_end_copy")
    if case.location_expectation == "inferred":
        if mode == "requires_input":
            issues.append("redundant_location_request")
        if not isinstance(response.get("resolved_location"), dict):
            issues.append("missing_map_focus")
    elif case.location_expectation == "required":
        if mode != "requires_input" or not isinstance(response.get("required_input"), dict):
            issues.append("missing_location_request")
    if (
        case.context_fixture == "first_incident"
        and case.location_expectation != "required"
        and selected_result_id is not None
        and response.get("selected_live_result_id") != selected_result_id
    ):
        issues.append("selected_record_not_preserved")
    return not issues, issues


async def run_probe(
    cases: list[ProductQuestionCase],
    *,
    max_cost_usd: float,
) -> dict[str, Any]:
    config = FireLensConfig.from_env(ROOT).model_copy(
        update={"anonymous_rate_limit": max(1_000, len(cases) * 4)}
    )
    runtime = load_runtime(config)
    live_service = LiveDataService()
    app = create_app(config, runtime=runtime, live_service=live_service)
    transport = httpx.ASGITransport(app=app)
    usage_before = await _key_usage(config)
    selected_result_id: str | None = None
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    stopped_for_budget = False
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://firelens.test",
            timeout=config.public_request_deadline_seconds + 5,
        ) as client:
            for index, case in enumerate(cases, start=1):
                if index > 1 and index % 10 == 1 and usage_before is not None:
                    current_usage = await _key_usage(config)
                    if (
                        current_usage is not None
                        and current_usage - usage_before >= max_cost_usd
                    ):
                        stopped_for_budget = True
                        break
                body: dict[str, Any] = {
                    "question": case.question,
                    "history": list(case.history),
                    "context": {},
                }
                case_selected_result_id: str | None = None
                if case.context_fixture == "first_incident":
                    # Live records can change while a long replay is running. Refresh the
                    # fixture immediately before each selected-result journey so the probe
                    # tests context handling rather than source churn from minutes earlier.
                    map_response = await client.get(
                        "/api/v1/live/map?layers=incidents,perimeters,evacuations"
                    )
                    if map_response.status_code == 200:
                        case_selected_result_id = next(
                            (
                                item.get("result_id")
                                for item in map_response.json().get("results", [])
                                if item.get("kind") == "incident"
                            ),
                            None,
                        )
                    if case_selected_result_id:
                        selected_result_id = case_selected_result_id
                        body["context"] = {"selected_live_result_id": case_selected_result_id}
                case_started = time.perf_counter()
                try:
                    response = await client.post("/api/v1/ask", json=body)
                    payload = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    response_status = 0
                    payload = {
                        "status": "error",
                        "response_mode": None,
                        "answer": None,
                        "error": type(exc).__name__,
                    }
                else:
                    response_status = response.status_code
                passed, issues = _score(
                    case,
                    status_code=response_status,
                    response=payload,
                    selected_result_id=case_selected_result_id,
                )
                results.append(
                    {
                        **case.as_dict(),
                        "passed": passed,
                        "issues": issues,
                        "http_status": response_status,
                        "latency_ms": round((time.perf_counter() - case_started) * 1_000, 1),
                        "selected_result_fixture": case_selected_result_id,
                        "response": payload,
                    }
                )
                print(
                    f"[{index:03d}/{len(cases):03d}] {case.id} "
                    f"mode={payload.get('response_mode')} passed={passed}",
                    flush=True,
                )
    finally:
        await runtime.aclose()
        await live_service.aclose()

    usage_after = await _key_usage(config)
    spend = (
        max(0.0, usage_after - usage_before)
        if usage_before is not None and usage_after is not None
        else None
    )
    bucket_totals = Counter(row["bucket"] for row in results)
    bucket_passed = Counter(row["bucket"] for row in results if row["passed"])
    catalog = _catalog_payload(cases)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "dataset_version": catalog["dataset_version"],
        "dataset_sha256": catalog["sha256"],
        "requested_case_count": len(cases),
        "case_count": len(results),
        "complete": len(results) == len(cases) and not stopped_for_budget,
        "passed": sum(1 for row in results if row["passed"]),
        "failed": sum(1 for row in results if not row["passed"]),
        "stopped_for_budget": stopped_for_budget,
        "max_cost_usd": max_cost_usd,
        "reported_openrouter_spend_usd": spend,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "selected_result_fixture": selected_result_id,
        "by_bucket": {
            bucket: {"total": total, "passed": bucket_passed[bucket]}
            for bucket, total in sorted(bucket_totals.items())
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="run")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--buckets", default="")
    parser.add_argument("--max-cost-usd", type=float, default=0.75)
    parser.add_argument("--dump-only", action="store_true")
    args = parser.parse_args()
    if args.max_cost_usd <= 0:
        parser.error("--max-cost-usd must be greater than zero")

    cases = build_product_question_cases()
    dump_catalog(cases)
    if args.dump_only:
        print(f"wrote {CATALOG_PATH} cases={len(cases)}")
        return 0
    wanted_ids = {item.strip() for item in args.case_ids.split(",") if item.strip()}
    wanted_buckets = {item.strip() for item in args.buckets.split(",") if item.strip()}
    if wanted_ids:
        cases = [case for case in cases if case.id in wanted_ids]
        missing = wanted_ids - {case.id for case in cases}
        if missing:
            parser.error("unknown case IDs: " + ", ".join(sorted(missing)))
    if wanted_buckets:
        cases = [case for case in cases if case.bucket in wanted_buckets]
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        parser.error("no product-question cases selected")

    report = asyncio.run(run_probe(cases, max_cost_usd=args.max_cost_usd))
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    output_path = DEFAULT_OUT / f"{args.label}.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"saved {output_path} passed={report['passed']}/{report['case_count']} "
        f"complete={report['complete']}"
    )
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
