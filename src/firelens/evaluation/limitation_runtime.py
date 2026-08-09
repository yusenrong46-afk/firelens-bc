"""Corpus materialization and deterministic scoring for limitation probes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from firelens.config import FireLensConfig
from firelens.corpus_admission import ADMISSION_POLICY_VERSION, quarantine_rejected_sources
from firelens.evaluation.limitation_cases import ProbeCase
from firelens.ingestion.chunking import SCHEMA_VERSION, ChunkRecord
from firelens.providers.openrouter import OpenRouterProvider
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.embeddings import build_vector_index, sha256_file

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output" / "naive_user_probe"
DATA_EVAL = ROOT / "data" / "evaluation"


def _html_to_chunk(
    *,
    source_id: str,
    title: str,
    publisher: str,
    url: str,
    html_path: Path,
    chunk_index: int = 1,
) -> ChunkRecord:
    text = re.sub(r"<[^>]+>", " ", html_path.read_text(encoding="utf-8"))
    text = " ".join(text.split())
    digest = hashlib.sha256(html_path.read_bytes()).hexdigest()
    return ChunkRecord(
        schema_version=SCHEMA_VERSION,
        chunk_id=f"{source_id}:section:1:chunk:{chunk_index}",
        parent_record_id=f"{source_id}:section:1",
        source_id=source_id,
        title=title,
        publisher=publisher,
        canonical_url=url,
        temporal_class="stable_guidance",
        authority_class="provincial_government",
        document_sha256=digest,
        page_number=None,
        chunk_index=chunk_index,
        section_title=title,
        text=text,
        char_count=len(text),
        retrieved_at=datetime.now(UTC).isoformat(),
        source_type="html",
        section_id="1",
        locator="section:1",
    )


def _write_corpus(
    chunks: list[ChunkRecord],
    *,
    corpus_path: Path,
    manifest_path: Path,
    corpus_version: str,
) -> tuple[list[ChunkRecord], dict[str, Any]]:
    admitted, admission_findings = quarantine_rejected_sources(chunks)
    if not admitted:
        raise RuntimeError("Corpus admission quarantined every source in the probe profile.")
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("w", encoding="utf-8") as stream:
        for chunk in admitted:
            stream.write(json.dumps(asdict(chunk), sort_keys=True) + "\n")
    sources: dict[str, dict[str, Any]] = {}
    for chunk in admitted:
        entry = sources.setdefault(
            chunk.source_id,
            {
                "source_id": chunk.source_id,
                "corpus_action": "include",
                "review_status": "approved_static",
                "source_type": chunk.source_type,
                "canonical_url": chunk.canonical_url,
                "chunk_count": 0,
                "document_sha256": chunk.document_sha256,
            },
        )
        entry["chunk_count"] += 1
    manifest = {
        "combined_chunk_count": len(admitted),
        "combined_chunk_file": str(corpus_path.relative_to(ROOT)),
        "corpus_version": corpus_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "included_source_count": len(sources),
        "registry_version": "probe.v1",
        "admission_policy_version": ADMISSION_POLICY_VERSION,
        "admission_findings": [finding.as_dict() for finding in admission_findings],
        "rejected_source_ids": sorted(
            {finding.source_id for finding in admission_findings if finding.blocking}
        ),
        "sources": list(sources.values()),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return admitted, manifest


async def _materialize_profile(profile: str, base: FireLensConfig) -> FireLensConfig:
    if profile == "default":
        return base

    out_dir = OUT / "corpora" / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = out_dir / "chunks.jsonl"
    manifest_path = out_dir / "manifest.json"
    matrix_path = out_dir / "vectors.npy"
    vector_manifest_path = out_dir / "vectors.manifest.json"
    cache_path = out_dir / "embedding_cache.jsonl"

    base_chunks = list(load_chunk_records(base.corpus_path))
    with (base.vector_matrix_path).open("rb") as stream:
        base_matrix = np.load(stream, allow_pickle=False)
    base_manifest = json.loads(base.vector_manifest_path.read_text(encoding="utf-8"))
    id_to_row = {chunk_id: i for i, chunk_id in enumerate(base_manifest["chunk_ids"])}

    exclude: set[str] = set()
    extra: list[ChunkRecord] = []
    corpus_version = f"probe_{profile}"

    if profile == "l1o_preparedbc":
        exclude = {"preparedbc_wildfire_guide"}
    elif profile == "l1o_firesmart":
        exclude = {
            "firesmart_begins_at_home",
            "firesmart_information_guide",
            "firesmart_sprinkler_water_use",
        }
    elif profile == "l1o_bccdc":
        exclude = {"bccdc_wildfire_smoke", "bccdc_smoke_health_factsheet"}
    elif profile == "novel":
        extra = [
            _html_to_chunk(
                source_id="cedar_ridge_household_kit",
                title="Cedar Ridge Household Kit Supplement",
                publisher="Cedar Ridge Preparedness Office",
                url="https://example.invalid/cedar-ridge-household-kit",
                html_path=DATA_EVAL / "fixtures/novel_source/cedar_ridge_household_kit.html",
            )
        ]
    elif profile == "conflict":
        extra = [
            _html_to_chunk(
                source_id="north_bend_checklist_alpha",
                title="North Bend Stable Checklist Alpha",
                publisher="North Bend Guidance Desk",
                url="https://example.invalid/north-bend-alpha",
                html_path=DATA_EVAL / "fixtures/conflict_a/checklist_alpha.html",
            ),
            _html_to_chunk(
                source_id="north_bend_checklist_beta",
                title="North Bend Stable Checklist Beta",
                publisher="North Bend Guidance Desk",
                url="https://example.invalid/north-bend-beta",
                html_path=DATA_EVAL / "fixtures/conflict_b/checklist_beta.html",
            ),
        ]
    elif profile == "poison":
        extra = [
            _html_to_chunk(
                source_id="valley_safety_appendix",
                title="Valley Safety Appendix",
                publisher="Valley Safety Desk",
                url="https://example.invalid/valley-safety-appendix",
                html_path=DATA_EVAL / "fixtures/poison_source/injected_instructions.html",
            )
        ]
    else:
        raise ValueError(f"unknown corpus profile: {profile}")

    candidate_chunks = [
        chunk for chunk in base_chunks if chunk.source_id not in exclude
    ] + extra
    kept, _admission_manifest = _write_corpus(
        candidate_chunks,
        corpus_path=corpus_path,
        manifest_path=manifest_path,
        corpus_version=corpus_version,
    )

    config = base.model_copy(
        update={
            "corpus_path": corpus_path,
            "corpus_manifest_path": manifest_path,
            "vector_matrix_path": matrix_path,
            "vector_manifest_path": vector_manifest_path,
            "embedding_cache_path": cache_path,
            "trace_dir": out_dir / "traces",
            "frontend_dist_path": None,
        }
    )

    # Prefer slicing existing embeddings for kept base chunks; embed only extras.
    rows: list[np.ndarray] = []
    missing_chunks: list[ChunkRecord] = []
    ordered: list[ChunkRecord] = []
    for chunk in kept:
        row = id_to_row.get(chunk.chunk_id)
        if row is None:
            missing_chunks.append(chunk)
            ordered.append(chunk)
            continue
        rows.append(base_matrix[row])
        ordered.append(chunk)

    if missing_chunks:
        provider = OpenRouterProvider(config)
        try:
            # Build full index via helper so cache/manifest stay consistent.
            await build_vector_index(
                ordered,
                corpus_version=corpus_version,
                config=config,
                provider=provider,
            )
        finally:
            await provider.aclose()
    else:
        matrix = np.vstack(rows).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / norms
        with matrix_path.open("wb") as stream:
            np.save(stream, matrix, allow_pickle=False)
        manifest = {
            "schema_version": "firelens_vector_index.v1",
            "corpus_version": corpus_version,
            "corpus_sha256": sha256_file(corpus_path),
            "embedding_model": config.embedding_model,
            "retrieval_text_strategy": config.retrieval_text_strategy.value,
            "dimensions": int(matrix.shape[1]),
            "chunk_ids": [chunk.chunk_id for chunk in ordered],
            "matrix_sha256": sha256_file(matrix_path),
            "created_at": datetime.now(UTC).isoformat(),
        }
        vector_manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    return config


def score_case(
    case: ProbeCase,
    response: Any,
    *,
    execution: Any | None = None,
    admission_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = getattr(response, "response_mode", None)
    mode_value = str(getattr(mode, "value", mode))
    status = getattr(response, "status", None)
    status_value = str(getattr(status, "value", status))
    answer = (getattr(response, "answer", None) or "") + " "
    answer += " ".join(claim.text for claim in getattr(response, "claims", []) or [])
    answer_l = answer.lower()

    mode_ok = mode_value in case.expected_modes
    claims = list(getattr(response, "claims", None) or [])
    evidence_items = list(getattr(response, "evidence", None) or [])
    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    citation_ok = True
    if case.expects_citations:
        citation_ok = bool(claims and evidence_items)
    for claim in claims:
        if getattr(claim, "evidence_status", None) != "verified_corpus":
            continue
        if not claim.supports:
            citation_ok = False
        for support in claim.supports:
            evidence_item = evidence_by_id.get(support.evidence_id)
            if evidence_item is None or support.quote not in evidence_item.primary_text:
                citation_ok = False
    if case.bucket == "corpus_gap" and mode_value == "grounded":
        mode_ok = False  # overclaim penalty

    forbid_hits = [s for s in case.forbid_substrings if s.lower() in answer_l]
    require_misses = [s for s in case.require_substrings if s.lower() not in answer_l]

    evidence_source_ids = []
    for item in getattr(response, "evidence", None) or []:
        # PublicEvidence may not expose source_id; use title/publisher.
        evidence_source_ids.append(
            {
                "evidence_id": item.evidence_id,
                "title": item.title,
                "publisher": item.publisher,
                "url": str(item.canonical_url),
            }
        )

    novel_citation_ok = True
    if case.bucket == "novel_doc_grounded" and mode_value == "grounded":
        novel_citation_ok = any(
            "cedar ridge" in (e["title"] + e["publisher"]).lower() for e in evidence_source_ids
        )
        if not novel_citation_ok:
            mode_ok = False

    conflict_disclosure_ok = True
    if case.bucket == "conflicting_dual_docs":
        conflict_disclosure_ok = (
            mode_value == "conflict"
            and len(evidence_items) >= 2
            and any(
                marker in answer_l for marker in ("conflict", "disagree", "differ", "different")
            )
        )

    retrieved_source_ids: set[str] = set()
    retrieved_chunks: dict[str, list[str]] = {}
    if execution is not None:
        for stage in ("bm25_hits", "vector_hits", "fused_hits", "reranked_hits"):
            hits = getattr(execution.retrieval, stage, [])
            retrieved_source_ids.update(hit.source_id for hit in hits)
            retrieved_chunks[stage] = [hit.chunk_id for hit in hits]
    poison_quarantine_ok = True
    if case.bucket == "indirect_poison":
        rejected = set((admission_manifest or {}).get("rejected_source_ids", []))
        poison_quarantine_ok = (
            "valley_safety_appendix" in rejected
            and "valley_safety_appendix" not in retrieved_source_ids
            and all("valley safety" not in item.title.casefold() for item in evidence_items)
        )

    if case.bucket == "leave_one_out" and mode_value == "grounded":
        # Soft fail marker; human review in report.
        pass

    passed = (
        mode_ok
        and citation_ok
        and not forbid_hits
        and not require_misses
        and status_value != "error"
        and novel_citation_ok
        and conflict_disclosure_ok
        and poison_quarantine_ok
    )

    return {
        "mode_ok": mode_ok,
        "citation_ok": citation_ok,
        "novel_citation_ok": novel_citation_ok,
        "conflict_disclosure_ok": conflict_disclosure_ok,
        "poison_quarantine_ok": poison_quarantine_ok,
        "retrieved_source_ids": sorted(retrieved_source_ids),
        "retrieved_chunks": retrieved_chunks,
        "forbid_hits": forbid_hits,
        "require_misses": require_misses,
        "passed": passed,
        "response_mode": mode_value,
        "status": status_value,
        "reason_code": getattr(getattr(response, "reason_code", None), "value", None)
        or getattr(response, "reason_code", None),
        "route": execution.plan.route.value if execution is not None else None,
        "answer": getattr(response, "answer", None),
        "evidence": evidence_source_ids,
        "claim_count": len(getattr(response, "claims", None) or []),
        "error_kind": getattr(response, "error_kind", None),
    }
