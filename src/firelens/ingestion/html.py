"""Extract stable, provenance-preserving sections from approved HTML sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lxml import html

from firelens.ingestion.pdf import IngestionError, load_source_record


SCHEMA_VERSION = "section_record.v1"
_SPACE = re.compile(r"\s+")
_REMOVE_XPATH = ".//script|.//style|.//noscript|.//svg|.//form|.//template"


@dataclass(frozen=True)
class SectionRecord:
    """One headed HTML section with stable source and retrieval metadata."""

    schema_version: str
    record_id: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    temporal_class: str
    authority_class: str
    document_sha256: str
    section_index: int
    section_id: str
    heading_path: tuple[str, ...]
    text: str
    char_count: int
    extraction_status: str
    quality_flags: tuple[str, ...]
    retrieved_at: str


def _normalized_text(element: Any) -> str:
    return _SPACE.sub(" ", element.text_content()).strip()


def _content_root(document: Any) -> Any:
    """Choose a publisher-specific content container without navigation chrome."""

    bc_gov = document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), '
        '" topicContent__main ")]'
    )
    if bc_gov:
        return bc_gov[0]

    bccdc = document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), '
        '" ms-rtestate-field ")]'
    )
    if bccdc:
        return max(bccdc, key=lambda element: len(_normalized_text(element)))

    mains = document.xpath("//main")
    if mains:
        return max(mains, key=lambda element: len(_normalized_text(element)))
    raise IngestionError("No approved HTML content container was found.")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "section"


def _extract_sections(root: Any, source: dict[str, Any]) -> list[tuple[tuple[str, ...], str]]:
    """Walk headings and readable blocks in document order."""

    for element in list(root.xpath(_REMOVE_XPATH)):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)

    heading_stack: list[tuple[int, str]] = [(1, source["title"])]
    sections: list[tuple[tuple[str, ...], str]] = []
    active_lines: list[str] = []

    def flush() -> None:
        nonlocal active_lines
        deduplicated = list(dict.fromkeys(line for line in active_lines if line))
        body = "\n".join(deduplicated).strip()
        if len(body) >= 50:
            path = tuple(title for _, title in heading_stack)
            if len(path) > 2 and deduplicated:
                contextual_heading = " > ".join(path[1:])
                body = "\n".join([contextual_heading, *deduplicated[1:]]).strip()
            sections.append((path, body))
        active_lines = []

    for element in root.xpath(".//h1|.//h2|.//h3|.//h4|.//p|.//li"):
        if element.tag in {"h1", "h2", "h3", "h4"}:
            heading = _normalized_text(element)
            if not heading or not heading.replace("\u200b", "").strip():
                continue
            if (
                source["source_id"] == "bccdc_wildfire_smoke"
                and heading.casefold() == "translated content"
            ):
                flush()
                break
            flush()
            level = int(element.tag[1])
            heading_stack = [
                item for item in heading_stack if item[0] < level
            ]
            heading_stack.append((level, heading))
            active_lines.append(heading)
            continue

        if element.tag == "p" and element.xpath("ancestor::li"):
            continue
        if element.tag == "li" and element.xpath(".//li"):
            continue
        text = _normalized_text(element)
        if re.match(r"^Rank\s+[1-6]\s*[–-]", text):
            flush()
            heading_stack = [item for item in heading_stack if item[0] < 2]
            heading_stack.append((2, text))
            active_lines.append(text)
            continue
        if text:
            active_lines.append(text)

    flush()
    return sections


def ingest_html(
    html_path: Path,
    source: dict[str, Any],
    *,
    retrieved_at: datetime | None = None,
) -> list[SectionRecord]:
    """Extract reviewed stable guidance into headed section records."""

    if not html_path.is_file():
        raise IngestionError(f"HTML does not exist: {html_path}")
    raw = html_path.read_bytes()
    if b"<html" not in raw[:5000].lower():
        raise IngestionError(f"File does not appear to contain HTML: {html_path}")
    if source.get("temporal_class") != "stable_guidance":
        raise IngestionError("Live-status HTML must not enter the static corpus.")

    try:
        document = html.fromstring(raw)
        root = _content_root(document)
        extracted = _extract_sections(root, source)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"Unable to extract HTML: {html_path}") from exc
    if not extracted:
        raise IngestionError(f"No usable HTML sections found: {html_path}")

    document_sha256 = hashlib.sha256(raw).hexdigest()
    timestamp = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records: list[SectionRecord] = []
    used_ids: dict[str, int] = {}
    for section_index, (heading_path, text) in enumerate(extracted, start=1):
        base = _slug(heading_path[-1])
        used_ids[base] = used_ids.get(base, 0) + 1
        section_id = base if used_ids[base] == 1 else f"{base}-{used_ids[base]}"
        records.append(
            SectionRecord(
                schema_version=SCHEMA_VERSION,
                record_id=f"{source['source_id']}:section:{section_id}",
                source_id=source["source_id"],
                title=source["title"],
                publisher=source["publisher"],
                canonical_url=source["canonical_url"],
                temporal_class=source["temporal_class"],
                authority_class=source["authority_class"],
                document_sha256=document_sha256,
                section_index=section_index,
                section_id=section_id,
                heading_path=heading_path,
                text=text,
                char_count=len(text),
                extraction_status="text_extracted",
                quality_flags=(),
                retrieved_at=timestamp.isoformat(),
            )
        )
    return records


def write_jsonl(records: Iterable[SectionRecord], output_path: Path) -> int:
    materialized = list(records)
    if not materialized:
        raise IngestionError("Refusing to write an empty section collection.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in materialized:
            stream.write(
                json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n"
            )
    return len(materialized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract stable, provenance-preserving sections from HTML."
    )
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = load_source_record(
        args.registry, args.source_id, expected_source_type="html"
    )
    records = ingest_html(args.html, source)
    count = write_jsonl(records, args.output)
    print(f"Wrote {count} section records to {args.output}")


if __name__ == "__main__":
    main()
