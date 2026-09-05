"""Zero-cost sample evidence and no-comparison false-green controls."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from firelens.evaluation.pre_release_performance import build_pre_release_report
from firelens.evaluation.round2_workload import load_performance_workload

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "rows", [None, {}, {"other": {}}, {"route": {"regressed_over_10pct": False}}]
)
def test_missing_measurement_is_not_no_regression(rows: dict | None) -> None:
    current = {
        "representative_average_generate_calls": 0,
        "routes": {
            "route": {"p50_ms": 1, "p95_ms": 2, "mean_generate_calls": 0, "failures": 0}
        },
    }
    with patch("firelens.evaluation.pre_release_performance.clean_checkout_commit"):
        report = build_pre_release_report(
            root=ROOT,
            current=current,
            comparison={
                "v1_5_status": "SKIPPED",
                "compare": None if rows is None else {"route_p95": rows},
            },
            warmup=5,
            measured=30,
        )
    assert report["h8_review"]["status"] == "NOT_COMPARABLE"


def test_valid_matched_comparison_control() -> None:
    current = {
        "representative_average_generate_calls": 0,
        "routes": {
            "route": {"p50_ms": 1, "p95_ms": 2, "mean_generate_calls": 0, "failures": 0}
        },
    }
    compare = {
        "route_p95": {
            "route": {"v1_5_p95_ms": 2, "round2_p95_ms": 2, "regressed_over_10pct": False}
        }
    }
    with patch("firelens.evaluation.pre_release_performance.clean_checkout_commit"):
        report = build_pre_release_report(
            root=ROOT,
            current=current,
            comparison={"v1_5_status": "EXECUTED", "compare": compare},
            warmup=5,
            measured=30,
        )
    assert report["h8_review"]["status"] == "MEASURED_NO_ROUTE_REGRESSION"


def test_loopback_workload_retains_validated_samples(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "astra_perf_runner", ROOT / "scripts/v1_6_round2_performance.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    workload = load_performance_workload(ROOT)
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps([route.model_dump() for route in workload.routes]))
    repetitions = []
    for _ in range(3):
        result = asyncio.run(
            module._measure(
                argparse.Namespace(root=ROOT, routes_json=routes, warmup=5, measured=30)
            )
        )
        assert set(result["routes"]) == {route.id for route in workload.routes}
        for row in result["routes"].values():
            assert row["failures"] == 0
            assert len(row["samples"]) == 30
            assert all(
                sample["http_status"] == 200 and sample["contract_valid"]
                for sample in row["samples"]
            )
            assert row["p95_ms"] == module._percentile(
                [sample["latency_ms"] for sample in row["samples"]], 0.95
            )
        repetitions.append(result)
    output = Path(os.environ.get("FIRELENS_LOCAL_ARTIFACTS", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "loopback-samples.json").write_text(
        json.dumps(
            {
                "evidence_class": "local_fake_loopback",
                "external_calls": 0,
                "repetitions": repetitions,
            },
            indent=2,
        )
    )
