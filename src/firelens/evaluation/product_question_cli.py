"""Replay the exploratory product-question catalog through the real local API stack."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from firelens.api import create_app
from firelens.config import FireLensConfig
from firelens.evaluation.product_question_cases import (
    ProductQuestionCase,
    build_product_question_cases,
    build_product_question_regression_cases,
    build_v1_6_user_end_cases,
)
from firelens.evaluation.productbench import (
    attach_tool_capture,
    load_productbench_cases,
    productbench_extra_issues,
    productbench_result_fields,
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

_CRITICAL_NAMED_PLACE_BUCKETS = {
    "named_place_live",
    "named_place_evacuation",
    "colloquial_and_typos",
    "regression_named_evacuation",
    "regression_perimeter",
    "regression_telegraphic_live",
}


def _nonempty_list(response: dict[str, Any], key: str) -> bool:
    value = response.get(key)
    return isinstance(value, list) and bool(value)


def _live_result_kinds(response: dict[str, Any]) -> set[str]:
    results = response.get("live_results")
    if not isinstance(results, list):
        return set()
    return {
        str(item.get("kind"))
        for item in results
        if isinstance(item, dict) and isinstance(item.get("kind"), str)
    }


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_web_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _valid_mixed_live_half(response: dict[str, Any]) -> bool:
    """Require observable official-record identity, not a kind-only placeholder."""

    results = response.get("live_results")
    if not isinstance(results, list) or not results:
        return False
    required = {
        "result_id",
        "kind",
        "authority",
        "source_url",
        "source_updated_at",
        "retrieved_at",
        "freshness",
        "status",
    }
    for result in results:
        if not isinstance(result, dict) or not required.issubset(result):
            return False
        if not all(
            _nonempty_string(result[field])
            for field in required - {"source_url", "source_updated_at", "retrieved_at"}
        ):
            return False
        if not _valid_web_url(result["source_url"]):
            return False
        if not _valid_timestamp(result["source_updated_at"]) or not _valid_timestamp(
            result["retrieved_at"]
        ):
            return False
    return True


def _valid_mixed_static_half(response: dict[str, Any]) -> bool:
    """Require claims to link to observable reviewed-evidence metadata."""

    claims = response.get("claims")
    evidence = response.get("evidence")
    if (
        not isinstance(claims, list)
        or not claims
        or not isinstance(evidence, list)
        or not evidence
    ):
        return False
    evidence_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            return False
        required = {"evidence_id", "title", "publisher", "canonical_url", "primary_text"}
        if not required.issubset(item) or not all(
            _nonempty_string(item[field]) for field in required - {"canonical_url"}
        ):
            return False
        if not _valid_web_url(item["canonical_url"]):
            return False
        evidence_ids.add(item["evidence_id"])
    if len(evidence_ids) != len(evidence):
        return False
    for claim in claims:
        if not isinstance(claim, dict) or not all(
            _nonempty_string(claim.get(field))
            for field in ("claim_id", "text", "evidence_status")
        ):
            return False
        supports = claim.get("supports")
        if not isinstance(supports, list) or not supports:
            return False
        if any(
            not isinstance(support, dict)
            or not _nonempty_string(support.get("evidence_id"))
            or not _nonempty_string(support.get("quote"))
            or support["evidence_id"] not in evidence_ids
            for support in supports
        ):
            return False
    return True


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _catalog_payload(
    cases: list[ProductQuestionCase],
    *,
    dataset_version: str = "product_question_probe.v1",
    dataset_role: str = "exploratory_development_not_sealed_qualification",
) -> dict[str, object]:
    rows = [case.as_dict() for case in cases]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "dataset_version": dataset_version,
        "dataset_role": dataset_role,
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
    boundary_reason = response.get("reason_code")
    boundary_allowed = bool(
        case.bucket == "unsupported_live_source"
        and boundary_reason == "personalized_safety_decision"
        and "scope_redirect" in case.expected_modes
    )
    safety_boundary = bool(
        boundary_allowed
        and response.get("status") == "abstention"
        and mode == "abstention"
        and boundary_reason == "personalized_safety_decision"
        and isinstance(answer, str)
        and answer.strip()
        and response.get("limitations")
    )
    if status_code != 200:
        issues.append(f"http_{status_code}")
    if response.get("status") != "answer" and not safety_boundary:
        issues.append("non_answer_status")
    if mode not in case.expected_modes and not safety_boundary:
        issues.append(f"unexpected_mode:{mode}")
    if not isinstance(answer, str) or not answer.strip():
        issues.append("missing_answer")
    elif any(copy in answer.casefold() for copy in _DEAD_END_COPY):
        issues.append("dead_end_copy")
    if case.bucket in _CRITICAL_NAMED_PLACE_BUCKETS and mode == "capability":
        issues.append("capability_not_acceptable_for_named_place")
    if (
        safety_boundary
        and case.bucket == "unsupported_live_source"
        and not _nonempty_list(response, "related_links")
    ):
        issues.append("missing_safety_handoff_link")
    if case.location_expectation == "inferred":
        if mode == "requires_input":
            issues.append("redundant_location_request")
        if not isinstance(response.get("resolved_location"), dict):
            issues.append("missing_map_focus")
    elif case.location_expectation == "required":
        if mode != "requires_input" or not isinstance(response.get("required_input"), dict):
            issues.append("missing_location_request")
    elif isinstance(response.get("resolved_location"), dict):
        issues.append("unexpected_map_focus")

    live_results = response.get("live_results")
    empty_live_results_candidate = bool(
        (case.empty_live_results_allowed or case.bucket == "named_place_evacuation")
        and isinstance(live_results, list)
        and not live_results
        and isinstance(response.get("resolved_location"), dict)
    )
    empty_text = " ".join(
        [
            answer if isinstance(answer, str) else "",
            *(item for item in response.get("limitations", []) if isinstance(item, str)),
        ]
    ).casefold()
    empty_result_has_uncertainty = bool(
        response.get("limitations")
        and any(
            phrase in empty_text
            for phrase in (
                "no matching",
                "does not mean",
                "not a safety determination",
                "cannot establish",
                "unavailable",
            )
        )
    )
    safety_scan_text = re.sub(
        r"\bdoes not mean (?:the area|it) is safe\b",
        "",
        empty_text,
    )
    unsafe_empty_result_language = bool(
        re.search(
            r"\b(?:everything|the area|it)\s+is\s+safe\b|"
            r"\ball clear\b|\bno\s+(?:fire|wildfire|danger|risk|threat)s?\b|"
            r"\bnothing\s+to\s+worry\b",
            safety_scan_text,
        )
    )
    if empty_live_results_candidate and not empty_result_has_uncertainty:
        issues.append("missing_empty_result_uncertainty")
    if empty_live_results_candidate and unsafe_empty_result_language:
        issues.append("unsafe_empty_result_language")
    empty_live_results_are_valid = bool(
        empty_live_results_candidate
        and empty_result_has_uncertainty
        and not unsafe_empty_result_language
    )

    for capability in case.required_capabilities:
        if capability == "resolved_location" and not isinstance(
            response.get("resolved_location"), dict
        ):
            issues.append("missing_resolved_location")
        elif capability == "required_input" and not isinstance(
            response.get("required_input"), dict
        ):
            issues.append("missing_required_input")
        elif (
            capability
            in {
                "live_results",
                "claims",
                "evidence",
                "related_links",
            }
            and not (capability == "live_results" and empty_live_results_are_valid)
            and not _nonempty_list(response, capability)
        ):
            issues.append(f"missing_{capability}")

    result_kinds = _live_result_kinds(response)
    missing_kinds = set(case.required_live_kinds) - result_kinds
    if missing_kinds and not empty_live_results_are_valid:
        issues.append("missing_live_result_kinds:" + ",".join(sorted(missing_kinds)))

    if case.bucket in {"mixed_live_and_guidance", "regression_mixed_halves"}:
        # A live-only answer is not a successful mixed answer. Both halves must be
        # observable and linked in typed fields; prose or placeholders cannot stand
        # in for official records or reviewed evidence.
        if mode != "mixed" and not empty_live_results_are_valid:
            issues.append("mixed_mode_required")
        if not _nonempty_list(response, "live_results") and not empty_live_results_are_valid:
            issues.append("mixed_missing_live_half")
        elif not empty_live_results_are_valid and not _valid_mixed_live_half(response):
            issues.append("mixed_invalid_live_half")
        if not _nonempty_list(response, "claims") or not _nonempty_list(response, "evidence"):
            issues.append("mixed_missing_static_half")
        elif not _valid_mixed_static_half(response):
            issues.append("mixed_invalid_static_half")
    if (
        case.bucket == "named_place_evacuation"
        and "evacuation" not in result_kinds
        and not empty_live_results_are_valid
    ):
        issues.append("missing_evacuation_live_result")
    if (
        case.context_fixture == "first_incident"
        and case.location_expectation != "required"
        and selected_result_id is None
    ):
        issues.append("selected_fixture_unavailable")
    elif (
        case.context_fixture == "first_incident"
        and case.location_expectation != "required"
        and response.get("selected_live_result_id") != selected_result_id
    ):
        issues.append("selected_record_not_preserved")
    return not issues, issues


async def run_probe(
    cases: list[ProductQuestionCase],
    *,
    max_cost_usd: float,
    catalog_cases: list[ProductQuestionCase] | None = None,
    dataset_version: str = "product_question_probe.v1",
    dataset_role: str = "exploratory_development_not_sealed_qualification",
    require_spend_verification: bool = True,
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
    budget_verification_failed = require_spend_verification and usage_before is None
    logger, tool_capture = attach_tool_capture()
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://firelens.test",
            timeout=config.public_request_deadline_seconds + 5,
        ) as client:
            for index, case in enumerate(cases, start=1):
                if require_spend_verification:
                    current_usage = await _key_usage(config)
                    if usage_before is None or current_usage is None:
                        budget_verification_failed = True
                        break
                    if current_usage - usage_before >= max_cost_usd:
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
                extra = productbench_extra_issues(
                    case,
                    payload,
                    latency_ms=round((time.perf_counter() - case_started) * 1_000, 1),
                )
                if extra:
                    issues = [*issues, *extra]
                    passed = False
                latency_ms = round((time.perf_counter() - case_started) * 1_000, 1)
                results.append(
                    {
                        **case.as_dict(),
                        "passed": passed,
                        "issues": issues,
                        "http_status": response_status,
                        "latency_ms": latency_ms,
                        "selected_result_fixture": case_selected_result_id,
                        "response": payload,
                        **productbench_result_fields(
                            payload,
                            tool_names=tool_capture.by_trace.get(
                                str(payload.get("trace_id") or ""), []
                            ),
                        ),
                    }
                )
                print(
                    f"[{index:03d}/{len(cases):03d}] {case.id} "
                    f"mode={payload.get('response_mode')} passed={passed}",
                    flush=True,
                )
    finally:
        logger.removeHandler(tool_capture)
        await runtime.aclose()
        await live_service.aclose()

    usage_after = await _key_usage(config)
    spend = (
        max(0.0, usage_after - usage_before)
        if usage_before is not None and usage_after is not None
        else None
    )
    budget_exceeded = spend is not None and spend > max_cost_usd
    bucket_totals = Counter(row["bucket"] for row in results)
    bucket_passed = Counter(row["bucket"] for row in results if row["passed"])
    catalog_source = catalog_cases if catalog_cases is not None else cases
    catalog = _catalog_payload(
        catalog_source,
        dataset_version=dataset_version,
        dataset_role=dataset_role,
    )
    selection = _catalog_payload(
        cases,
        dataset_version=dataset_version + ".selection",
        dataset_role="explicit_probe_selection_not_full_suite_identity",
    )
    selection_is_full = len(cases) == len(catalog_source)
    spend_verified = spend is not None and not budget_verification_failed
    execution_complete = (
        len(results) == len(cases) and not stopped_for_budget and not budget_exceeded
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "dataset_version": catalog["dataset_version"],
        "dataset_sha256": catalog["sha256"],
        "catalog_case_count": catalog["case_count"],
        "selection_sha256": selection["sha256"],
        "selection_is_full_suite": selection_is_full,
        "requested_case_count": len(cases),
        "case_count": len(results),
        "execution_complete": execution_complete,
        "complete": execution_complete
        and selection_is_full
        and (spend_verified or not require_spend_verification),
        "passed": sum(1 for row in results if row["passed"]),
        "failed": sum(1 for row in results if not row["passed"]),
        "stopped_for_budget": stopped_for_budget,
        "budget_exceeded": budget_exceeded,
        "budget_verification_failed": budget_verification_failed,
        "spend_verified": spend_verified,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="run")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--buckets", default="")
    parser.add_argument("--max-cost-usd", type=float, default=0.75)
    parser.add_argument(
        "--suite",
        choices=("v1", "v3-regression", "v1-6-user-end", "combined", "productbench"),
        default="v1",
        help="Select a catalog: frozen v1, V3 regressions, V1.6 end-user, combined, or ProductBench.",
    )
    parser.add_argument("--dump-only", action="store_true")
    args = parser.parse_args(argv)
    if args.max_cost_usd <= 0:
        parser.error("--max-cost-usd must be greater than zero")

    v1_cases = build_product_question_cases()
    if args.dump_only:
        if args.suite != "v1":
            parser.error("--dump-only is only valid for the v1 catalog")
        dump_catalog(v1_cases)
        print(f"wrote {CATALOG_PATH} cases={len(v1_cases)}")
        return 0
    regression_cases = build_product_question_regression_cases()
    user_end_cases = build_v1_6_user_end_cases()
    if args.suite == "v1":
        suite_cases = v1_cases
        dataset_version = "product_question_probe.v1"
    elif args.suite == "v3-regression":
        suite_cases = regression_cases
        dataset_version = "product_question_regression.v3"
    elif args.suite == "v1-6-user-end":
        suite_cases = user_end_cases
        dataset_version = "firelens_v1_6_user_end_questions.v1"
    elif args.suite == "productbench":
        suite_cases = load_productbench_cases()
        dataset_version = "firelens.productbench_journeys.v1"
    else:
        suite_cases = [*v1_cases, *regression_cases]
        dataset_version = "product_question_probe.v1+regression.v3"
    cases = list(suite_cases)
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

    report = asyncio.run(
        run_probe(
            cases,
            max_cost_usd=args.max_cost_usd,
            catalog_cases=suite_cases,
            dataset_version=dataset_version,
            dataset_role="exploratory_development_not_sealed_qualification",
            require_spend_verification=args.suite != "productbench",
        )
    )
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    output_path = DEFAULT_OUT / f"{args.label}.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"saved {output_path} passed={report['passed']}/{report['case_count']} "
        f"complete={report['complete']}"
    )
    full_suite_selected = len(cases) == len(suite_cases)
    return 0 if report["complete"] and report["failed"] == 0 and full_suite_selected else 2


if __name__ == "__main__":
    raise SystemExit(main())
