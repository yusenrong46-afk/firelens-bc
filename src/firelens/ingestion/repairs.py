"""Apply narrowly scoped, human-reviewed repairs to defective text layers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import yaml

from firelens.ingestion.pdf import IngestionError, PageRecord

REPAIR_REVIEW_STATUSES = frozenset(
    {"human_verified", "pending_owner_review", "automated_visual_reviewed"}
)


def load_text_repairs(path: Path) -> list[dict[str, Any]]:
    """Load reviewed repairs and validate the fields that make them auditable."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise IngestionError("Text repair registry must be a mapping.")
    raw_repairs = payload.get("repairs", [])
    if not isinstance(raw_repairs, list):
        raise IngestionError("Text repair registry repairs must be a list.")
    if any(not isinstance(repair, dict) for repair in raw_repairs):
        raise IngestionError("Each text repair must be a mapping.")
    repairs = [cast(dict[str, Any], repair) for repair in raw_repairs]
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
            raise IngestionError(f"Text repair {index} is missing required fields: {missing}.")
        if repair["review_status"] not in REPAIR_REVIEW_STATUSES:
            raise IngestionError(f"Text repair {index} has an unknown review status.")
    return list(repairs)


def apply_text_repairs(
    records: Sequence[PageRecord],
    repairs: Sequence[dict[str, Any]],
) -> list[PageRecord]:
    """Replace only an exact source/page/hash match and preserve repair flags."""

    unapproved = [
        repair for repair in repairs if repair.get("review_status") != "human_verified"
    ]
    if unapproved:
        raise IngestionError("Only human_verified text repairs are approved for corpus use.")

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
                    dict.fromkeys((*record.quality_flags, "human_reviewed_text_repair"))
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


def quarantine_unapproved_repair_pages(
    records: Sequence[PageRecord], repairs: Sequence[dict[str, Any]]
) -> tuple[list[PageRecord], list[dict[str, Any]]]:
    """Exclude pages with a pending repair before chunking, without approving it."""

    targets = {
        (repair["source_id"], int(repair["page_number"]), repair["document_sha256"]): repair
        for repair in repairs
        if repair["review_status"] != "human_verified"
    }
    kept: list[PageRecord] = []
    quarantined: list[dict[str, Any]] = []
    for record in records:
        repair = targets.get((record.source_id, record.page_number, record.document_sha256))
        if repair is None:
            kept.append(record)
            continue
        quarantined.append(
            {
                "source_id": record.source_id,
                "page_number": record.page_number,
                "document_sha256": record.document_sha256,
                "review_status": repair["review_status"],
                "reason": repair["reason"],
            }
        )
    return kept, quarantined


def validate_chunk_repair_provenance(
    chunks: Sequence[Any], repairs: Sequence[dict[str, Any]]
) -> None:
    """Fail closed if corpus chunks disagree with the page repair registry."""

    repairs_by_target = {
        (
            repair["source_id"],
            int(repair["page_number"]),
            repair["document_sha256"],
        ): repair
        for repair in repairs
    }
    for chunk in chunks:
        if chunk.page_number is None:
            continue
        target = (chunk.source_id, chunk.page_number, chunk.document_sha256)
        repair = repairs_by_target.get(target)
        if repair is None:
            if chunk.review_provenance != "native_text":
                raise IngestionError(
                    f"Chunk {chunk.chunk_id} claims repair provenance without a registry entry."
                )
            continue
        if repair["review_status"] != "human_verified":
            raise IngestionError(
                f"Chunk {chunk.chunk_id} comes from a repair pending human verification."
            )
        if chunk.review_provenance != "human_verified_repair":
            raise IngestionError(f"Chunk {chunk.chunk_id} lost its human repair provenance.")
