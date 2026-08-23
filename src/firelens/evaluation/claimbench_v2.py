"""Frozen ClaimBench v2 loader. Catalog must not change after checker work."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field

from firelens.evaluation.claimbench import ClaimBenchCase, StrictModel, evaluate_case
from firelens.evaluation.claimbench_v2_catalog import extra_v2_cases
from firelens.evaluation.common import file_sha256

CLAIMBENCH_V1_RELATIVE = "data/evaluation/claimbench_v1_6.yaml"
CLAIMBENCH_V2_RELATIVE = "data/evaluation/claimbench_v1_6_2.yaml"
MANIFEST_V2_RELATIVE = "data/evaluation/claimbench_v1_6_2.manifest.json"
MINIMUM_TOTAL = 320
MINIMUM_FAITHFUL = 80
MINIMUM_MUTATIONS = 240


class ClaimBenchV2Catalog(StrictModel):
    schema_version: Literal["firelens_claimbench.v2"]
    catalog_id: str
    parent_catalog_id: str
    independent_examiner_cases_still_required: bool
    cases: list[ClaimBenchCase] = Field(min_length=MINIMUM_TOTAL)


def load_claimbench_v2(repository_root: Path) -> ClaimBenchV2Catalog:
    path = repository_root / CLAIMBENCH_V2_RELATIVE
    return ClaimBenchV2Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def evaluate_v2_catalog(catalog: ClaimBenchV2Catalog) -> dict[str, Any]:
    rows = [evaluate_case(case) for case in catalog.cases]
    faithful = [row for row in rows if row["kind"] == "faithful"]
    mutations = [row for row in rows if row["kind"] == "mutation"]
    unsafe_false_accept = sum(1 for row in mutations if row["accepted"])
    faithful_false_reject = sum(1 for row in faithful if not row["accepted"])
    by_dimension: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "mutations": 0,
            "unsafe_false_accepts": 0,
            "faithful": 0,
            "faithful_rejects": 0,
        }
    )
    for case, row in zip(catalog.cases, rows, strict=True):
        bucket = by_dimension[case.dimension]
        if case.kind == "mutation":
            bucket["mutations"] += 1
            if row["accepted"]:
                bucket["unsafe_false_accepts"] += 1
        else:
            bucket["faithful"] += 1
            if not row["accepted"]:
                bucket["faithful_rejects"] += 1
    coverage = []
    for dimension, bucket in sorted(by_dimension.items()):
        if bucket["mutations"] == 0:
            continue
        coverage.append(
            {
                "dimension": dimension,
                "mutations": bucket["mutations"],
                "unsafe_false_accept_rate": bucket["unsafe_false_accepts"]
                / bucket["mutations"],
                "covered": bucket["unsafe_false_accepts"] == 0,
            }
        )
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
        # Salvage and one-rewrite re-run validate_draft / output_rail; a checker
        # rejection cannot be published by those later layers.
        "full_pipeline_unsafe_publication_rate": (
            unsafe_false_accept / len(mutations) if mutations else 1.0
        ),
        "partial_salvage_bypass_rate": (
            unsafe_false_accept / len(mutations) if mutations else 1.0
        ),
        "rewrite_bypass_rate": unsafe_false_accept / len(mutations) if mutations else 1.0,
        "risk_coverage_curve": coverage,
        "dimensions_fully_covered": sum(1 for item in coverage if item["covered"]),
        "dimensions_with_mutations": len(coverage),
        "incorrect_ids": [row["id"] for row in rows if not row["correct"]],
        "rows": rows,
    }


def catalog_v2_identity(repository_root: Path) -> dict[str, str]:
    return {
        "path": CLAIMBENCH_V2_RELATIVE,
        "sha256": file_sha256(repository_root / CLAIMBENCH_V2_RELATIVE),
    }


def write_claimbench_v2(repository_root: Path) -> dict[str, object]:
    parent = yaml.safe_load(
        (repository_root / CLAIMBENCH_V1_RELATIVE).read_text(encoding="utf-8")
    )
    parent_ids = {case["id"] for case in parent["cases"]}
    extras = extra_v2_cases()
    extra_ids = {case["id"] for case in extras}
    if parent_ids & extra_ids:
        raise ValueError("ClaimBench v2 extras collide with v1 ids")
    cases = [*parent["cases"], *extras]
    catalog = {
        "schema_version": "firelens_claimbench.v2",
        "catalog_id": "firelens_claimbench_v1_6_2",
        "parent_catalog_id": "firelens_claimbench_v1_6",
        "independent_examiner_cases_still_required": True,
        "cases": cases,
    }
    output = repository_root / CLAIMBENCH_V2_RELATIVE
    manifest = repository_root / MANIFEST_V2_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    faithful = sum(1 for case in cases if case["kind"] == "faithful")
    mutations = sum(1 for case in cases if case["kind"] == "mutation")
    payload = {
        "catalog_id": "firelens_claimbench_v1_6_2",
        "parent_catalog_id": "firelens_claimbench_v1_6",
        "path": CLAIMBENCH_V2_RELATIVE,
        "sha256": file_sha256(output),
        "case_count": len(cases),
        "faithful": faithful,
        "mutations": mutations,
        "independent_examiner_cases_still_required": True,
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
