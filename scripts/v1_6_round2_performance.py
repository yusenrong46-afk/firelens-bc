#!/usr/bin/env python3
"""Matched representative-workload Ask measurement. Not a fleet average."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
V15 = "3de745a22ad0801e19563f90ac64f18609ecae03"
WORKLOAD = ROOT / "data/evaluation/v1_6_round2_performance_workload.yaml"


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(fraction * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _snapshot(provider: Any) -> dict[str, int]:
    return {
        "plan_calls": int(getattr(provider, "plan_calls", 0)),
        "embed_calls": int(getattr(provider, "embed_calls", 0)),
        "rerank_calls": int(getattr(provider, "rerank_calls", 0)),
        "generate_calls": int(getattr(provider, "generate_calls", 0)),
    }


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


async def _measure(args: argparse.Namespace) -> dict[str, Any]:
    from firelens.api import create_app
    from firelens.config import FireLensConfig
    from firelens.evaluation.hard_probe_cli import OfflineLiveDataService
    from firelens.providers.fake import FakeProvider
    from firelens.runtime import load_runtime

    routes = json.loads(Path(args.routes_json).read_text(encoding="utf-8"))
    root = Path(args.root)
    config = FireLensConfig.from_env(root).model_copy(update={"anonymous_rate_limit": 10_000})
    dimensions = int(json.loads(config.vector_manifest_path.read_text())["dimensions"])
    provider = FakeProvider(dimensions=dimensions)
    live = OfflineLiveDataService()
    runtime = load_runtime(config, provider=provider)
    if runtime.service is None:
        raise RuntimeError("runtime unavailable: " + "; ".join(runtime.problems))
    app = create_app(config, runtime=runtime, live_service=live)
    route_rows: dict[str, dict[str, Any]] = {}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://firelens.local",
            timeout=90,
        ) as client:
            for route in routes:
                for _ in range(args.warmup):
                    await client.post(
                        "/api/v1/ask", json={"question": route["question"], "history": []}
                    )
                latencies: list[float] = []
                generate: list[int] = []
                embed: list[int] = []
                rerank: list[int] = []
                failures = 0
                modes: dict[str, int] = {}
                for _ in range(args.measured):
                    before = _snapshot(provider)
                    started = time.perf_counter()
                    response = await client.post(
                        "/api/v1/ask", json={"question": route["question"], "history": []}
                    )
                    latency = (time.perf_counter() - started) * 1_000
                    after = _snapshot(provider)
                    delta = _delta(before, after)
                    latencies.append(latency)
                    generate.append(delta["generate_calls"])
                    embed.append(delta["embed_calls"])
                    rerank.append(delta["rerank_calls"])
                    if response.status_code >= 500:
                        failures += 1
                    mode = str((response.json() or {}).get("response_mode") or "unknown")
                    modes[mode] = modes.get(mode, 0) + 1
                route_rows[route["id"]] = {
                    "weight": route["weight"],
                    "measured": args.measured,
                    "p50_ms": _percentile(latencies, 0.5),
                    "p95_ms": _percentile(latencies, 0.95),
                    "max_ms": max(latencies) if latencies else 0.0,
                    "mean_generate_calls": sum(generate) / len(generate) if generate else 0.0,
                    "mean_embed_calls": sum(embed) / len(embed) if embed else 0.0,
                    "mean_rerank_calls": sum(rerank) / len(rerank) if rerank else 0.0,
                    "failures": failures,
                    "modes": modes,
                }
    finally:
        await runtime.aclose()
        await live.aclose()
    weighted_generate = sum(
        row["mean_generate_calls"] * row["weight"] for row in route_rows.values()
    )
    return {
        "schema_version": "firelens_v1_6_round2_performance.v1",
        "label": "representative_workload_average",
        "not_fleet_average": True,
        "root": str(root),
        "warmup_per_route": args.warmup,
        "measured_per_route": args.measured,
        "routes": route_rows,
        "representative_average_generate_calls": weighted_generate,
        "pure_static_generate_calls": route_rows.get("pure_static_guidance", {}).get(
            "mean_generate_calls"
        ),
    }


def _routes_from_workload() -> list[dict[str, Any]]:
    payload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    return [
        {"id": row["id"], "weight": row["weight"], "question": row["question"]}
        for row in payload["routes"]
    ]


def _run_tree(
    root: Path, label: str, warmup: int, measured: int, output: Path
) -> dict[str, Any]:
    routes_path = output.parent / f"{label}_routes.json"
    routes_path.write_text(json.dumps(_routes_from_workload()), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--measure-only",
        "--root",
        str(root),
        "--routes-json",
        str(routes_path),
        "--warmup",
        str(warmup),
        "--measured",
        str(measured),
        "--output",
        str(output),
        "--label",
        label,
    ]
    completed = subprocess.run(command, cwd=root, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} measurement failed with status {completed.returncode}")
    return json.loads(output.read_text(encoding="utf-8"))


def _ensure_v15(worktree: Path) -> Path:
    if (worktree / "src/firelens").is_dir():
        return worktree
    worktree.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), V15],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git worktree add failed")
    return worktree


def _compare(v15: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    v15_gen = float(v15["representative_average_generate_calls"])
    cur_gen = float(current["representative_average_generate_calls"])
    reduction = None if v15_gen == 0 else (v15_gen - cur_gen) / v15_gen
    p95: dict[str, Any] = {}
    for route_id, row in current["routes"].items():
        baseline = v15["routes"][route_id]["p95_ms"]
        candidate = row["p95_ms"]
        delta = None if baseline == 0 else (candidate - baseline) / baseline
        p95[route_id] = {
            "v1_5_p95_ms": baseline,
            "round2_p95_ms": candidate,
            "relative_change": delta,
            "regressed_over_10pct": bool(delta is not None and delta > 0.10),
        }
    return {
        "schema_version": "firelens_v1_6_round2_performance_compare.v1",
        "label": "representative_workload_average",
        "not_fleet_average": True,
        "v1_5_average_generate_calls": v15_gen,
        "round2_average_generate_calls": cur_gen,
        "generative_call_reduction": reduction,
        "meets_20pct_generate_reduction": bool(reduction is not None and reduction >= 0.20),
        "pure_static_round2_generate_calls": current.get("pure_static_generate_calls"),
        "route_p95": p95,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure-only", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--routes-json", type=Path)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--measured", type=int, default=30)
    parser.add_argument("--label", default="current")
    parser.add_argument("--skip-v15", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/benchmark/v1_6_round2/performance_current.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=ROOT / "output/benchmark/v1_6_round2/performance_report.json",
        help="Comparison report path; historical docs reports are never overwritten by default.",
    )
    args = parser.parse_args()
    if args.measure_only:
        if args.routes_json is None:
            raise SystemExit("--routes-json is required with --measure-only")
        payload = asyncio.run(_measure(args))
        payload["label_id"] = args.label
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "label": args.label,
                    "generate": payload["representative_average_generate_calls"],
                }
            )
        )
        return 0
    from firelens.evaluation.pre_release_performance import build_pre_release_report

    out_dir = ROOT / "output/benchmark/v1_6_round2"
    out_dir.mkdir(parents=True, exist_ok=True)
    current = _run_tree(
        ROOT, "current", args.warmup, args.measured, out_dir / "performance_current.json"
    )
    comparison = {"current": current, "v1_5": None, "compare": None, "v1_5_status": "SKIPPED"}
    if not args.skip_v15:
        worktree = _ensure_v15(ROOT / "output/worktrees/v1_5_baseline")
        v15 = _run_tree(
            worktree, "v1_5", args.warmup, args.measured, out_dir / "performance_v1_5.json"
        )
        comparison = {
            "current": current,
            "v1_5": v15,
            "compare": _compare(v15, current),
            "v1_5_status": "EXECUTED",
        }
    slim = build_pre_release_report(
        root=ROOT,
        current=current,
        comparison=comparison,
        warmup=args.warmup,
        measured=args.measured,
    )
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(slim, indent=2, sort_keys=True) + "\n")
    print(json.dumps(slim, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
