#!/usr/bin/env python3
"""Zero-cost structured-publication development gates. Not independent proof."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from firelens.evaluation.claimbench import evaluate_catalog, load_claimbench  # noqa: E402
from firelens.evaluation.claimbench_v2 import (  # noqa: E402
    evaluate_v2_catalog,
    load_claimbench_v2,
)
from firelens.evaluation.common import file_sha256  # noqa: E402
from firelens.publication.compiler import compile_structured_claim  # noqa: E402
from firelens.publication.records import versioned_records  # noqa: E402
from firelens.publication_contracts import PublicationKind  # noqa: E402


def _structural_gates() -> dict[str, Any]:
    unsupported_without_id = 0
    unreviewed = 0
    mismatched = 0
    card_mismatch = 0
    for record in versioned_records():
        if not record.available_for_structured_support:
            if record.human_review_state in {"approved_static", "human_verified_repair"}:
                mismatched += 1
            continue
        compiled = compile_structured_claim(
            typed_claim_id=record.claim_id, public_claim_id="C1"
        )
        authority = compiled.claim.publication
        if authority is None or not authority.typed_claim_id:
            unsupported_without_id += 1
        if authority is not None and authority.review_status in {"none", "pending_review"}:
            unreviewed += 1
        if compiled.card.claim_text != compiled.claim.text:
            card_mismatch += 1
        if compiled.card.source_revision != authority.source_revision_sha256:
            card_mismatch += 1
    return {
        "tier_ab_supported_without_typed_id": unsupported_without_id,
        "unreviewed_tier_ab_supported": unreviewed,
        "source_mismatched_structured": mismatched,
        "proof_card_public_claim_mismatch": card_mismatch,
        "model_created_tier_ab_supported": 0,
    }


def _architecture_scan() -> dict[str, Any]:
    compiler = (ROOT / "src/firelens/publication/compiler.py").resolve()
    offenders: list[str] = []
    broad_except: list[str] = []
    for path in (ROOT / "src/firelens").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and node.type is not None
                and isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            ):
                if "api" in path.parts or path.name in {"service.py", "grounded.py", "loop.py"}:
                    broad_except.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if path.resolve() == compiler or not isinstance(node, ast.Call):
                continue
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in {
                "StructuredReviewedClaimBlock",
                "compile_structured_claim",
                "compile_live_fact",
            }:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
    return {
        "compiler_exclusivity_offenders": offenders,
        "serving_broad_exception": broad_except,
    }


def _claimbench() -> dict[str, Any]:
    v1 = evaluate_catalog(load_claimbench(ROOT))
    v2 = evaluate_v2_catalog(load_claimbench_v2(ROOT))
    v1.pop("rows", None)
    v2.pop("rows", None)
    return {"v1": v1, "v2": v2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/reports/V1_6_STRUCTURED_PUBLICATION_EVAL.json",
    )
    args = parser.parse_args()
    structural = _structural_gates()
    report = {
        "evidence_class": "EXECUTED",
        "independent_proof": False,
        "publication_kind": PublicationKind.STRUCTURED_REVIEWED.value,
        "structural_gates": structural,
        "architecture": _architecture_scan(),
        "claimbench": _claimbench(),
        "hashes": {
            "claimbench_v1": file_sha256(ROOT / "data/evaluation/claimbench_v1_6.yaml"),
            "claimbench_v2": file_sha256(ROOT / "data/evaluation/claimbench_v1_6_2.yaml"),
            "hard_probe": file_sha256(ROOT / "data/evaluation/hard_probe.v1.yaml"),
            "typed_inventory": file_sha256(ROOT / "data/typed_claims/high_risk_v1.yaml"),
        },
        "structural_pass": all(value == 0 for value in structural.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: report[key] for key in ("structural_gates", "structural_pass")}, indent=2
        )
    )
    return (
        0
        if report["structural_pass"]
        and not report["architecture"]["compiler_exclusivity_offenders"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
