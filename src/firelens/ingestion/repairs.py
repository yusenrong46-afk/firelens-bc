"""Apply narrowly scoped, human-reviewed repairs to defective text layers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import yaml

from firelens.ingestion.pdf import IngestionError, PageRecord


def load_text_repairs(path: Path) -> list[dict[str, Any]]:
    """Load reviewed repairs and validate the fields that make them auditable."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repairs = payload.get("repairs", [])
    required = {
        "source_id",
        "page_number",
        "document_sha256",
        "replacement_text",
        "reason",
        "review_status",
    }
    for index, repair in enumerate(repairs, start=1):
        missing = sorted(field for field in required if not repair.get(field))
        if missing:
            raise IngestionError(
                f"Text repair {index} is missing required fields: {missing}."
            )
        if repair["review_status"] != "human_verified":
            raise IngestionError(
                f"Text repair {index} is not approved for corpus use."
            )
    return repairs


def apply_text_repairs(
    records: Sequence[PageRecord],
    repairs: Sequence[dict[str, Any]],
) -> list[PageRecord]:
    """Replace only an exact source/page/hash match and preserve repair flags."""

    by_key = {
        (
            repair["source_id"],
            int(repair["page_number"]),
            repair["document_sha256"],
        ): repair
        for repair in repairs
    }
    if len(by_key) != len(repairs):
        raise IngestionError("Duplicate text-repair targets are not allowed.")

    repaired: list[PageRecord] = []
    matched: set[tuple[str, int, str]] = set()
    for record in records:
        key = (record.source_id, record.page_number, record.document_sha256)
        repair = by_key.get(key)
        if repair is None:
            repaired.append(record)
            continue

        text = str(repair["replacement_text"]).strip()
        if len(text) < 50:
            raise IngestionError(f"Replacement text is implausibly short for {key}.")
        repaired.append(
            replace(
                record,
                text=text,
                char_count=len(text),
                extraction_status="text_extracted",
                quality_flags=tuple(
                    dict.fromkeys(
                        (*record.quality_flags, "human_reviewed_text_repair")
                    )
                ),
            )
        )
        matched.add(key)

    unmatched = sorted(set(by_key) - matched)
    if unmatched:
        raise IngestionError(
            "Text repair did not match the ingested document hash: "
            + ", ".join(map(str, unmatched))
        )
    return repaired
