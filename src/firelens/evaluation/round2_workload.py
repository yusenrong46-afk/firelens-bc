"""Frozen representative Ask workload for matched V1.5 vs Round-2 measurement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.evaluation.common import file_sha256

WORKLOAD_RELATIVE = "data/evaluation/v1_6_round2_performance_workload.yaml"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkloadRoute(StrictModel):
    id: str = Field(min_length=3, max_length=80)
    weight: float = Field(gt=0, le=1)
    question: str = Field(min_length=8, max_length=500)


class PerformanceWorkload(StrictModel):
    schema_version: str
    workload_id: str
    label: str
    not_fleet_average: bool
    warmup_per_route: int = Field(ge=1)
    measured_per_route: int = Field(ge=1)
    case_count: int = Field(ge=1)
    routes: list[WorkloadRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def weights_and_count_match(self) -> PerformanceWorkload:
        if len(self.routes) != self.case_count:
            raise ValueError("case_count must equal the number of declared routes")
        total = round(sum(route.weight for route in self.routes), 10)
        if total != 1.0:
            raise ValueError("route weights must sum to 1.0")
        if self.label != "representative_workload_average" or not self.not_fleet_average:
            raise ValueError("this mix is a representative average, not a fleet average")
        return self


def load_performance_workload(repository_root: Path) -> PerformanceWorkload:
    path = repository_root / WORKLOAD_RELATIVE
    return PerformanceWorkload.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def workload_identity(repository_root: Path) -> dict[str, Any]:
    path = repository_root / WORKLOAD_RELATIVE
    return {"path": WORKLOAD_RELATIVE, "sha256": file_sha256(path)}
