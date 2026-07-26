"""Content-hash embedding cache and reproducible local index construction."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from firelens.config import FireLensConfig
from firelens.errors import IndexValidationError
from firelens.ingestion.chunking import ChunkRecord
from firelens.providers.base import AIProvider
from firelens.storage import atomic_binary_writer, atomic_text_writer, exclusive_file_lock

INDEX_SCHEMA_VERSION = "firelens_vector_index.v1"
CACHE_SCHEMA_VERSION = "firelens_embedding_cache.v1"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def content_sha256(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


class EmbeddingCacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CACHE_SCHEMA_VERSION
    model: str
    chunk_content_sha256: str
    dimensions: int = Field(gt=0)
    vector: list[float]
    created_at: str


class VectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = INDEX_SCHEMA_VERSION
    corpus_version: str
    corpus_sha256: str
    embedding_model: str
    dimensions: int = Field(gt=0)
    chunk_ids: list[str]
    matrix_sha256: str
    created_at: str


def _cache_key(model: str, content_hash: str) -> tuple[str, str]:
    return model, content_hash


def load_embedding_cache(path: Path) -> dict[tuple[str, str], EmbeddingCacheRecord]:
    if not path.is_file():
        return {}
    records: dict[tuple[str, str], EmbeddingCacheRecord] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = EmbeddingCacheRecord.model_validate_json(line)
            except ValidationError as exc:
                raise IndexValidationError(
                    f"Invalid embedding cache record on line {line_number}."
                ) from exc
            key = _cache_key(record.model, record.chunk_content_sha256)
            if key in records:
                raise IndexValidationError("Embedding cache contains duplicate keys.")
            records[key] = record
    return records


def _validate_vector(vector: Sequence[float], dimensions: int | None = None) -> int:
    if not vector:
        raise IndexValidationError("Embedding vector cannot be empty.")
    if dimensions is not None and len(vector) != dimensions:
        raise IndexValidationError("Embedding dimensions do not match.")
    if any(not math.isfinite(float(value)) for value in vector):
        raise IndexValidationError("Embedding vector contains a non-finite value.")
    if not any(float(value) != 0.0 for value in vector):
        raise IndexValidationError("Embedding vector cannot be all zeros.")
    return len(vector)


def _write_cache(records: dict[tuple[str, str], EmbeddingCacheRecord], path: Path) -> None:
    with atomic_text_writer(path) as stream:
        for key in sorted(records):
            stream.write(records[key].model_dump_json())
            stream.write("\n")


async def _build_vector_index_unlocked(
    chunks: Sequence[ChunkRecord],
    *,
    corpus_version: str,
    config: FireLensConfig,
    provider: AIProvider,
) -> VectorManifest:
    """Reuse cached vectors, embed misses in batches, and persist a normalized matrix."""

    if not chunks:
        raise IndexValidationError("Cannot build a vector index without chunks.")
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise IndexValidationError("Vector index chunk IDs must be unique.")

    cache = load_embedding_cache(config.embedding_cache_path)
    vectors: list[list[float] | None] = [None] * len(chunks)
    missing_indices: list[int] = []
    dimensions: int | None = None

    for index, chunk in enumerate(chunks):
        content_hash = content_sha256(chunk.text)
        record = cache.get(_cache_key(config.embedding_model, content_hash))
        if record is None:
            missing_indices.append(index)
            continue
        _validate_vector(record.vector, record.dimensions)
        dimensions = _validate_vector(record.vector, dimensions)
        vectors[index] = record.vector

    for start in range(0, len(missing_indices), config.embedding_batch_size):
        batch_indices = missing_indices[start : start + config.embedding_batch_size]
        response = await provider.embed([chunks[index].text for index in batch_indices])
        if len(response.vectors) != len(batch_indices):
            raise IndexValidationError("Provider returned the wrong embedding count.")
        for chunk_index, vector in zip(batch_indices, response.vectors, strict=True):
            dimensions = _validate_vector(vector, dimensions)
            values = [float(value) for value in vector]
            vectors[chunk_index] = values
            content_hash = content_sha256(chunks[chunk_index].text)
            cache[_cache_key(config.embedding_model, content_hash)] = EmbeddingCacheRecord(
                model=config.embedding_model,
                chunk_content_sha256=content_hash,
                dimensions=dimensions,
                vector=values,
                created_at=datetime.now(UTC).isoformat(),
            )

    if dimensions is None or any(vector is None for vector in vectors):
        raise IndexValidationError("Vector index construction was incomplete.")

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0) or not np.isfinite(matrix).all():
        raise IndexValidationError("Embedding matrix contains invalid values.")
    matrix = matrix / norms

    with atomic_binary_writer(config.vector_matrix_path) as stream:
        np.save(stream, matrix, allow_pickle=False)
    _write_cache(cache, config.embedding_cache_path)

    manifest = VectorManifest(
        corpus_version=corpus_version,
        corpus_sha256=sha256_file(config.corpus_path),
        embedding_model=config.embedding_model,
        dimensions=dimensions,
        chunk_ids=chunk_ids,
        matrix_sha256=sha256_file(config.vector_matrix_path),
        created_at=datetime.now(UTC).isoformat(),
    )
    with atomic_text_writer(config.vector_manifest_path) as stream:
        stream.write(json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n")
    return manifest


async def build_vector_index(
    chunks: Sequence[ChunkRecord],
    *,
    corpus_version: str,
    config: FireLensConfig,
    provider: AIProvider,
) -> VectorManifest:
    lock_path = config.vector_manifest_path.with_suffix(".lock")
    with exclusive_file_lock(lock_path):
        return await _build_vector_index_unlocked(
            chunks,
            corpus_version=corpus_version,
            config=config,
            provider=provider,
        )
