"""Isolated GraphRAG preparation and evidence-based promotion rules."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from firelens.ingestion.chunking import ChunkRecord
from firelens.storage import atomic_text_writer


def prepare_graphrag_workspace(
    chunks: Sequence[ChunkRecord], *, output_dir: Path, openrouter_base_url: str
) -> dict[str, Any]:
    """Export raw chunks without granting graph summaries citation authority."""

    input_dir = output_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    export_path = input_dir / "firelens_chunks.jsonl"
    with atomic_text_writer(export_path) as stream:
        for chunk in chunks:
            stream.write(
                json.dumps(
                    {
                        "id": chunk.chunk_id,
                        "text": chunk.text,
                        "title": chunk.title,
                        "source_id": chunk.source_id,
                        "canonical_url": chunk.canonical_url,
                        "document_sha256": chunk.document_sha256,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    settings = {
        "models": {
            "default_chat_model": {
                "type": "openai_chat",
                "model": "google/gemini-3.5-flash-lite",
                "api_base": openrouter_base_url,
                "api_key": "${OPENROUTER_API_KEY}",
                "model_supports_json": True,
            },
            "default_embedding_model": {
                "type": "openai_embedding",
                "model": "openai/text-embedding-3-small",
                "api_base": openrouter_base_url,
                "api_key": "${OPENROUTER_API_KEY}",
            },
        },
        "input": {"type": "file", "file_type": "json", "base_dir": "input"},
        "output": {"type": "file", "base_dir": "output"},
    }
    settings_path = output_dir / "settings.yaml"
    with atomic_text_writer(settings_path) as stream:
        yaml.safe_dump(settings, stream, sort_keys=False)
    return {
        "chunk_count": len(chunks),
        "input_path": str(export_path),
        "settings_path": str(settings_path),
        "citation_authority": "raw_chunk_ids_only",
    }


def select_graphrag(
    *,
    standard_passes: int,
    graph_passes: int,
    case_count: int,
    provenance_rate: float,
    ordinary_regressions: int,
    p95_latency_seconds: float,
    cost_ratio: float,
) -> tuple[bool, str]:
    if not 12 <= case_count <= 15:
        return False, "relationship evaluation must contain 12 to 15 cases"
    if graph_passes < standard_passes + 2:
        return False, "GraphRAG did not add two fully passing relationship cases"
    if provenance_rate != 1.0:
        return False, "GraphRAG did not preserve complete raw-chunk provenance"
    if ordinary_regressions:
        return False, "GraphRAG caused ordinary-query regressions"
    if p95_latency_seconds > 10:
        return False, "GraphRAG exceeded the ten-second p95 gate"
    if cost_ratio > 5:
        return False, "GraphRAG exceeded the five-times cost gate"
    return True, "GraphRAG cleared every promotion gate"
