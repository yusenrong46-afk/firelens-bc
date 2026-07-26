"""Download registered source snapshots without requiring an LLM or API key."""

from __future__ import annotations

import argparse
import mimetypes
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from firelens.ingestion.pdf import IngestionError


USER_AGENT = "FireLens-BC-RAG/1.0 source-acquisition"


def _load_sources(registry_path: Path) -> list[dict[str, Any]]:
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return list(registry.get("sources", []))


def _validate_payload(source: dict[str, Any], payload: bytes) -> None:
    source_type = source["source_type"]
    if source_type == "pdf" and not payload.startswith(b"%PDF-"):
        raise IngestionError(f"{source['source_id']} did not return a PDF.")
    if source_type == "html" and b"<html" not in payload[:5000].lower():
        raise IngestionError(f"{source['source_id']} did not return HTML.")


def acquire_source(source: dict[str, Any], project_root: Path) -> Path:
    """Download one non-live registered source to its declared local path."""

    if source.get("corpus_action") == "exclude_live":
        raise IngestionError("Live sources cannot be snapshotted into the static corpus.")
    local_file = source.get("local_file")
    if not local_file:
        raise IngestionError(f"{source['source_id']} has no declared local_file.")

    request = urllib.request.Request(
        source["canonical_url"],
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read()
    except Exception as exc:
        raise IngestionError(
            f"Unable to download registered source {source['source_id']}."
        ) from exc
    _validate_payload(source, payload)

    destination = project_root / local_file
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download non-live sources declared in the source registry."
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--source-id", action="append")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected = set(args.source_id or [])
    sources = [
        source
        for source in _load_sources(args.registry)
        if source.get("local_file")
        and source.get("corpus_action") != "exclude_live"
        and (not selected or source["source_id"] in selected)
    ]
    if selected - {source["source_id"] for source in sources}:
        raise IngestionError("One or more requested source IDs are unavailable.")
    for source in sources:
        path = acquire_source(source, args.project_root)
        media_type, _ = mimetypes.guess_type(path.name)
        print(f"Acquired {source['source_id']} -> {path} ({media_type or 'binary'})")


if __name__ == "__main__":
    main()
