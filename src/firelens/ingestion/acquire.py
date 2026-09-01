"""Download registered source snapshots without requiring an LLM or API key."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import urllib.request
from html import escape
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import yaml
from lxml import html

from firelens.ingestion.pdf import IngestionError
from firelens.storage import atomic_binary_writer, atomic_text_writer

USER_AGENT = "FireLens-BC-RAG/1.0 source-acquisition"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
APPROVED_SOURCE_HOSTS = frozenset(
    {
        "firesmartbc.ca",
        "www.bccdc.ca",
        "www.emergencyinfobc.gov.bc.ca",
        "www2.gov.bc.ca",
    }
)


def canonical_official_html(payload: bytes, *, required_quote: str) -> bytes:
    """Return a stable article snapshot, excluding volatile transport shell data."""

    document = cast(html.HtmlElement, html.fromstring(payload))
    removable_nodes = cast(
        list[html.HtmlElement],
        document.xpath("//script|//style|//nav|//header|//footer"),
    )
    for node in removable_nodes:
        node.drop_tree()
    article = cast(list[html.HtmlElement], document.xpath("//main|//article"))
    root = article[0] if article else document
    heading = cast(list[html.HtmlElement], root.xpath(".//h1[1]"))
    text = " ".join(root.text_content().split())
    title = " ".join(heading[0].text_content().split()) if heading else "Official guidance"
    if required_quote not in text:
        raise IngestionError("Official article snapshot lacks its required exact quotation.")
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        f"<main><h1>{escape(title)}</h1><p>{escape(text)}</p></main>"
        "</body></html>"
    ).encode()


def _load_sources(registry_path: Path) -> list[dict[str, Any]]:
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return list(registry.get("sources", []))


def _validate_payload(source: dict[str, Any], payload: bytes) -> None:
    source_type = source["source_type"]
    if source_type == "pdf" and not payload.startswith(b"%PDF-"):
        raise IngestionError(f"{source['source_id']} did not return a PDF.")
    if source_type == "html" and b"<html" not in payload[:5000].lower():
        raise IngestionError(f"{source['source_id']} did not return HTML.")
    expected_hash = source.get("expected_sha256")
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise IngestionError(
            f"{source['source_id']} bytes do not match the reviewed SHA-256; "
            "review the changed source before updating the registry."
        )


def _validated_source_url(source: dict[str, Any]) -> str:
    value = source.get("canonical_url")
    if not isinstance(value, str):
        raise IngestionError(f"{source['source_id']} has no canonical HTTPS URL.")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in APPROVED_SOURCE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise IngestionError(
            f"{source['source_id']} canonical URL is outside approved HTTPS hosts."
        )
    return value


def _validated_destination(project_root: Path, local_file: str) -> Path:
    root = project_root.resolve()
    destination = (root / local_file).resolve()
    if destination == root or not destination.is_relative_to(root):
        raise IngestionError("Registered source local_file escapes the project root.")
    return destination


def acquire_source(source: dict[str, Any], project_root: Path) -> Path:
    """Download one non-live registered source to its declared local path."""

    if source.get("corpus_action") == "exclude_live":
        raise IngestionError("Live sources cannot be snapshotted into the static corpus.")
    local_file = source.get("local_file")
    if not isinstance(local_file, str) or not local_file:
        raise IngestionError(f"{source['source_id']} has no declared local_file.")
    canonical_url = _validated_source_url(source)
    destination = _validated_destination(project_root, local_file)

    request = urllib.request.Request(
        canonical_url,
        headers={"User-Agent": USER_AGENT},
    )
    try:

        def fetch() -> tuple[bytes, str]:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read(MAX_SOURCE_BYTES + 1), str(response.geturl())

        payload, final_url = fetch()
        raw_hashes: tuple[str, str] | None = None
        if source.get("snapshot_policy") == "canonical_article_v1":
            second_payload, second_url = fetch()
            if second_url != final_url:
                raise IngestionError(
                    "Official source redirect changed between acquisition reads."
                )
            required_quote = str(source.get("required_exact_quote") or "")
            first_raw = payload
            first = canonical_official_html(first_raw, required_quote=required_quote)
            second = canonical_official_html(second_payload, required_quote=required_quote)
            if first != second:
                raise IngestionError(
                    "Official article content changed between acquisition reads."
                )
            payload = first
            raw_hashes = (
                hashlib.sha256(first_raw).hexdigest(),
                hashlib.sha256(second_payload).hexdigest(),
            )
        if _validated_source_url({**source, "canonical_url": final_url}) != final_url:
            raise IngestionError("Registered source redirected outside approved hosts.")
    except Exception as exc:
        if isinstance(exc, IngestionError):
            raise
        raise IngestionError(
            f"Unable to download registered source {source['source_id']}."
        ) from exc
    if len(payload) > MAX_SOURCE_BYTES:
        raise IngestionError(f"{source['source_id']} exceeded the acquisition size limit.")
    _validate_payload(source, payload)

    with atomic_binary_writer(destination) as stream:
        stream.write(payload)
    if raw_hashes is not None:
        record = destination.with_suffix(destination.suffix + ".acquisition.json")
        with atomic_text_writer(record) as stream:
            json.dump(
                {
                    "source_id": source["source_id"],
                    "snapshot_policy": "canonical_article_v1",
                    "raw_response_sha256": list(raw_hashes),
                    "canonical_sha256": hashlib.sha256(payload).hexdigest(),
                },
                stream,
                sort_keys=True,
            )
            stream.write("\n")
    return destination


def acquire_registered_sources(
    registry_path: Path,
    project_root: Path,
    *,
    source_ids: set[str] | None = None,
) -> list[tuple[str, Path]]:
    selected = source_ids or set()
    sources = [
        source
        for source in _load_sources(registry_path)
        if source.get("local_file")
        and source.get("corpus_action") != "exclude_live"
        and (not selected or source["source_id"] in selected)
    ]
    if selected - {source["source_id"] for source in sources}:
        raise IngestionError("One or more requested source IDs are unavailable.")
    return [(source["source_id"], acquire_source(source, project_root)) for source in sources]


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
    for source_id, path in acquire_registered_sources(
        args.registry,
        args.project_root,
        source_ids=set(args.source_id or []),
    ):
        media_type, _ = mimetypes.guess_type(path.name)
        print(f"Acquired {source_id} -> {path} ({media_type or 'binary'})")


if __name__ == "__main__":
    main()
