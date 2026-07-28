"""Versioned, deterministic text rendered for retrieval only."""

from __future__ import annotations

from firelens.contracts import RetrievalTextStrategy
from firelens.ingestion.chunking import ChunkRecord


def render_retrieval_text(
    chunk: ChunkRecord,
    strategy: RetrievalTextStrategy,
    *,
    document_context: str | None = None,
) -> str:
    """Return index/rerank text while preserving ``chunk.text`` for citations."""

    if strategy == RetrievalTextStrategy.ORIGINAL_V1:
        return chunk.text
    if strategy == RetrievalTextStrategy.METADATA_CONTEXT_V1:
        fields = [
            f"Publisher: {chunk.publisher}",
            f"Document: {chunk.title}",
        ]
        if chunk.section_title:
            fields.append(f"Section: {chunk.section_title}")
        if chunk.locator:
            fields.append(f"Locator: {chunk.locator}")
        fields.extend(
            [
                "Temporal class: stable guidance",
                f"Passage: {chunk.text}",
            ]
        )
        return "\n".join(fields)
    if strategy == RetrievalTextStrategy.DOCUMENT_CONTEXT_V2:
        if document_context is None:
            raise ValueError(f"missing document context for chunk {chunk.chunk_id}")
        return "\n".join(
            [
                f"Document context: {document_context}",
                f"Publisher: {chunk.publisher}",
                f"Document: {chunk.title}",
                f"Passage: {chunk.text}",
            ]
        )
    raise ValueError(f"Unsupported retrieval text strategy: {strategy}")
