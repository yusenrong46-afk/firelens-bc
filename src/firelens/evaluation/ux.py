"""UX round validation, statistics, and before/after comparability."""

from __future__ import annotations

import math
import random
import re
import statistics
from collections import Counter
from typing import Any

from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_full_git_sha as _require_full_git_sha,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    require_timestamp as _require_timestamp,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)
from firelens.evaluation.common import (
    strict_number as _strict_number,
)
from firelens.evaluation.spec_models import BenchmarkSpec

UX_DISTRIBUTION_MAX_SHARE_DELTA = 0.15
UX_REQUIRED_COHORTS = frozenset({"novice_bc_resident", "wildfire_aware"})
UX_REQUIRED_DEVICE_CLASSES = frozenset({"mobile", "desktop"})
UX_REQUIRED_ACCESS_METHODS = frozenset({"keyboard", "screen_reader"})
UX_ALLOWED_ACCESS_METHODS = frozenset(
    {"keyboard", "pointer", "screen_reader", "switch_control", "touch", "voice_control"}
)
UX_MINIMUM_CORE_COHORT_SIZE = 4
UX_MINIMUM_DEVICE_CLASS_SIZE = 3
EXECUTION_ENVIRONMENT_FIELDS = (
    "os",
    "os_release",
    "architecture",
    "cpu_model",
    "logical_cpu_count",
    "python_implementation",
    "python_version",
    "node_version",
    "npm_version",
    "playwright_version",
    "chromium_version",
)


def _named_frontend_reviewer(value: Any, *, context: str) -> str:
    name = _require_nonempty_string(value, context=context)
    placeholders = {
        "accessibility specialist",
        "adjudicator",
        "owner",
        "moderator",
        "release adjudicator",
        "reviewer",
        "tbd",
        "unknown",
        "ux researcher",
        "wildfire product safety reviewer",
    }
    if (
        len(name) < 3
        or name.casefold() in placeholders
        or name.casefold().startswith(("gpt-", "claude-", "gemini-", "model-"))
        or not any(character.isalpha() for character in name)
    ):
        raise ValueError(f"{context} must identify a named human, not a placeholder or model")
    return name


def _wilson_interval(successes: int, total: int) -> dict[str, float]:
    if total <= 0:
        raise ValueError("Wilson interval requires at least one observation")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return {"lower": max(0.0, center - radius), "upper": min(1.0, center + radius)}


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires observations")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _bootstrap_ux_round(
    participant_outcomes: list[dict[str, Any]], *, seed: int, resamples: int = 2_000
) -> dict[str, Any]:
    randomizer = random.Random(seed)
    completion_samples: list[float] = []
    near_me_samples: list[float] = []
    count = len(participant_outcomes)
    for _ in range(resamples):
        sample = [participant_outcomes[randomizer.randrange(count)] for _ in range(count)]
        completion_samples.append(sum(float(row["completion_rate"]) for row in sample) / count)
        near_me_samples.append(
            float(statistics.median(float(row["near_me_seconds"]) for row in sample))
        )
    return {
        "seed": seed,
        "resamples": resamples,
        "completion_rate_95ci": {
            "lower": _percentile(completion_samples, 0.025),
            "upper": _percentile(completion_samples, 0.975),
        },
        "near_me_median_seconds_95ci": {
            "lower": _percentile(near_me_samples, 0.025),
            "upper": _percentile(near_me_samples, 0.975),
        },
    }


def _ux(report: dict[str, Any] | None, spec: BenchmarkSpec) -> dict[str, Any]:
    if report is None:
        return {"status": "not_run", "task_count": len(spec.ux_tasks)}
    _require_exact_keys(
        report,
        {
            "schema_version",
            "label",
            "protocol_id",
            "commit",
            "deployment_id",
            "moderator",
            "observed_at",
            "participant_count",
            "recruitment_constraint",
            "participants",
            "attempts",
            "task_reference",
        },
        context="UX report",
    )
    if report.get("schema_version") != "firelens_ux_benchmark_report.v3":
        raise ValueError("UX report uses an unsupported schema_version")
    if report.get("label") not in {"before", "after"}:
        raise ValueError("UX report label must be before or after")
    if report.get("protocol_id") != spec.benchmark_id:
        raise ValueError("UX report protocol does not match the frozen benchmark")
    commit = _require_full_git_sha(report.get("commit"), context="UX report commit")
    _require_nonempty_string(report.get("deployment_id"), context="UX deployment ID")
    _named_frontend_reviewer(report.get("moderator"), context="UX moderator")
    _require_timestamp(report.get("observed_at"), context="UX observed_at")
    _require_nonempty_string(
        report.get("recruitment_constraint"), context="UX recruitment constraint"
    )
    if report.get("task_reference") != [task.model_dump() for task in spec.ux_tasks]:
        raise ValueError("UX report task reference does not match the frozen task wording")

    participants = report.get("participants")
    attempts = report.get("attempts")
    if not isinstance(participants, list) or not isinstance(attempts, list):
        raise ValueError("UX report participants and attempts must be lists")
    participant_count = _strict_int(report, "participant_count", "UX report", minimum=12)
    if participant_count != len(participants):
        raise ValueError("UX report participant_count does not match participant rows")

    participant_ids: set[str] = set()
    participant_cohorts: dict[str, str] = {}
    participant_device_classes: dict[str, str] = {}
    participant_access_methods: dict[str, tuple[str, ...]] = {}
    cohort_counts: Counter[str] = Counter()
    device_class_counts: Counter[str] = Counter()
    access_method_counts: Counter[str] = Counter()
    for row in participants:
        if not isinstance(row, dict):
            raise ValueError("UX participant row must be an object")
        _require_exact_keys(
            row,
            {"participant_id", "cohort", "device_class", "access_methods"},
            context="UX participant row",
        )
        participant_id = str(row.get("participant_id") or "").strip()
        cohort = str(row.get("cohort") or "").strip()
        device_class = str(row.get("device_class") or "").strip()
        access_methods = row.get("access_methods")
        if not all((participant_id, cohort, device_class)):
            raise ValueError("UX participant rows require identity, cohort, and device")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", participant_id):
            raise ValueError("UX participant IDs must be canonical pseudonymous identifiers")
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", cohort):
            raise ValueError("UX participant cohorts must be canonical identifiers")
        if device_class not in UX_REQUIRED_DEVICE_CLASSES:
            raise ValueError("UX participant device class must be mobile or desktop")
        if (
            not isinstance(access_methods, list)
            or not access_methods
            or len(access_methods) != len(set(access_methods))
            or any(method not in UX_ALLOWED_ACCESS_METHODS for method in access_methods)
        ):
            raise ValueError("UX participant access methods are invalid")
        if participant_id in participant_ids:
            raise ValueError("UX participant IDs must be unique")
        participant_ids.add(participant_id)
        participant_cohorts[participant_id] = cohort
        participant_device_classes[participant_id] = device_class
        participant_access_methods[participant_id] = tuple(access_methods)
        cohort_counts[cohort] += 1
        device_class_counts[device_class] += 1
        access_method_counts.update(access_methods)
    if any(
        cohort_counts[cohort] < UX_MINIMUM_CORE_COHORT_SIZE for cohort in UX_REQUIRED_COHORTS
    ):
        raise ValueError("UX report requires at least four participants in each core cohort")
    if any(
        device_class_counts[device] < UX_MINIMUM_DEVICE_CLASS_SIZE
        for device in UX_REQUIRED_DEVICE_CLASSES
    ):
        raise ValueError(
            "UX report requires at least three mobile and three desktop participants"
        )
    if any(access_method_counts[method] < 1 for method in UX_REQUIRED_ACCESS_METHODS):
        raise ValueError("UX report requires keyboard and screen-reader coverage")

    task_by_id = {task.id: task for task in spec.ux_tasks}
    expected = set(task_by_id)
    observed_pairs: set[tuple[str, str]] = set()
    task_attempts: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in expected}
    validated_attempts: list[dict[str, Any]] = []
    for row in attempts:
        if not isinstance(row, dict):
            raise ValueError("UX attempt row must be an object")
        participant_id = str(row.get("participant_id") or "").strip()
        task_id = str(row.get("task_id") or "").strip()
        if participant_id not in participant_ids or task_id not in expected:
            raise ValueError("UX attempt references an unknown participant or task")
        context = f"UX attempt {participant_id}/{task_id}"
        _require_exact_keys(
            row,
            {
                "participant_id",
                "task_id",
                "criterion_results",
                "critical_error_codes",
                "critical_error_notes",
                "duration_seconds",
                "seq_score",
                "confidence",
                "observed_outcome",
            },
            context=context,
        )
        pair = (participant_id, task_id)
        if pair in observed_pairs:
            raise ValueError("UX report contains a duplicate participant/task attempt")
        observed_pairs.add(pair)

        task = task_by_id[task_id]
        criterion_results = row.get("criterion_results")
        expected_criteria = {criterion.id for criterion in task.completion_criteria}
        if not isinstance(criterion_results, dict):
            raise ValueError(f"{context} criterion results must be an object")
        _require_exact_keys(criterion_results, expected_criteria, context=f"{context} criteria")
        if any(type(value) is not bool for value in criterion_results.values()):
            raise ValueError(f"{context} criterion results must be strict booleans")

        critical_error_codes = row.get("critical_error_codes")
        known_error_codes = {error.code for error in task.critical_errors}
        if (
            not isinstance(critical_error_codes, list)
            or len(critical_error_codes) != len(set(critical_error_codes))
            or any(code not in known_error_codes for code in critical_error_codes)
        ):
            raise ValueError(f"{context} critical-error codes are invalid")
        critical_error_notes = row.get("critical_error_notes")
        if not isinstance(critical_error_notes, dict):
            raise ValueError(f"{context} critical-error notes must be an object")
        _require_exact_keys(
            critical_error_notes,
            set(critical_error_codes),
            context=f"{context} critical-error notes",
        )
        if any(
            not isinstance(note, str) or not note.strip()
            for note in critical_error_notes.values()
        ):
            raise ValueError(f"{context} critical errors require notes")

        duration = _strict_number(row, "duration_seconds", context, minimum=0.001)
        if duration > task.time_cap_seconds:
            raise ValueError(f"{context} duration exceeds the frozen task cap")
        _strict_int(row, "seq_score", context, minimum=1, maximum=7)
        _strict_int(row, "confidence", context, minimum=1, maximum=7)
        if not str(row.get("observed_outcome") or "").strip():
            raise ValueError("UX attempts require an observed outcome")

        completed = all(criterion_results.values()) and not critical_error_codes
        effective_duration = (
            float(duration) if completed or task_id != "UX02" else float(task.time_cap_seconds)
        )
        normalized = {
            **row,
            "completed": completed,
            "critical_error_count": len(critical_error_codes),
            "effective_duration_seconds": effective_duration,
        }
        task_attempts[task_id].append(normalized)
        validated_attempts.append(normalized)

    expected_pairs = {
        (participant_id, task_id) for participant_id in participant_ids for task_id in expected
    }
    if observed_pairs != expected_pairs:
        raise ValueError("every UX participant must attempt each frozen task exactly once")

    attempt_count = len(validated_attempts)
    completed_count = sum(row["completed"] is True for row in validated_attempts)
    completion_by_task = {
        task_id: sum(row["completed"] is True for row in rows) / len(rows)
        for task_id, rows in task_attempts.items()
    }
    evidence_rate = (
        sum(row["criterion_results"]["UX01-C03"] is True for row in task_attempts["UX01"])
        / participant_count
    )
    freshness_rate = (
        sum(
            row["criterion_results"]["UX04-C01"] is True
            and row["criterion_results"]["UX04-C02"] is True
            for row in task_attempts["UX04"]
        )
        / participant_count
    )
    official_source_rate = (
        sum(row["criterion_results"]["UX02-C03"] is True for row in task_attempts["UX02"])
        / participant_count
    )
    near_me_seconds = [
        float(row["effective_duration_seconds"]) for row in task_attempts["UX02"]
    ]

    def completion_by_single_slice(
        participant_dimension: dict[str, str], counts: Counter[str]
    ) -> dict[str, float]:
        return {
            slice_name: sum(
                row["completed"] is True
                for row in validated_attempts
                if participant_dimension[str(row["participant_id"])] == slice_name
            )
            / (count * len(expected))
            for slice_name, count in sorted(counts.items())
        }

    def completion_by_multi_slice() -> dict[str, float]:
        return {
            method: sum(
                row["completed"] is True
                for row in validated_attempts
                if method in participant_access_methods[str(row["participant_id"])]
            )
            / (count * len(expected))
            for method, count in sorted(access_method_counts.items())
        }

    def distribution(counter: Counter[str]) -> tuple[dict[str, int], dict[str, float]]:
        counts = dict(sorted(counter.items()))
        return counts, {key: value / participant_count for key, value in counts.items()}

    completion_by_cohort = completion_by_single_slice(participant_cohorts, cohort_counts)
    completion_by_device = completion_by_single_slice(
        participant_device_classes, device_class_counts
    )
    completion_by_access = completion_by_multi_slice()
    participant_outcomes = []
    for participant_id in sorted(participant_ids):
        participant_rows = [
            row for row in validated_attempts if row["participant_id"] == participant_id
        ]
        near_me_row = next(row for row in participant_rows if row["task_id"] == "UX02")
        participant_outcomes.append(
            {
                "participant_id": participant_id,
                "completion_rate": sum(row["completed"] is True for row in participant_rows)
                / len(expected),
                "near_me_seconds": near_me_row["effective_duration_seconds"],
            }
        )
    cohort_distribution, cohort_shares = distribution(cohort_counts)
    device_distribution, device_shares = distribution(device_class_counts)
    access_distribution, access_shares = distribution(access_method_counts)
    seed = int(commit[:8], 16) ^ (0 if report["label"] == "before" else 1)
    return {
        "status": "complete",
        "label": report.get("label"),
        "commit": commit,
        "deployment_id": report.get("deployment_id"),
        "protocol_id": report.get("protocol_id"),
        "participant_count": participant_count,
        "task_count": len(expected),
        "attempts": attempt_count,
        "completed": completed_count,
        "task_completion_rate": completed_count / attempt_count,
        "min_task_completion_rate": min(completion_by_task.values()),
        "critical_error_count": sum(
            int(row["critical_error_count"]) for row in validated_attempts
        ),
        "near_me_median_seconds": float(statistics.median(near_me_seconds)),
        "median_seq_score": float(
            statistics.median(int(row["seq_score"]) for row in validated_attempts)
        ),
        "evidence_comprehension_rate": evidence_rate,
        "freshness_comprehension_rate": freshness_rate,
        "official_source_open_rate": official_source_rate,
        "accessibility_coverage": True,
        "cohort_counts": cohort_distribution,
        "cohort_shares": cohort_shares,
        "device_class_counts": device_distribution,
        "device_class_shares": device_shares,
        "access_method_counts": access_distribution,
        "access_method_shares": access_shares,
        "completion_by_task": completion_by_task,
        "completion_by_cohort": completion_by_cohort,
        "completion_by_device_class": completion_by_device,
        "completion_by_access_method": completion_by_access,
        "completion_wilson_95ci": _wilson_interval(completed_count, attempt_count),
        "completion_by_task_wilson_95ci": {
            task_id: _wilson_interval(sum(row["completed"] is True for row in rows), len(rows))
            for task_id, rows in sorted(task_attempts.items())
        },
        "worst_core_cohort_completion_rate": min(
            completion_by_cohort[cohort] for cohort in UX_REQUIRED_COHORTS
        ),
        "worst_device_class_completion_rate": min(completion_by_device.values()),
        "participant_outcomes": participant_outcomes,
        "bootstrap": _bootstrap_ux_round(participant_outcomes, seed=seed),
    }


def _ux_distribution_comparability(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    dimensions = {
        "cohort": (
            "cohort_counts",
            "cohort_shares",
            UX_REQUIRED_COHORTS,
            UX_MINIMUM_CORE_COHORT_SIZE,
            True,
        ),
        "device_class": (
            "device_class_counts",
            "device_class_shares",
            UX_REQUIRED_DEVICE_CLASSES,
            UX_MINIMUM_DEVICE_CLASS_SIZE,
            True,
        ),
        "access_method": (
            "access_method_counts",
            "access_method_shares",
            UX_REQUIRED_ACCESS_METHODS,
            1,
            False,
        ),
    }
    issues: list[str] = []
    profiles: dict[str, dict[str, dict[str, float]]] = {"before": {}, "after": {}}

    for label, ux in (("before", before), ("after", after)):
        if ux.get("status") != "complete":
            issues.append(f"{label} UX sampling evidence is not complete")
            continue
        participant_count = ux.get("participant_count")
        if (
            isinstance(participant_count, bool)
            or not isinstance(participant_count, int)
            or participant_count < 12
        ):
            issues.append(f"{label} UX participant count is invalid")
            continue
        for dimension, (
            counts_key,
            shares_key,
            required,
            minimum_count,
            _compare_shares,
        ) in dimensions.items():
            raw_counts = ux.get(counts_key)
            raw_shares = ux.get(shares_key)
            if not isinstance(raw_counts, dict) or not isinstance(raw_shares, dict):
                issues.append(f"{label} UX {dimension} distribution is missing")
                continue
            valid_counts = all(
                isinstance(key, str)
                and bool(key)
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
                for key, value in raw_counts.items()
            )
            is_partition = dimension != "access_method"
            counts_match_population = (
                sum(raw_counts.values()) == participant_count
                if is_partition
                else all(int(value) <= participant_count for value in raw_counts.values())
            )
            if not valid_counts or not counts_match_population:
                issues.append(f"{label} UX {dimension} counts are invalid")
                continue
            if any(raw_counts.get(category, 0) < minimum_count for category in required):
                issues.append(f"{label} UX {dimension} coverage is incomplete")
            computed_shares = {
                str(key): int(value) / participant_count for key, value in raw_counts.items()
            }
            valid_shares = set(raw_shares) == set(computed_shares) and all(
                isinstance(raw_shares.get(key), (int, float))
                and not isinstance(raw_shares.get(key), bool)
                and math.isfinite(float(raw_shares[key]))
                and math.isclose(float(raw_shares[key]), share, rel_tol=0, abs_tol=1e-12)
                for key, share in computed_shares.items()
            )
            if not valid_shares:
                issues.append(f"{label} UX {dimension} shares do not match its counts")
                continue
            profiles[label][dimension] = computed_shares

    dimension_deltas: dict[str, dict[str, float]] = {}
    maximum_delta = 0.0
    for dimension, distribution_spec in dimensions.items():
        if not distribution_spec[4]:
            continue
        before_shares = profiles["before"].get(dimension)
        after_shares = profiles["after"].get(dimension)
        if before_shares is None or after_shares is None:
            continue
        deltas = {
            category: abs(before_shares.get(category, 0.0) - after_shares.get(category, 0.0))
            for category in sorted(set(before_shares) | set(after_shares))
        }
        dimension_deltas[dimension] = deltas
        dimension_maximum = max(deltas.values(), default=0.0)
        maximum_delta = max(maximum_delta, dimension_maximum)
        if dimension_maximum > UX_DISTRIBUTION_MAX_SHARE_DELTA and not math.isclose(
            dimension_maximum,
            UX_DISTRIBUTION_MAX_SHARE_DELTA,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            issues.append(
                f"UX {dimension} maximum share delta {dimension_maximum:.3f} exceeds "
                f"{UX_DISTRIBUTION_MAX_SHARE_DELTA:.3f}"
            )
    effect_intervals = _ux_effect_intervals(before, after)
    return {
        "passed": not issues,
        "maximum_allowed_share_delta": UX_DISTRIBUTION_MAX_SHARE_DELTA,
        "maximum_observed_share_delta": maximum_delta,
        "share_deltas": dimension_deltas,
        "effect_intervals": effect_intervals,
        "issues": issues,
    }


def _ux_effect_intervals(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    seed: int = 20260808,
    resamples: int = 5_000,
) -> dict[str, Any]:
    """Bootstrap independent-cohort completion and Near Me effects when raw slices exist."""

    before_rows = before.get("participant_outcomes")
    after_rows = after.get("participant_outcomes")
    if not isinstance(before_rows, list) or not isinstance(after_rows, list):
        return {
            "status": "not_available",
            "reason": "participant-level derived outcomes are absent",
        }
    if not before_rows or not after_rows:
        return {"status": "not_available", "reason": "participant outcomes are empty"}

    def values(rows: list[Any], label: str) -> tuple[list[float], list[float]]:
        completion: list[float] = []
        near_me: list[float] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{label} UX participant outcome {index} must be an object")
            _require_exact_keys(
                row,
                {"participant_id", "completion_rate", "near_me_seconds"},
                context=f"{label} UX participant outcome {index}",
            )
            rate = row.get("completion_rate")
            seconds = row.get("near_me_seconds")
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(float(rate))
                or not 0 <= float(rate) <= 1
                or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(float(seconds))
                or float(seconds) <= 0
            ):
                raise ValueError(f"{label} UX participant outcome {index} is invalid")
            completion.append(float(rate))
            near_me.append(float(seconds))
        return completion, near_me

    before_completion, before_near_me = values(before_rows, "before")
    after_completion, after_near_me = values(after_rows, "after")
    randomizer = random.Random(seed)
    completion_deltas: list[float] = []
    near_me_improvements: list[float] = []
    for _ in range(resamples):
        sampled_before_completion = [
            before_completion[randomizer.randrange(len(before_completion))]
            for _ in before_completion
        ]
        sampled_after_completion = [
            after_completion[randomizer.randrange(len(after_completion))]
            for _ in after_completion
        ]
        sampled_before_near = [
            before_near_me[randomizer.randrange(len(before_near_me))] for _ in before_near_me
        ]
        sampled_after_near = [
            after_near_me[randomizer.randrange(len(after_near_me))] for _ in after_near_me
        ]
        completion_deltas.append(
            statistics.mean(sampled_after_completion)
            - statistics.mean(sampled_before_completion)
        )
        near_me_improvements.append(
            statistics.median(sampled_before_near) - statistics.median(sampled_after_near)
        )
    near_interval = {
        "lower": _percentile(near_me_improvements, 0.025),
        "upper": _percentile(near_me_improvements, 0.975),
    }
    established = near_interval["lower"] > 0
    return {
        "status": "complete",
        "seed": seed,
        "resamples": resamples,
        "completion_rate_delta_95ci": {
            "lower": _percentile(completion_deltas, 0.025),
            "upper": _percentile(completion_deltas, 0.975),
        },
        "near_me_seconds_improvement_95ci": near_interval,
        "near_me_improvement_established": established,
        "near_me_interpretation": (
            "established improvement"
            if established
            else "observed sample difference; interval crosses or reaches no effect"
        ),
    }


def _execution_environment_comparability(
    before_identity: dict[str, Any], after_identity: dict[str, Any]
) -> dict[str, Any]:
    before = before_identity.get("execution_environment")
    after = after_identity.get("execution_environment")
    issues: list[str] = []
    if not isinstance(before, dict):
        issues.append("before snapshot has no execution-environment identity")
        before = {}
    if not isinstance(after, dict):
        issues.append("after snapshot has no execution-environment identity")
        after = {}
    missing_before = [field for field in EXECUTION_ENVIRONMENT_FIELDS if field not in before]
    missing_after = [field for field in EXECUTION_ENVIRONMENT_FIELDS if field not in after]
    if missing_before:
        issues.append(f"before execution environment is missing {missing_before}")
    if missing_after:
        issues.append(f"after execution environment is missing {missing_after}")
    for label, environment in (("before", before), ("after", after)):
        invalid_fields = [
            field
            for field in EXECUTION_ENVIRONMENT_FIELDS
            if field in environment
            and (
                (
                    field == "logical_cpu_count"
                    and (
                        isinstance(environment[field], bool)
                        or not isinstance(environment[field], int)
                        or environment[field] < 1
                    )
                )
                or (
                    field != "logical_cpu_count"
                    and (
                        not isinstance(environment[field], str)
                        or not environment[field].strip()
                        or environment[field] in {"unknown", "unavailable"}
                    )
                )
            )
        ]
        if invalid_fields:
            issues.append(f"{label} execution environment has invalid {invalid_fields}")
    differing_fields = [
        field
        for field in EXECUTION_ENVIRONMENT_FIELDS
        if field in before and field in after and before[field] != after[field]
    ]
    if differing_fields:
        issues.append(f"execution environments differ in {differing_fields}")
    return {
        "passed": not issues,
        "required_fields": list(EXECUTION_ENVIRONMENT_FIELDS),
        "differing_fields": differing_fields,
        "issues": issues,
    }
