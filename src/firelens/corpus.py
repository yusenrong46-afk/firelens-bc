"""Build the complete reviewed static corpus before embedding generation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from firelens.ingestion.chunking import (
    ChunkRecord,
    chunk_page_records,
    chunk_section_records,
    write_chunk_jsonl,
)
from firelens.ingestion.html import ingest_html, write_jsonl as write_section_jsonl
from firelens.ingestion.pdf import (
    IngestionError,
    ingest_pdf,
    sha256_file,
    write_jsonl as write_page_jsonl,
)
from firelens.ingestion.repairs import apply_text_repairs, load_text_repairs


CORPUS_VERSION = "firelens_static_corpus.v1"


def _load_registry(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = payload.get("sources", [])
    if not sources:
        raise IngestionError("Source registry contains no sources.")
    return payload


def _write_manifest(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def build_corpus(
    project_root: Path,
    *,
    registry_path: Path,
    repairs_path: Path,
    output_dir: Path,
    generated_at: datetime | None = None,
) -> tuple[list[ChunkRecord], dict[str, Any]]:
    """Ingest, repair, chunk, validate, and manifest every included source."""

    registry = _load_registry(registry_path)
    repairs = load_text_repairs(repairs_path)
    timestamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    chunks: list[ChunkRecord] = []
    source_entries: list[dict[str, Any]] = []

    for source in registry["sources"]:
        if source.get("corpus_action") != "include":
            source_entries.append(
                {
                    "source_id": source["source_id"],
                    "corpus_action": source.get("corpus_action", "unreviewed"),
                    "review_status": source.get("review_status"),
                }
            )
            continue
        if source.get("review_status") != "approved_static":
            raise IngestionError(
                f"Included source {source['source_id']} is not approved_static."
            )

        raw_path = project_root / source["local_file"]
        if not raw_path.is_file():
            raise IngestionError(f"Missing registered source file: {raw_path}")
        source_id = source["source_id"]
        if source["source_type"] == "pdf":
            records = ingest_pdf(raw_path, source, retrieved_at=timestamp)
            relevant_repairs = [
                repair for repair in repairs if repair["source_id"] == source_id
            ]
            if relevant_repairs:
                records = apply_text_repairs(records, relevant_repairs)
            record_path = output_dir / f"{source_id}.pages.jsonl"
            record_count = write_page_jsonl(records, record_path)
            source_chunks = chunk_page_records(records)
            excluded_records = sum(
                record.extraction_status != "text_extracted" for record in records
            )
        elif source["source_type"] == "html":
            records = ingest_html(raw_path, source, retrieved_at=timestamp)
            record_path = output_dir / f"{source_id}.sections.jsonl"
            record_count = write_section_jsonl(records, record_path)
            source_chunks = chunk_section_records(records)
            excluded_records = 0
        else:
            raise IngestionError(f"Unsupported source_type for {source_id}.")

        chunk_path = output_dir / f"{source_id}.chunks.jsonl"
        write_chunk_jsonl(source_chunks, chunk_path)
        chunks.extend(source_chunks)
        source_entries.append(
            {
                "source_id": source_id,
                "source_type": source["source_type"],
                "corpus_action": "include",
                "review_status": source["review_status"],
                "canonical_url": source["canonical_url"],
                "local_file": source["local_file"],
                "document_sha256": sha256_file(raw_path),
                "record_count": record_count,
                "excluded_record_count": excluded_records,
                "chunk_count": len(source_chunks),
            }
        )

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise IngestionError("Combined corpus contains duplicate chunk IDs.")
    if not chunks:
        raise IngestionError("Combined corpus contains no chunks.")

    corpus_path = output_dir / "firelens_static_corpus.chunks.jsonl"
    write_chunk_jsonl(chunks, corpus_path)
    manifest = {
        "corpus_version": CORPUS_VERSION,
        "registry_version": registry.get("registry_version"),
        "generated_at": timestamp.isoformat(),
        "combined_chunk_file": str(corpus_path.relative_to(project_root)),
        "included_source_count": sum(
            entry.get("corpus_action") == "include" for entry in source_entries
        ),
        "combined_chunk_count": len(chunks),
        "sources": source_entries,
    }
    _write_manifest(manifest, output_dir / "firelens_static_corpus.manifest.json")
    return chunks, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the reviewed static FireLens corpus."
    )
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument(
        "--registry", type=Path, default=Path("data/sources/source_registry.yaml")
    )
    parser.add_argument(
        "--repairs", type=Path, default=Path("data/repairs/text_overrides.yaml")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed")
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = args.project_root.resolve()
    registry = args.registry if args.registry.is_absolute() else root / args.registry
    repairs = args.repairs if args.repairs.is_absolute() else root / args.repairs
    output = (
        args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    )
    _, manifest = build_corpus(
        root,
        registry_path=registry,
        repairs_path=repairs,
        output_dir=output,
    )
    print(
        f"Built {manifest['combined_chunk_count']} chunks from "
        f"{manifest['included_source_count']} approved sources."
    )


if __name__ == "__main__":
    main()
