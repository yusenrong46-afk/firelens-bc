"""Run the natural-language mutation set against a live FireLens deployment.

    python scripts/run_nl_mutation_set.py --base http://127.0.0.1:8000 \
        --output evals/fable51_product_rescue/nl_mutation_local.json

Expectations live in ``data/evaluation/nl_mutation_set.v1.yaml`` and describe
product behaviour (mode, boundary wording, handoff links, source proof), not
data values. Exit status is non-zero when any case fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "data/evaluation/nl_mutation_set.v1.yaml"


def _ask(
    base: str, case: dict[str, Any], timeout: float
) -> tuple[dict[str, Any] | None, float, str]:
    body = {"question": case["question"], "history": case.get("history", []), "context": {}}
    request = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/ask",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return None, time.perf_counter() - started, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, time.perf_counter() - started, f"transport: {exc}"
    return payload, time.perf_counter() - started, ""


def _matches(patterns: list[str], text: str) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, re.I | re.M)]


def evaluate(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    answer = response.get("answer") or ""
    mode = response.get("response_mode")
    if mode not in case["modes"]:
        failures.append(f"mode {mode!r} ({response.get('reason_code')}) not in {case['modes']}")
    if case.get("answer_any") and not _matches(case["answer_any"], answer):
        failures.append(f"answer matched none of {case['answer_any']}")
    hit = _matches(case.get("answer_none", []), answer)
    if hit:
        failures.append(f"answer matched forbidden {hit}")
    if case.get("sections_any"):
        kinds = {section.get("kind") for section in response.get("answer_sections") or []}
        if not kinds & set(case["sections_any"]):
            failures.append(f"sections {sorted(kinds)} lack {case['sections_any']}")
    if case.get("links_any"):
        titles = " | ".join(
            link.get("title", "") for link in response.get("related_links") or []
        )
        if not _matches(case["links_any"], titles):
            failures.append(f"links [{titles}] lack {case['links_any']}")
    live = len(response.get("live_results") or [])
    if case.get("live_results") == "some" and live == 0:
        failures.append("expected live records")
    if case.get("live_results") == "none" and live:
        failures.append(f"expected no live records, got {live}")
    if case.get("evidence") == "some" and not response.get("evidence"):
        failures.append("expected source evidence")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", required=True, help="FireLens origin, e.g. http://127.0.0.1:8000"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between requests")
    parser.add_argument("--only", default="", help="comma-separated case ids")
    args = parser.parse_args()

    cases = yaml.safe_load(args.cases.read_text())["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [case for case in cases if case["id"] in wanted]

    results: list[dict[str, Any]] = []
    for case in cases:
        response, seconds, error = _ask(args.base, case, args.timeout)
        if response is None:
            failures = [error]
        else:
            failures = evaluate(case, response)
        results.append(
            {
                "id": case["id"],
                "flow": case["flow"],
                "question": case["question"],
                "passed": not failures,
                "failures": failures,
                "seconds": round(seconds, 2),
                "response_mode": response.get("response_mode") if response else None,
                "reason_code": response.get("reason_code") if response else None,
                "live_results": len(response.get("live_results") or []) if response else 0,
                "evidence": len(response.get("evidence") or []) if response else 0,
                "answer": (response.get("answer") or "")[:400] if response else "",
            }
        )
        mark = "PASS" if not failures else "FAIL"
        print(f"{mark} {case['id']} {seconds:5.1f}s {case['question']}")
        for failure in failures:
            print(f"       {failure}")
        if args.pause:
            time.sleep(args.pause)

    passed = sum(1 for item in results if item["passed"])
    by_flow: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_flow.setdefault(item["flow"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(item["passed"])
    summary = {
        "base": args.base,
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "p50_seconds": sorted(item["seconds"] for item in results)[len(results) // 2]
        if results
        else None,
        "max_seconds": max((item["seconds"] for item in results), default=None),
        "by_flow": by_flow,
        "results": results,
    }
    print(
        f"\n{passed}/{len(results)} passed; by flow: "
        + ", ".join(
            f"{flow} {counts['passed']}/{counts['total']}"
            for flow, counts in sorted(by_flow.items())
        )
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
