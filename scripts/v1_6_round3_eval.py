#!/usr/bin/env python3
"""Dump Round-3 development-suite results. Not an independent proof."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from round3_semantic_support import (  # noqa: E402
    FABLE_ADVERSARY,
    ROUND3_DEV,
    checker_row,
    load_case_file,
    publish_claim,
    summarize,
)

from firelens.evaluation.claimbench import evaluate_catalog, load_claimbench  # noqa: E402
from firelens.evaluation.claimbench_v2 import (  # noqa: E402
    evaluate_v2_catalog,
    load_claimbench_v2,
)
from firelens.evaluation.common import file_sha256  # noqa: E402


def _suite(path: Path) -> dict[str, Any]:
    cases = load_case_file(path)
    checker_rows = [checker_row(case) for case in cases]
    publication: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for case in cases:
            published, errors, leaked = publish_claim(tmp_path, case["quote"], case["claim"])
            expected_publish = case["expect"] == "accept"
            publication.append(
                {
                    "id": case["id"],
                    "expect": case["expect"],
                    "published": published,
                    "correct": published == expected_publish,
                    "salvage_leaked": leaked,
                    "errors": errors,
                }
            )
    published_mutations = [
        row["id"] for row in publication if row["expect"] == "reject" and row["published"]
    ]
    leaked = [row["id"] for row in publication if row["salvage_leaked"]]
    faithful_rejected = [
        row["id"] for row in publication if row["expect"] == "accept" and not row["published"]
    ]
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": file_sha256(path),
        "checker": {**summarize(checker_rows), "rows": checker_rows},
        "publication": {
            "total": len(publication),
            "correct": sum(1 for row in publication if row["correct"]),
            "unsafe_published": published_mutations,
            "faithful_unpublished": faithful_rejected,
            "salvage_leaks": leaked,
            "always_abstain": bool(publication)
            and all(not row["published"] for row in publication),
            "rows": publication,
        },
    }


def _claimbench_v1() -> dict[str, Any]:
    catalog = load_claimbench(ROOT)
    summary = evaluate_catalog(catalog)
    rows = summary.pop("rows")
    return {
        "sha256": file_sha256(ROOT / "data/evaluation/claimbench_v1_6.yaml"),
        **summary,
        "incorrect_ids": [row["id"] for row in rows if not row["correct"]],
        "rows": rows,
    }


def _claimbench_v2() -> dict[str, Any]:
    catalog = load_claimbench_v2(ROOT)
    summary = evaluate_v2_catalog(catalog)
    rows = summary.pop("rows")
    return {
        "sha256": file_sha256(ROOT / "data/evaluation/claimbench_v1_6_2.yaml"),
        **summary,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "firelens_v1_6_round3_eval.v1",
        "evidence_class": "EXECUTED",
        "independent_proof": False,
        "fable_round2_adversary": _suite(FABLE_ADVERSARY),
        "round3_development_adversary": _suite(ROUND3_DEV),
        "claimbench_v1": _claimbench_v1(),
        "claimbench_v2": _claimbench_v2(),
    }
    path = out / "V1_6_ROUND3_DEVELOPMENT_EVAL.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fable = payload["fable_round2_adversary"]
    extra = payload["round3_development_adversary"]
    print(
        json.dumps(
            {
                "wrote": str(path),
                "claimbench_v1": payload["claimbench_v1"]["correct"],
                "claimbench_v2": payload["claimbench_v2"]["correct"],
                "fable_checker": fable["checker"]["correct"],
                "fable_publication_correct": fable["publication"]["correct"],
                "fable_unsafe_published": fable["publication"]["unsafe_published"],
                "round3_checker": extra["checker"]["correct"],
                "round3_unsafe_published": extra["publication"]["unsafe_published"],
                "always_abstain": (
                    fable["checker"]["always_abstain"] or extra["checker"]["always_abstain"]
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
