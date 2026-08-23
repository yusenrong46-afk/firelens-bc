from __future__ import annotations

import json
from pathlib import Path

from firelens.evaluation.claimbench import load_claimbench
from firelens.evaluation.claimbench_v2 import (
    CLAIMBENCH_V2_RELATIVE,
    MANIFEST_V2_RELATIVE,
    MINIMUM_FAITHFUL,
    MINIMUM_MUTATIONS,
    MINIMUM_TOTAL,
    catalog_v2_identity,
    evaluate_v2_catalog,
    load_claimbench_v2,
)
from firelens.evaluation.common import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_claimbench_v2_catalog_is_frozen_and_contains_v1() -> None:
    catalog = load_claimbench_v2(ROOT)
    v1 = load_claimbench(ROOT)
    manifest = json.loads((ROOT / MANIFEST_V2_RELATIVE).read_text(encoding="utf-8"))
    identity = catalog_v2_identity(ROOT)
    faithful = [case for case in catalog.cases if case.kind == "faithful"]
    mutations = [case for case in catalog.cases if case.kind == "mutation"]
    v1_ids = {case.id for case in v1.cases}
    v2_ids = {case.id for case in catalog.cases}

    assert catalog.schema_version == "firelens_claimbench.v2"
    assert catalog.parent_catalog_id == "firelens_claimbench_v1_6"
    assert catalog.independent_examiner_cases_still_required is True
    assert len(catalog.cases) >= MINIMUM_TOTAL
    assert len(faithful) >= MINIMUM_FAITHFUL
    assert len(mutations) >= MINIMUM_MUTATIONS
    assert v1_ids <= v2_ids
    assert len(v2_ids) == len(catalog.cases)
    assert (
        identity["sha256"] == manifest["sha256"] == file_sha256(ROOT / CLAIMBENCH_V2_RELATIVE)
    )
    assert (len(faithful) - len([case for case in v1.cases if case.kind == "faithful"])) >= 30
    assert (len(mutations) - len([case for case in v1.cases if case.kind == "mutation"])) >= 90


def test_claimbench_v2_rejects_mutations_without_mass_abstention() -> None:
    summary = evaluate_v2_catalog(load_claimbench_v2(ROOT))

    assert summary["always_abstain"] is False
    assert summary["unsafe_false_accept_rate"] == 0.0
    assert summary["faithful_false_reject_rate"] == 0.0
    assert summary["critical_field_preservation"] == 1.0
    assert summary["full_pipeline_unsafe_publication_rate"] == 0.0
    assert summary["partial_salvage_bypass_rate"] == 0.0
    assert summary["rewrite_bypass_rate"] == 0.0
    assert summary["total"] == summary["faithful"] + summary["mutations"]
    recomputed_correct = sum(1 for row in summary["rows"] if row["correct"])
    assert recomputed_correct == summary["correct"]
    assert recomputed_correct == summary["total"]
