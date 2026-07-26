"""Inspectable corpus coverage and PDF layout-quality audit."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pdfplumber
import yaml

from firelens.storage import atomic_text_writer


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def audit_corpus(project_root: Path, output_path: Path) -> dict[str, Any]:
    registry_path = project_root / "data/sources/source_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    included = [
        source for source in registry["sources"] if source.get("corpus_action") == "include"
    ]
    authority = Counter(source["authority_class"] for source in included)
    temporal = Counter(source["temporal_class"] for source in included)
    topics: dict[str, list[str]] = defaultdict(list)
    layout_candidates: list[dict[str, Any]] = []
    extraction_flags: list[dict[str, Any]] = []

    for source in included:
        for topic in source.get("intended_use", []):
            topics[topic].append(source["source_id"])
        if source["source_type"] != "pdf":
            continue
        records = {
            row["page_number"]: row
            for row in _jsonl(
                project_root / "data/processed" / f"{source['source_id']}.pages.jsonl"
            )
        }
        raw_path = project_root / source["local_file"]
        with pdfplumber.open(raw_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                table_count = len(page.find_tables())
                record = records.get(page_number, {})
                flags = list(record.get("quality_flags", []))
                if table_count >= 2:
                    layout_candidates.append(
                        {
                            "source_id": source["source_id"],
                            "page_number": page_number,
                            "layout_regions_detected": table_count,
                            "review_priority": "high" if table_count >= 5 else "normal",
                            "extraction_status": record.get("extraction_status"),
                            "quality_flags": flags,
                            "note": (
                                "Conservative layout candidate; detector may include design boxes "
                                "and does not prove that a semantic table exists."
                            ),
                        }
                    )
                if flags or record.get("extraction_status") != "text_extracted":
                    extraction_flags.append(
                        {
                            "source_id": source["source_id"],
                            "page_number": page_number,
                            "extraction_status": record.get("extraction_status"),
                            "quality_flags": flags,
                        }
                    )

    report = {
        "report_version": "firelens_corpus_audit.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_version": registry.get("registry_version"),
        "included_source_count": len(included),
        "reviewed_hash_count": sum(bool(source.get("expected_sha256")) for source in included),
        "source_review_date_count": sum(
            bool(source.get("source_reviewed_on")) for source in included
        ),
        "coverage": {
            "authority_classes": dict(sorted(authority.items())),
            "temporal_classes": dict(sorted(temporal.items())),
            "topics": {key: sorted(value) for key, value in sorted(topics.items())},
        },
        "layout_review_candidates": layout_candidates,
        "extraction_quality_flags": extraction_flags,
        "limitations": [
            "Layout-region detection is a review aid, not proof of a semantic table.",
            "This report does not establish semantic completeness of extracted text.",
        ],
    }
    with atomic_text_writer(output_path) as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report
