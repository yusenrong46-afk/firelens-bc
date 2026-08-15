#!/usr/bin/env python3
"""Zero-cost HTTP gates for bound candidate identity, ZDR, and live fail-closed states."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from firelens.deployment_gates import qualify_deployment_gates

ROOT = Path(__file__).resolve().parents[1]


async def _run(args: argparse.Namespace) -> int:
    parsed = urlparse(args.base_url)
    if parsed.scheme != "https" and not (
        args.allow_http
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        print("deployment gates require HTTPS (or --allow-http for localhost)")
        return 2
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        report = await qualify_deployment_gates(
            client,
            base_url=args.base_url,
            candidate_path=args.candidate,
            expect_production=args.expect_production,
            include_ask_probes=args.include_ask_probes,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("qualified", "checks")}, indent=2))
    return 0 if report["qualified"] else 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=ROOT / "config/runtime_candidate.v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/qualification/v1_5_v3_deployment_gates.json",
    )
    parser.add_argument("--expect-production", action="store_true")
    parser.add_argument(
        "--include-ask-probes",
        action="store_true",
        help="POST one safety-boundary Ask probe; incurs provider cost on a live origin",
    )
    parser.add_argument("--allow-http", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
