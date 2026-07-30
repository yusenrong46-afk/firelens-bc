"""Create provenance-preserving retrieval chunks from PDF pages and HTML sections."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from firelens.ingestion.html import SectionRecord
from firelens.ingestion.pdf import IngestionError, PageRecord

SCHEMA_VERSION = "chunk_record.v2"
DEFAULT_MAX_CHARS = 900
MIN_CHARS = 80

_BULLET_PREFIXES = ("•", "¢", "-", "–", "—")
_BOILERPLATE_LINES = {"PreparedBC", "Wildfire Preparedness Guide"}


@dataclass(frozen=True)
class ChunkRecord:
    """One retrieval unit traceable to exactly one page or headed web section."""

    schema_version: str
    chunk_id: str
    parent_record_id: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    temporal_class: str
    authority_class: str
    document_sha256: str
    page_number: int | None
    chunk_index: int
    section_title: str | None
    text: str
    char_count: int
    retrieved_at: str
    source_type: str = "pdf"
    section_id: str | None = None
    locator: str | None = None
    review_provenance: Literal["native_text", "human_verified_repair"] = "native_text"


def load_page_records(path: Path) -> list[PageRecord]:
    """Load page records from JSON Lines and validate their schema."""

    records: list[PageRecord] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                payload["quality_flags"] = tuple(payload["quality_flags"])
                records.append(PageRecord(**payload))
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise IngestionError(
                    f"Invalid page record on JSONL line {line_number}: {path}"
                ) from exc

    if not records:
        raise IngestionError(f"No page records found: {path}")
    return records


def load_section_records(path: Path) -> list[SectionRecord]:
    """Load HTML section records from JSON Lines and validate their schema."""

    records: list[SectionRecord] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                payload["heading_path"] = tuple(payload["heading_path"])
                payload["quality_flags"] = tuple(payload["quality_flags"])
                records.append(SectionRecord(**payload))
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise IngestionError(
                    f"Invalid section record on JSONL line {line_number}: {path}"
                ) from exc
    if not records:
        raise IngestionError(f"No section records found: {path}")
    return records


def _is_heading(line: str) -> bool:
    """Recognize conservative heading forms found in the approved guide."""

    stripped = line.strip()
    if not stripped or stripped.startswith(_BULLET_PREFIXES):
        return False
    if stripped.startswith("TIP:"):
        return True

    letters = [character for character in stripped if character.isalpha()]
    if letters and len(stripped) <= 90 and all(character.isupper() for character in letters):
        return True

    words = stripped.rstrip(":").split()
    if (
        1 <= len(words) <= 8
        and len(stripped) <= 70
        and stripped.istitle()
        and not re.search(r"[.!?]$", stripped)
    ):
        return True

    return (
        stripped.endswith(":")
        and 1 <= len(words) <= 8
        and not stripped.startswith(("http://", "https://", "www."))
    )


def _content_lines(record: PageRecord) -> list[str]:
    """Remove known running headers and the visible page-number footer."""

    lines = [line.strip() for line in record.text.splitlines() if line.strip()]
    while lines and lines[0] in _BOILERPLATE_LINES:
        lines.pop(0)
    if lines and lines[-1] == str(record.page_number):
        lines.pop()
    return lines


def _logical_units(record: PageRecord) -> list[tuple[str | None, str]]:
    """Group visual lines without cutting headings or bullet continuations."""

    units: list[tuple[str | None, str]] = []
    current_lines: list[str] = []
    current_section: str | None = None

    def flush() -> None:
        if current_lines:
            units.append((current_section, "\n".join(current_lines)))
            current_lines.clear()

    for line in _content_lines(record):
        if _is_heading(line):
            flush()
            current_section = line
            current_lines.append(line)
            continue

        if line.startswith(_BULLET_PREFIXES):
            flush()
            current_lines.append(line)
            continue

        current_lines.append(line)
        if re.search(r'[.!?]["”\']?$', line):
            flush()

    flush()
    return units


def _merge_short_chunks(
    packed: list[tuple[str | None, str]],
) -> list[tuple[str | None, str]]:
    """Attach micro-chunks to neighboring context on the same page."""

    merged: list[tuple[str | None, str]] = []
    pending_text = ""

    for section_title, text in packed:
        if pending_text:
            text = f"{pending_text}\n{text}"
            pending_text = ""

        if len(text) < MIN_CHARS:
            pending_text = text
            continue

        merged.append((section_title, text))

    if pending_text:
        if merged:
            section_title, text = merged[-1]
            merged[-1] = (section_title, f"{text}\n{pending_text}")
        else:
            merged.append((None, pending_text))

    return merged


def chunk_page_record(
    record: PageRecord,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[ChunkRecord]:
    """Split one clean page into line-safe chunks that share page provenance."""

    if max_chars < 200:
        raise ValueError("max_chars must be at least 200.")
    if record.extraction_status != "text_extracted":
        return []

    packed: list[tuple[str | None, str]] = []
    active_section: str | None = None
    active_text = ""

    for unit_section, unit_text in _logical_units(record):
        candidate = f"{active_text}\n{unit_text}".strip()
        starts_new_section = (
            unit_section is not None
            and unit_text.splitlines()[0] == unit_section
            and bool(active_text)
        )
        if active_text and (starts_new_section or len(candidate) > max_chars):
            packed.append((active_section, active_text))
            active_text = unit_text
            active_section = unit_section
        else:
            active_text = candidate
            if active_section is None and unit_section is not None:
                active_section = unit_section

    if active_text:
        packed.append((active_section, active_text))
    packed = _merge_short_chunks(packed)

    if "automated_visual_reviewed_text_repair" in record.quality_flags:
        raise IngestionError("An unapproved automated repair cannot be chunked.")
    review_provenance: Literal["native_text", "human_verified_repair"] = (
        "human_verified_repair"
        if "human_reviewed_text_repair" in record.quality_flags
        else "native_text"
    )
    chunks: list[ChunkRecord] = []
    for chunk_index, (section_title, text) in enumerate(packed, start=1):
        chunks.append(
            ChunkRecord(
                schema_version=SCHEMA_VERSION,
                chunk_id=f"{record.record_id}:chunk:{chunk_index}",
                parent_record_id=record.record_id,
                source_id=record.source_id,
                title=record.title,
                publisher=record.publisher,
                canonical_url=record.canonical_url,
                temporal_class=record.temporal_class,
                authority_class=record.authority_class,
                document_sha256=record.document_sha256,
                page_number=record.page_number,
                chunk_index=chunk_index,
                section_title=section_title,
                text=text,
                char_count=len(text),
                retrieved_at=record.retrieved_at,
                source_type="pdf",
                section_id=None,
                locator=f"page:{record.page_number}",
                review_provenance=review_provenance,
            )
        )
    return chunks


def chunk_page_records(
    records: Sequence[PageRecord],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[ChunkRecord]:
    """Chunk all clean pages while preserving source and page order."""

    chunks: list[ChunkRecord] = []
    for record in records:
        chunks.extend(chunk_page_record(record, max_chars=max_chars))
    return chunks


def _split_long_unit(text: str, max_chars: int) -> list[str]:
    """Split an oversized HTML paragraph at sentence or word boundaries."""

    if len(text) <= max_chars:
        return [text]
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    pieces: list[str] = []
    active = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            words = sentence.split()
            for word in words:
                candidate = f"{active} {word}".strip()
                if active and len(candidate) > max_chars:
                    pieces.append(active)
                    active = word
                else:
                    active = candidate
            continue
        candidate = f"{active} {sentence}".strip()
        if active and len(candidate) > max_chars:
            pieces.append(active)
            active = sentence
        else:
            active = candidate
    if active:
        pieces.append(active)
    return pieces


def chunk_section_record(
    record: SectionRecord,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[ChunkRecord]:
    """Chunk one stable HTML section without losing its headed locator."""

    if max_chars < 200:
        raise ValueError("max_chars must be at least 200.")
    if record.extraction_status != "text_extracted":
        return []

    units: list[str] = []
    for paragraph in record.text.splitlines():
        paragraph = paragraph.strip()
        if paragraph:
            units.extend(_split_long_unit(paragraph, max_chars))

    packed: list[str] = []
    active = ""
    for unit in units:
        candidate = f"{active}\n{unit}".strip()
        if active and len(candidate) > max_chars:
            packed.append(active)
            active = unit
        else:
            active = candidate
    if active:
        packed.append(active)

    chunks: list[ChunkRecord] = []
    section_title = record.heading_path[-1] if record.heading_path else record.title
    for chunk_index, text in enumerate(packed, start=1):
        chunks.append(
            ChunkRecord(
                schema_version=SCHEMA_VERSION,
                chunk_id=f"{record.record_id}:chunk:{chunk_index}",
                parent_record_id=record.record_id,
                source_id=record.source_id,
                title=record.title,
                publisher=record.publisher,
                canonical_url=record.canonical_url,
                temporal_class=record.temporal_class,
                authority_class=record.authority_class,
                document_sha256=record.document_sha256,
                page_number=None,
                chunk_index=chunk_index,
                section_title=section_title,
                text=text,
                char_count=len(text),
                retrieved_at=record.retrieved_at,
                source_type="html",
                section_id=record.section_id,
                locator=f"section:{record.section_id}",
                review_provenance="native_text",
            )
        )
    return chunks


def chunk_section_records(
    records: Sequence[SectionRecord],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for record in records:
        chunks.extend(chunk_section_record(record, max_chars=max_chars))
    return chunks


def write_chunk_jsonl(records: Iterable[ChunkRecord], output_path: Path) -> int:
    """Write deterministic UTF-8 chunk records as JSON Lines."""

    materialized = list(records)
    if not materialized:
        raise IngestionError("Refusing to write an empty chunk collection.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in materialized:
            stream.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return len(materialized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create retrieval chunks from validated PDF page records."
    )
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pages = load_page_records(args.pages)
    chunks = chunk_page_records(pages, max_chars=args.max_chars)
    count = write_chunk_jsonl(chunks, args.output)
    excluded = sum(page.extraction_status != "text_extracted" for page in pages)
    print(f"Wrote {count} chunks to {args.output}; excluded {excluded} non-clean pages.")


if __name__ == "__main__":
    main()
