from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from firelens.agent.budget import RequestExecutionPolicy
from firelens.config import FireLensConfig
from firelens.evaluation.pre_release_performance import build_pre_release_report
from firelens.evaluation.round2_workload import load_performance_workload, workload_identity

ROOT = Path(__file__).resolve().parents[1]

ROOT = Path(__file__).resolve().parents[1]


def test_round2_workload_is_a_declared_representative_mix() -> None:
    workload = load_performance_workload(ROOT)
    identity = workload_identity(ROOT)

    assert workload.not_fleet_average is True
    assert workload.label == "representative_workload_average"
    assert workload.case_count == 10
    assert workload.warmup_per_route == 10
    assert workload.measured_per_route == 30
    assert abs(sum(route.weight for route in workload.routes) - 1.0) < 1e-9
    assert {route.id for route in workload.routes} >= {
        "pure_static_guidance",
        "ready_live",
        "mixed_live_and_static",
        "capability",
        "prohibited_personalized_safety",
        "missing_location",
        "unsupported_tangent",
        "unresolved_tool_loop",
        "output_rail_rewrite",
        "deterministic_fallback",
    }
    assert len(identity["sha256"]) == 64


def test_adaptive_retrieval_stays_disabled_by_default() -> None:
    assert FireLensConfig.from_env(ROOT).retrieval_strategy == "baseline"


def test_request_policy_exposes_content_free_call_counters() -> None:
    policy = RequestExecutionPolicy(route="pure_static_accepted")
    policy.consume_grounded_generation()
    counters = policy.as_counters()
    assert counters["grounded_generations"] == 1
    assert counters["outer_chat_turns"] == 0
    assert "question" not in counters
    assert "answer" not in counters
    for key in (
        "embedding_calls",
        "rerank_calls",
        "retrieval_cycles",
        "rewrites",
        "planner_calls",
    ):
        assert key in counters


def test_pre_release_report_requires_acceptance_for_route_regression() -> None:
    current = {
        "representative_average_generate_calls": 0.5,
        "pure_static_generate_calls": 0.0,
        "routes": {
            "mixed": {
                "p50_ms": 20.0,
                "p95_ms": 25.0,
                "mean_generate_calls": 1.0,
                "failures": 0,
            }
        },
    }
    comparison = {
        "compare": {"route_p95": {"mixed": {"regressed_over_10pct": True}}},
        "v1_5_status": "EXECUTED",
    }

    report = build_pre_release_report(
        root=ROOT,
        current=current,
        comparison=comparison,
        warmup=10,
        measured=100,
    )

    assert report["h8_review"] == {
        "regressed_routes_over_10pct": ["mixed"],
        "requires_accepted_evidence": True,
        "status": "NEEDS_HUMAN_TRADEOFF_ACCEPTANCE",
    }


def test_retrieval_dry_run_is_blocked_and_does_not_inspect_sealed_labels(
    tmp_path: Path,
) -> None:
    output = tmp_path / "retrieval.json"
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "scripts/v1_6_round2_retrieval.py"),
            "--dry-run",
            "--output",
            str(output),
        ],
        cwd=ROOT,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sealed_labels_inspected"] is False
    assert payload["provider_metrics"] == "BLOCKED"
    assert payload["default_strategy"] == "baseline"
    assert payload["adaptive_default"] is False
    assert payload["development_case_count"] == 50
    assert "holdout" not in json.dumps(payload)
