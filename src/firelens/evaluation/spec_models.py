"""Strict data models for the V1.5-2 benchmark and dataset-role protocol."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Forbid undeclared protocol fields."""

    model_config = ConfigDict(extra="forbid")


class ToleranceSpec(StrictModel):
    absolute: float = Field(ge=0)
    relative: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def finite_values(self) -> ToleranceSpec:
        if not math.isfinite(self.absolute) or not math.isfinite(self.relative):
            raise ValueError("metric tolerances must be finite")
        return self


class MetricSpec(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    track: Literal[
        "zero_cost",
        "network_no_model_cost",
        "paid_development",
        "paid_qualified",
        "human",
        "deployment",
    ]
    value_type: Literal["boolean", "integer", "number"]
    direction: Literal["higher_is_better", "lower_is_better"]
    comparison_mode: Literal["paired", "after_only", "prerequisite"]
    comparison_requirement: Literal["no_regression", "must_improve", "gate_only"]
    tolerance: ToleranceSpec | None = None
    required_after: bool = False
    gate_operator: Literal["gte", "lte", "eq"] | None = None
    gate_value: Any = None

    @model_validator(mode="after")
    def gate_is_complete(self) -> MetricSpec:
        if (self.gate_operator is None) != (self.gate_value is None):
            raise ValueError("gate_operator and gate_value must be supplied together")
        if self.value_type == "boolean":
            _validate_boolean_metric(self)
        else:
            _validate_numeric_metric(self)
        _validate_metric_comparison(self)
        return self


def _validate_boolean_metric(metric: MetricSpec) -> None:
    if metric.tolerance is not None:
        raise ValueError("boolean metrics cannot define a numeric tolerance")
    if metric.gate_value is not None and type(metric.gate_value) is not bool:
        raise ValueError("boolean metric gates require a strict boolean value")
    if metric.gate_operator not in {None, "eq"}:
        raise ValueError("boolean metric gates must use eq")


def _validate_numeric_metric(metric: MetricSpec) -> None:
    if metric.comparison_mode == "paired" and metric.tolerance is None:
        raise ValueError("paired numeric metrics require a ratified tolerance")
    if metric.gate_value is not None and (
        isinstance(metric.gate_value, bool)
        or not isinstance(metric.gate_value, (int, float))
        or not math.isfinite(float(metric.gate_value))
    ):
        raise ValueError("numeric metric gates require a finite numeric value")
    if (
        metric.value_type == "integer"
        and metric.gate_value is not None
        and not isinstance(metric.gate_value, int)
    ):
        raise ValueError("integer metric gates require an integer value")


def _validate_metric_comparison(metric: MetricSpec) -> None:
    if metric.comparison_mode in {"after_only", "prerequisite"}:
        if metric.comparison_requirement != "gate_only":
            raise ValueError("after-only and prerequisite metrics must use gate_only")
        if not metric.required_after or metric.gate_operator is None:
            raise ValueError(
                "after-only and prerequisite metrics require an explicit after gate"
            )
    if metric.comparison_requirement == "must_improve" and metric.comparison_mode != "paired":
        raise ValueError("must_improve requires paired comparison")


class DatasetRoleEntry(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    role: Literal[
        "development",
        "permanent_regression",
        "sealed_release_qualification",
        "planned_sealed_qualification",
        "paired_human",
        "red_team",
    ]
    status: Literal["available", "planned"]
    inputs: list[str] = Field(min_length=1)
    splits: list[str] = Field(min_length=1)
    baseline_policy: Literal["paired", "required_after_only", "not_scored"]
    allowed_uses: list[str] = Field(min_length=1)
    prohibited_uses: list[str] = Field(min_length=1)
    notes: str


class DatasetRoleRegistry(StrictModel):
    schema_version: Literal["firelens_evaluation_dataset_roles.v1"]
    registry_id: str
    ratification_status: Literal["provisional", "ratified"]
    ratified_at: datetime | None = None
    open_decisions: list[str] = Field(default_factory=list)
    description: str
    datasets: list[DatasetRoleEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_and_safe_roles(self) -> DatasetRoleRegistry:
        if self.ratification_status == "ratified":
            if self.ratified_at is None or self.open_decisions:
                raise ValueError(
                    "a ratified dataset-role registry requires a timestamp and no open decisions"
                )
        elif self.ratified_at is not None:
            raise ValueError("a provisional dataset-role registry cannot have ratified_at")
        ids = [item.id for item in self.datasets]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset role IDs must be unique")
        for item in self.datasets:
            _validate_dataset_role(item)
        return self


def _validate_dataset_role(item: DatasetRoleEntry) -> None:
    if set(item.allowed_uses) & set(item.prohibited_uses):
        raise ValueError(f"dataset role {item.id} has conflicting allowed uses")
    if item.role in {"sealed_release_qualification", "planned_sealed_qualification"}:
        if item.baseline_policy != "required_after_only":
            raise ValueError("sealed qualification must be required-after-only")
        required_prohibitions = {"paired_before_after", "tuning"}
        if not required_prohibitions.issubset(set(item.prohibited_uses)):
            raise ValueError("sealed qualification is missing required prohibitions")
    if item.role == "sealed_release_qualification" and item.status != "available":
        raise ValueError("sealed release qualification must be available")
    if item.role == "planned_sealed_qualification" and item.status != "planned":
        raise ValueError(
            "planned sealed qualification cannot become available without role conversion"
        )
    if (
        item.status == "available"
        and item.baseline_policy == "required_after_only"
        and item.role != "sealed_release_qualification"
    ):
        raise ValueError("available required-after-only data must use the sealed release role")


class UXCriterion(StrictModel):
    id: str = Field(pattern=r"^UX[0-9]{2}-C[0-9]{2}$")
    description: str = Field(min_length=1, max_length=500)


class UXCriticalError(StrictModel):
    code: str = Field(pattern=r"^UX[0-9]{2}-E[0-9]{2}$")
    description: str = Field(min_length=1, max_length=500)


class UXTask(StrictModel):
    id: str = Field(pattern=r"^UX[0-9]{2}$")
    name: str
    critical_success: str
    time_cap_seconds: int = Field(ge=30, le=600)
    completion_criteria: list[UXCriterion] = Field(min_length=1)
    critical_errors: list[UXCriticalError] = Field(min_length=1)

    @model_validator(mode="after")
    def criterion_ids_match_task(self) -> UXTask:
        criterion_ids = [criterion.id for criterion in self.completion_criteria]
        error_codes = [error.code for error in self.critical_errors]
        if len(criterion_ids) != len(set(criterion_ids)) or len(error_codes) != len(
            set(error_codes)
        ):
            raise ValueError("UX task criterion and critical-error IDs must be unique")
        if any(not value.startswith(f"{self.id}-") for value in (*criterion_ids, *error_codes)):
            raise ValueError("UX task criteria and critical errors must match the task ID")
        return self


class BenchmarkSpec(StrictModel):
    schema_version: Literal["firelens_upgrade_benchmark_spec.v2"]
    benchmark_id: str
    frozen_before_upgrade: bool
    description: str
    dataset_role_registry: str
    before_snapshot_seal: str = Field(min_length=1)
    identity_inputs: list[str] = Field(min_length=1)
    harness_inputs: list[str] = Field(min_length=1)
    tracks: dict[str, list[str]]
    comparison_metrics: list[MetricSpec] = Field(min_length=1)
    ux_tasks: list[UXTask] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> BenchmarkSpec:
        metric_keys = [metric.key for metric in self.comparison_metrics]
        task_ids = [task.id for task in self.ux_tasks]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("comparison metric keys must be unique")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("UX task IDs must be unique")
        return self
