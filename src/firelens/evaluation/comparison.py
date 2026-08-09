"""Before/after benchmark metric comparison and verdict rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from firelens.evaluation.snapshot import (
    _validated_metric_value,
    _validated_snapshot_metrics,
)
from firelens.evaluation.spec_models import BenchmarkSpec, MetricSpec
from firelens.evaluation.ux import (
    _execution_environment_comparability,
    _ux_distribution_comparability,
)


def _target_passed(metric: MetricSpec, value: Any) -> bool | None:
    if metric.gate_operator is None:
        return None
    if value is None:
        return False
    value = _validated_metric_value(metric, value, label="after")
    if metric.gate_operator == "eq":
        return type(value) is type(metric.gate_value) and value == metric.gate_value
    target = float(metric.gate_value)
    if metric.gate_operator == "gte":
        return float(value) >= target
    return float(value) <= target


def _verdict(metric: MetricSpec, before: Any, after: Any) -> tuple[str, float | None]:
    if metric.comparison_mode == "after_only":
        if before is not None:
            raise ValueError(f"after-only metric {metric.key} must not have a before value")
        if after is not None:
            _validated_metric_value(metric, after, label="after")
        return "after_only", None
    if metric.comparison_mode == "prerequisite":
        if before is not None:
            _validated_metric_value(metric, before, label="before")
        if after is not None:
            _validated_metric_value(metric, after, label="after")
        return "prerequisite", None
    if before is None or after is None:
        return "not_measured", None
    before = _validated_metric_value(metric, before, label="before")
    after = _validated_metric_value(metric, after, label="after")
    if isinstance(before, bool) and isinstance(after, bool):
        if before == after:
            return "within_tolerance", 0.0
        directed = (
            float(after) - float(before)
            if metric.direction == "higher_is_better"
            else float(before) - float(after)
        )
        return ("improved" if directed > 0 else "regressed"), float(after) - float(before)
    delta = float(after) - float(before)
    tolerance = metric.tolerance
    if tolerance is None:
        raise ValueError(f"paired numeric metric {metric.key} has no tolerance")
    limit = max(tolerance.absolute, abs(float(before)) * tolerance.relative)
    directed = delta if metric.direction == "higher_is_better" else -delta
    if metric.comparison_requirement == "must_improve":
        if directed > 0 and directed >= limit:
            return "improved", delta
        if directed < -limit:
            return "regressed", delta
        return "within_tolerance", delta
    if directed > limit:
        return "improved", delta
    if directed < -limit:
        return "regressed", delta
    return "within_tolerance", delta


def _comparison_requirement_passed(metric: MetricSpec, verdict: str) -> bool | None:
    if metric.comparison_mode != "paired":
        return None
    if verdict == "not_measured":
        return False
    if metric.comparison_requirement == "must_improve":
        return verdict == "improved"
    if metric.comparison_requirement == "no_regression":
        return verdict in {"improved", "within_tolerance"}
    return True


def compare_snapshots(
    before: dict[str, Any], after: dict[str, Any], spec: BenchmarkSpec
) -> dict[str, Any]:
    if (
        before.get("benchmark_id") != spec.benchmark_id
        or after.get("benchmark_id") != spec.benchmark_id
    ):
        raise ValueError("snapshot benchmark_id does not match the specification")
    if before.get("label") != "before" or after.get("label") != "after":
        raise ValueError("comparison requires explicit before and after snapshot labels")
    before_identity = before.get("identity") or {}
    after_identity = after.get("identity") or {}
    if (
        before.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2"
        or after.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2"
    ):
        raise ValueError("before and after snapshots must use snapshot schema v2")
    if before_identity.get("spec_sha256") != after_identity.get("spec_sha256"):
        raise ValueError("before and after snapshots use different benchmark specifications")
    if before_identity.get("identity_input_sha256") != after_identity.get(
        "identity_input_sha256"
    ):
        raise ValueError("before and after snapshots use different frozen evaluation inputs")
    if before_identity.get("harness_input_sha256") != after_identity.get(
        "harness_input_sha256"
    ):
        raise ValueError("before and after snapshots use different benchmark harnesses")

    environment_comparability = _execution_environment_comparability(
        before_identity, after_identity
    )
    ux_comparability = _ux_distribution_comparability(
        before.get("ux") or {}, after.get("ux") or {}
    )
    comparability_failures = [
        name
        for name, result in (
            ("execution_environment", environment_comparability),
            ("ux_sampling", ux_comparability),
        )
        if not result["passed"]
    ]

    before_metrics = _validated_snapshot_metrics(before, spec, label="before")
    after_metrics = _validated_snapshot_metrics(after, spec, label="after")
    rows = []
    for metric in spec.comparison_metrics:
        before_value = before_metrics.get(metric.key)
        after_value = after_metrics.get(metric.key)
        verdict, delta = _verdict(metric, before_value, after_value)
        requirement_passed = _comparison_requirement_passed(metric, verdict)
        rows.append(
            {
                "key": metric.key,
                "track": metric.track,
                "direction": metric.direction,
                "value_type": metric.value_type,
                "comparison_mode": metric.comparison_mode,
                "comparison_requirement": metric.comparison_requirement,
                "tolerance": metric.tolerance.model_dump() if metric.tolerance else None,
                "before": before_value,
                "after": after_value,
                "delta": delta,
                "verdict": verdict,
                "comparison_requirement_passed": requirement_passed,
                "required_after": metric.required_after,
                "gate_operator": metric.gate_operator,
                "gate_value": metric.gate_value,
                "after_gate_passed": _target_passed(metric, after_value),
            }
        )
    required = [row for row in rows if row["required_after"]]
    missing_before = [
        row["key"]
        for row in rows
        if row["comparison_mode"] == "paired" and row["before"] is None
    ]
    missing = [row["key"] for row in required if row["after"] is None]
    failed = [row["key"] for row in required if row["after_gate_passed"] is False]
    regressions = [row["key"] for row in rows if row["verdict"] == "regressed"]
    insufficient_improvement = [
        row["key"]
        for row in rows
        if row["comparison_requirement"] == "must_improve"
        and row["comparison_requirement_passed"] is False
    ]
    return {
        "schema_version": "firelens_upgrade_benchmark_comparison.v2",
        "benchmark_id": spec.benchmark_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "before": {
            "label": before.get("label"),
            "commit": before_identity.get("commit"),
        },
        "after": {
            "label": after.get("label"),
            "commit": after_identity.get("commit"),
        },
        "comparability": {
            "execution_environment": environment_comparability,
            "ux_sampling": ux_comparability,
        },
        "metrics": rows,
        "summary": {
            "improved": sum(row["verdict"] == "improved" for row in rows),
            "regressed": len(regressions),
            "within_tolerance": sum(row["verdict"] == "within_tolerance" for row in rows),
            "not_measured": sum(row["verdict"] == "not_measured" for row in rows),
            "missing_required_before": missing_before,
            "missing_required_after": missing,
            "failed_after_gates": failed,
            "regressions": regressions,
            "insufficient_improvement": insufficient_improvement,
            "comparability_failures": comparability_failures,
            "benchmark_gate_passed": not any(
                (
                    missing_before,
                    missing,
                    failed,
                    regressions,
                    insufficient_improvement,
                    comparability_failures,
                )
            ),
        },
    }


def _markdown(comparison: dict[str, Any]) -> str:
    ancestry = comparison.get("before_snapshot_ancestry") or {}
    lines = [
        "# FireLens V1.5-2 before/after benchmark",
        "",
        f"Before: `{comparison['before']['label']}` at `{comparison['before']['commit']}`  ",
        f"After: `{comparison['after']['label']}` at `{comparison['after']['commit']}`",
        f"Before-seal commit: `{ancestry.get('seal_introducing_commit', 'not verified')}`",
        "",
        "| Metric | Track | Before | After | Delta | Verdict | Gate |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in comparison["metrics"]:
        gate = (
            "pass"
            if row["after_gate_passed"] is True
            else "fail"
            if row["after_gate_passed"] is False
            else "comparison only"
        )
        lines.append(
            "| {key} | {track} | {before} | {after} | {delta} | {verdict} | {gate} |".format(
                key=row["key"],
                track=row["track"],
                before=row["before"] if row["before"] is not None else "not measured",
                after=row["after"] if row["after"] is not None else "not measured",
                delta=row["delta"] if row["delta"] is not None else "—",
                verdict=row["verdict"],
                gate=gate,
            )
        )
    summary = comparison["summary"]
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Improved: {summary['improved']}",
            f"- Regressed: {summary['regressed']}",
            f"- Within tolerance: {summary['within_tolerance']}",
            f"- Not measured: {summary['not_measured']}",
            f"- Benchmark gate passed: {summary['benchmark_gate_passed']}",
            f"- Missing required before metrics: {', '.join(summary['missing_required_before']) or 'none'}",
            f"- Missing required after metrics: {', '.join(summary['missing_required_after']) or 'none'}",
            f"- Failed after gates: {', '.join(summary['failed_after_gates']) or 'none'}",
            f"- Regressions: {', '.join(summary['regressions']) or 'none'}",
            f"- Insufficient improvements: {', '.join(summary['insufficient_improvement']) or 'none'}",
            f"- Comparability failures: {', '.join(summary['comparability_failures']) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines)
