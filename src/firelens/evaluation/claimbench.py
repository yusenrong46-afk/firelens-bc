"""Frozen ClaimBench loader and deterministic evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from firelens.answering.semantic_invariants import preservation_errors
from firelens.evaluation.common import file_sha256

CLAIMBENCH_RELATIVE = "data/evaluation/claimbench_v1_6.yaml"
MANIFEST_RELATIVE = "data/evaluation/claimbench_v1_6.manifest.json"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimBenchCase(StrictModel):
    id: str
    kind: Literal["faithful", "mutation"]
    dimension: str
    quote: str = Field(min_length=8)
    claim: str = Field(min_length=8)
    expect: Literal["accept", "reject"]


class ClaimBenchCatalog(StrictModel):
    schema_version: Literal["firelens_claimbench.v1"]
    catalog_id: str
    cases: list[ClaimBenchCase] = Field(min_length=200)


def load_claimbench(repository_root: Path) -> ClaimBenchCatalog:
    path = repository_root / CLAIMBENCH_RELATIVE
    return ClaimBenchCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def evaluate_case(case: ClaimBenchCase) -> dict[str, Any]:
    errors = preservation_errors(case.claim, [case.quote])
    accepted = not errors
    expected_accept = case.expect == "accept"
    return {
        "id": case.id,
        "kind": case.kind,
        "dimension": case.dimension,
        "accepted": accepted,
        "expected_accept": expected_accept,
        "correct": accepted == expected_accept,
        "errors": errors,
    }


def evaluate_catalog(catalog: ClaimBenchCatalog) -> dict[str, Any]:
    rows = [evaluate_case(case) for case in catalog.cases]
    faithful = [row for row in rows if row["kind"] == "faithful"]
    mutations = [row for row in rows if row["kind"] == "mutation"]
    unsafe_false_accept = sum(1 for row in mutations if row["accepted"])
    faithful_false_reject = sum(1 for row in faithful if not row["accepted"])
    return {
        "total": len(rows),
        "faithful": len(faithful),
        "mutations": len(mutations),
        "correct": sum(row["correct"] for row in rows),
        "unsafe_false_accept_rate": unsafe_false_accept / len(mutations) if mutations else 1.0,
        "faithful_false_reject_rate": (
            faithful_false_reject / len(faithful) if faithful else 1.0
        ),
        "critical_field_preservation": 1.0
        - (unsafe_false_accept / len(mutations) if mutations else 1.0),
        "always_abstain": all(not row["accepted"] for row in rows),
        "partial_salvage_correctness": (
            1.0
            if faithful
            and mutations
            and unsafe_false_accept == 0
            and faithful_false_reject == 0
            else 0.0
        ),
        "rows": rows,
    }


def catalog_identity(repository_root: Path) -> dict[str, str]:
    return {
        "path": CLAIMBENCH_RELATIVE,
        "sha256": file_sha256(repository_root / CLAIMBENCH_RELATIVE),
    }
