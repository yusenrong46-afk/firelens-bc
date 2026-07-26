"""Validated in-memory cosine search over a persisted NumPy matrix."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from firelens.contracts import RetrievalHit
from firelens.errors import IndexValidationError
from firelens.ingestion.chunking import ChunkRecord
from firelens.retrieval.embeddings import VectorManifest, sha256_file


def retrieval_hit_from_chunk(chunk: ChunkRecord, **updates: object) -> RetrievalHit:
    payload: dict[str, object] = {
        "chunk_id": chunk.chunk_id,
        "parent_record_id": chunk.parent_record_id,
        "source_id": chunk.source_id,
        "title": chunk.title,
        "publisher": chunk.publisher,
        "canonical_url": chunk.canonical_url,
        "page_number": chunk.page_number,
        "section_title": chunk.section_title,
        "locator": chunk.locator,
        "temporal_class": chunk.temporal_class,
        "authority_class": chunk.authority_class,
        "document_sha256": chunk.document_sha256,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
    }
    payload.update(updates)
    return RetrievalHit.model_validate(payload)


class VectorIndex:
    def __init__(
        self,
        chunks: Sequence[ChunkRecord],
        matrix: np.ndarray,
        manifest: VectorManifest,
    ) -> None:
        if matrix.ndim != 2:
            raise IndexValidationError("Vector matrix must be two-dimensional.")
        if matrix.shape != (len(chunks), manifest.dimensions):
            raise IndexValidationError("Vector matrix shape does not match manifest.")
        if [chunk.chunk_id for chunk in chunks] != manifest.chunk_ids:
            raise IndexValidationError("Vector chunk order does not match corpus.")
        if not np.isfinite(matrix).all():
            raise IndexValidationError("Vector matrix contains non-finite values.")
        norms = np.linalg.norm(matrix, axis=1)
        if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
            raise IndexValidationError("Vector matrix rows are not normalized.")
        self.chunks = tuple(chunks)
        self.matrix = matrix.astype(np.float32, copy=False)
        self.manifest = manifest

    @classmethod
    def load(
        cls,
        chunks: Sequence[ChunkRecord],
        *,
        matrix_path: Path,
        manifest_path: Path,
        corpus_path: Path,
        corpus_version: str,
        embedding_model: str,
    ) -> VectorIndex:
        if not matrix_path.is_file() or not manifest_path.is_file():
            raise IndexValidationError("Vector index files are missing.")
        try:
            manifest = VectorManifest.model_validate(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            raise IndexValidationError("Vector manifest is invalid.") from exc
        if manifest.corpus_version != corpus_version:
            raise IndexValidationError("Vector index corpus version does not match.")
        if manifest.corpus_sha256 != sha256_file(corpus_path):
            raise IndexValidationError("Vector index corpus hash does not match.")
        if manifest.embedding_model != embedding_model:
            raise IndexValidationError("Vector index embedding model does not match.")
        if manifest.matrix_sha256 != sha256_file(matrix_path):
            raise IndexValidationError("Vector matrix hash does not match.")
        try:
            with matrix_path.open("rb") as stream:
                matrix = np.load(stream, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise IndexValidationError("Vector matrix cannot be loaded.") from exc
        return cls(chunks, matrix, manifest)

    def search(self, query_vector: Sequence[float], *, top_k: int) -> list[RetrievalHit]:
        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.manifest.dimensions:
            raise IndexValidationError("Query embedding dimensions do not match index.")
        if not np.isfinite(query).all():
            raise IndexValidationError("Query embedding contains invalid values.")
        norm = float(np.linalg.norm(query))
        if norm == 0:
            return []
        scores = self.matrix @ (query / norm)
        indices = np.argsort(-scores, kind="stable")[:top_k]
        return [
            retrieval_hit_from_chunk(
                self.chunks[int(index)],
                vector_rank=rank,
                vector_score=float(scores[int(index)]),
            )
            for rank, index in enumerate(indices, start=1)
        ]
