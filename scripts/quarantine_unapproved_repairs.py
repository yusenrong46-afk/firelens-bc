#!/usr/bin/env python3
"""Remove non-human text repairs while preserving aligned reviewed vectors."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from firelens.ingestion.repairs import load_text_repairs, validate_chunk_repair_provenance
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.embeddings import VectorManifest, sha256_file
from firelens.storage import atomic_binary_writer, atomic_text_writer


def quarantine(project_root: Path) -> dict[str, object]:
    corpus_path = project_root / "data/processed/firelens_static_corpus.chunks.jsonl"
    corpus_manifest_path = project_root / "data/processed/firelens_static_corpus.manifest.json"
    vector_path = project_root / "data/index/firelens_vectors.npy"
    vector_manifest_path = project_root / "data/index/firelens_vectors.manifest.json"
    repairs_path = project_root / "data/repairs/text_overrides.yaml"

    chunks = load_chunk_records(corpus_path)
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    vector_manifest = VectorManifest.model_validate_json(
        vector_manifest_path.read_text(encoding="utf-8")
    )
    with vector_path.open("rb") as stream:
        matrix = np.load(stream, allow_pickle=False)
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if chunk_ids != vector_manifest.chunk_ids or matrix.shape[0] != len(chunks):
        raise RuntimeError("Corpus and vector rows are not aligned; refusing to migrate.")

    repairs = load_text_repairs(repairs_path)
    repairs_by_target = {
        (
            repair["source_id"],
            int(repair["page_number"]),
            repair["document_sha256"],
        ): repair
        for repair in repairs
    }
    retained = []
    keep_indices: list[int] = []
    removed_ids: list[str] = []
    for index, chunk in enumerate(chunks):
        target = (chunk.source_id, chunk.page_number, chunk.document_sha256)
        repair = repairs_by_target.get(target) if chunk.page_number is not None else None
        if repair is not None and repair["review_status"] != "human_verified":
            removed_ids.append(chunk.chunk_id)
            continue
        provenance = "human_verified_repair" if repair is not None else "native_text"
        retained.append(replace(chunk, review_provenance=provenance))
        keep_indices.append(index)

    validate_chunk_repair_provenance(retained, repairs)
    retained_matrix = matrix[np.asarray(keep_indices, dtype=np.int64)]
    if retained_matrix.shape[0] != len(retained):
        raise RuntimeError("Filtered corpus and vector rows diverged.")

    with atomic_text_writer(corpus_path) as stream:
        for chunk in retained:
            stream.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
    with atomic_binary_writer(vector_path) as stream:
        np.save(stream, retained_matrix, allow_pickle=False)

    counts = Counter(chunk.source_id for chunk in retained)
    parent_counts: dict[str, set[str]] = {}
    for chunk in retained:
        parent_counts.setdefault(chunk.source_id, set()).add(chunk.parent_record_id)
    for source in corpus_manifest["sources"]:
        if source.get("corpus_action") != "include":
            continue
        source_id = source["source_id"]
        source["chunk_count"] = counts[source_id]
        if source.get("source_type") == "pdf":
            source["excluded_record_count"] = max(
                0, int(source["record_count"]) - len(parent_counts.get(source_id, set()))
            )
    corpus_manifest["combined_chunk_count"] = len(retained)
    corpus_manifest["repair_provenance_policy"] = "human_verified_only.v1"
    corpus_manifest["provenance_migrated_at"] = datetime.now(UTC).isoformat()
    with atomic_text_writer(corpus_manifest_path) as stream:
        json.dump(corpus_manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")

    updated_vector_manifest = vector_manifest.model_copy(
        update={
            "corpus_sha256": sha256_file(corpus_path),
            "chunk_ids": [chunk.chunk_id for chunk in retained],
            "matrix_sha256": sha256_file(vector_path),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    with atomic_text_writer(vector_manifest_path) as stream:
        stream.write(
            json.dumps(updated_vector_manifest.model_dump(), indent=2, sort_keys=True) + "\n"
        )
    return {
        "retained_chunks": len(retained),
        "removed_chunks": len(removed_ids),
        "removed_chunk_ids": removed_ids,
        "corpus_sha256": updated_vector_manifest.corpus_sha256,
        "matrix_sha256": updated_vector_manifest.matrix_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quarantine corpus rows derived from non-human text repairs."
    )
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    result = quarantine(args.project_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
