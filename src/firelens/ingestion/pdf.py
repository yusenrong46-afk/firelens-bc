"""Extract provenance-preserving page records from approved PDF sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
import pdfplumber
from pypdf import PdfReader


SCHEMA_VERSION = "page_record.v1"


class IngestionError(ValueError):
    """Raised when a document cannot be ingested under the R1 contract."""


@dataclass(frozen=True)
class PageRecord:
    """One extracted PDF page with enough metadata to stand alone."""

    schema_version: str
    record_id: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    temporal_class: str
    authority_class: str
    document_sha256: str
    page_number: int
    page_count: int
    text: str
    char_count: int
    extraction_status: str
    quality_flags: tuple[str, ...]
    retrieved_at: str


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source_record(
    registry_path: Path,
    source_id: str,
    *,
    expected_source_type: str = "pdf",
) -> dict[str, Any]:
    """Load one unique source from the approved source registry.

    The default remains ``pdf`` so existing PDF callers fail closed. Other
    ingestors must explicitly declare the source type they accept.
    """

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    matches = [source for source in sources if source.get("source_id") == source_id]

    if len(matches) != 1:
        raise IngestionError(
            f"Expected exactly one source_id={source_id!r}; found {len(matches)}."
        )

    source = matches[0]
    if source.get("source_type") != expected_source_type:
        raise IngestionError(
            f"Source {source_id!r} is not registered as {expected_source_type!r}."
        )

    required_fields = {
        "source_id",
        "title",
        "publisher",
        "canonical_url",
        "temporal_class",
        "authority_class",
    }
    missing = sorted(field for field in required_fields if not source.get(field))
    if missing:
        raise IngestionError(
            f"Source {source_id!r} is missing required fields: {missing}."
        )

    return source


def normalize_page_text(text: str | None) -> str:
    """Normalize line endings while preserving page-readable structure."""

    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def assess_text_quality(text: str) -> tuple[str, tuple[str, ...]]:
    """Classify obvious extraction defects without pretending to solve OCR."""

    if not text:
        return "empty", ()

    flags: list[str] = []
    if "(cid:" in text:
        flags.append("unmapped_font_glyphs")
    if len(text) < 50:
        flags.append("very_short_text")

    status = "suspect_text" if flags else "text_extracted"
    return status, tuple(flags)


def ingest_pdf(
    pdf_path: Path,
    source: dict[str, Any],
    *,
    retrieved_at: datetime | None = None,
) -> list[PageRecord]:
    """Extract one record per human-visible PDF page.

    Page numbers are one-indexed so citations match the page a user sees.
    """

    if not pdf_path.is_file():
        raise IngestionError(f"PDF does not exist: {pdf_path}")

    with pdf_path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise IngestionError(f"File does not have a PDF header: {pdf_path}")

    document_sha256 = sha256_file(pdf_path)
    timestamp = (retrieved_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    retrieved_at_iso = timestamp.isoformat()

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise IngestionError(f"Unable to open PDF: {pdf_path}") from exc

    if reader.is_encrypted:
        raise IngestionError(f"Encrypted PDFs are not supported in R1: {pdf_path}")

    page_count = len(reader.pages)
    if page_count == 0:
        raise IngestionError(f"PDF contains no pages: {pdf_path}")

    records: list[PageRecord] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) != page_count:
                raise IngestionError(
                    "PDF page-count mismatch between validation and extraction."
                )

            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    text = normalize_page_text(page.extract_text())
                except Exception as exc:
                    raise IngestionError(
                        f"Text extraction failed on page {page_number}: {pdf_path}"
                    ) from exc

                extraction_status, quality_flags = assess_text_quality(text)
                records.append(
                    PageRecord(
                        schema_version=SCHEMA_VERSION,
                        record_id=f"{source['source_id']}:page:{page_number}",
                        source_id=source["source_id"],
                        title=source["title"],
                        publisher=source["publisher"],
                        canonical_url=source["canonical_url"],
                        temporal_class=source["temporal_class"],
                        authority_class=source["authority_class"],
                        document_sha256=document_sha256,
                        page_number=page_number,
                        page_count=page_count,
                        text=text,
                        char_count=len(text),
                        extraction_status=extraction_status,
                        quality_flags=quality_flags,
                        retrieved_at=retrieved_at_iso,
                    )
                )
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"Unable to extract PDF: {pdf_path}") from exc

    return records


def write_jsonl(records: Iterable[PageRecord], output_path: Path) -> int:
    """Write page records as deterministic UTF-8 JSON Lines."""

    materialized = list(records)
    if not materialized:
        raise IngestionError("Refusing to write an empty page-record collection.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in materialized:
            stream.write(
                json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n"
            )
    return len(materialized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract provenance-preserving page records from a PDF."
    )
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = load_source_record(args.registry, args.source_id)
    records = ingest_pdf(args.pdf, source)
    count = write_jsonl(records, args.output)
    print(f"Wrote {count} page records to {args.output}")


if __name__ == "__main__":
    main()
