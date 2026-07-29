from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from firelens.config import FireLensConfig
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.providers.fake import FakeProvider
from firelens.retrieval.embeddings import build_vector_index
from firelens.runtime import Runtime, load_runtime


def make_chunk(
    chunk_id: str,
    text: str,
    *,
    parent: str = "parent-a",
    index: int = 0,
    authority: str = "provincial_government",
) -> ChunkRecord:
    return ChunkRecord(
        schema_version="firelens.chunk.v1",
        chunk_id=chunk_id,
        parent_record_id=parent,
        source_id="source-a",
        title="Preparedness Guide",
        publisher="Government of British Columbia",
        canonical_url="https://example.test/preparedness",
        temporal_class="stable_guidance",
        authority_class=authority,
        document_sha256="a" * 64,
        page_number=index + 1,
        chunk_index=index,
        section_title="Preparation",
        text=text,
        char_count=len(text),
        retrieved_at="2026-07-25T00:00:00Z",
        locator=f"PDF page {index + 1}",
    )


def write_test_corpus(root: Path, chunks: list[ChunkRecord]) -> FireLensConfig:
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    corpus = processed / "firelens_static_corpus.chunks.jsonl"
    corpus.write_text(
        "".join(json.dumps(asdict(chunk), sort_keys=True) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    source_ids = sorted({chunk.source_id for chunk in chunks})
    manifest = {
        "corpus_version": "test-corpus.v1",
        "combined_chunk_count": len(chunks),
        "included_source_count": len(source_ids),
        "sources": [
            {
                "source_id": source_id,
                "corpus_action": "include",
                "review_status": "approved_static",
            }
            for source_id in source_ids
        ],
    }
    (processed / "firelens_static_corpus.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return FireLensConfig.from_env(root).model_copy(
        update={"embedding_model": "fake/embedding", "debug": True}
    )


async def make_runtime(
    root: Path,
    *,
    provider: AIProvider | None = None,
    chunks: list[ChunkRecord] | None = None,
) -> tuple[Runtime, FakeProvider | AIProvider, FireLensConfig]:
    records = chunks or [
        make_chunk(
            "chunk-a0",
            "Prepare an emergency kit with water, food, medication, and a flashlight.",
            index=0,
        ),
        make_chunk(
            "chunk-a1",
            "Review the kit regularly and replace expired supplies.",
            index=1,
        ),
        make_chunk(
            "chunk-b0",
            "Keep important documents in a secure and accessible place.",
            parent="parent-b",
            index=0,
        ),
    ]
    config = write_test_corpus(root, records)
    active_provider = provider or FakeProvider()
    await build_vector_index(
        records,
        corpus_version="test-corpus.v1",
        config=config,
        provider=active_provider,
    )
    runtime = load_runtime(config, provider=active_provider)
    return runtime, active_provider, config
