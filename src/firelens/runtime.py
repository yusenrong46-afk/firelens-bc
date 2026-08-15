"""Load and validate corpus/index resources, then assemble the application service."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from firelens.answering.service import StaticRAGService
from firelens.config import FireLensConfig
from firelens.contracts import HealthResponse
from firelens.corpus_admission import audit_corpus_admission, blocking_findings
from firelens.errors import CorpusValidationError, IndexValidationError
from firelens.ingestion.chunking import ChunkRecord
from firelens.ingestion.pdf import IngestionError
from firelens.ingestion.repairs import load_text_repairs, validate_chunk_repair_provenance
from firelens.providers.base import AIProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.retrieval.vector import VectorIndex
from firelens.runtime_artifact_common import (
    CANDIDATE_RELATIVE_PATH,
    canonical_json,
    sha256_bytes,
)
from firelens.runtime_candidate import (
    apply_runtime_candidate_binding,
    load_runtime_candidate_document,
)


@dataclass
class Runtime:
    config: FireLensConfig
    chunks: tuple[ChunkRecord, ...] = ()
    corpus_version: str | None = None
    service: StaticRAGService | None = None
    problems: list[str] = field(default_factory=list)
    provider_configured: bool = False
    provider: AIProvider | None = None
    zdr_policy_state: Literal["disabled", "required_unprobed", "eligible", "failed"] = (
        "disabled"
    )
    bound_candidate: dict[str, str] | None = None
    candidate_binding_applied: bool = False

    def __post_init__(self) -> None:
        if self.config.require_zdr and self.zdr_policy_state == "disabled":
            self.zdr_policy_state = "required_unprobed"

    @property
    def chunks_by_id(self) -> dict[str, ChunkRecord]:
        return {chunk.chunk_id: chunk for chunk in self.chunks}

    def health(self) -> HealthResponse:
        corpus_ready = bool(self.chunks and self.corpus_version)
        index_ready = self.service is not None
        production_zdr_ready = (
            self.config.deployment_environment != "production"
            or self.zdr_policy_state == "eligible"
        )
        ready = (
            corpus_ready and index_ready and self.provider_configured and production_zdr_ready
        )
        provider_state: Literal[
            "not_configured",
            "configured_unprobed",
            "available",
            "degraded",
            "circuit_open",
        ] = "not_configured"
        if self.provider_configured:
            provider_state = "configured_unprobed"
            state_reader = getattr(self.provider, "operational_state", None)
            if callable(state_reader):
                observed_state = state_reader()
                if observed_state in {
                    "configured_unprobed",
                    "available",
                    "degraded",
                    "circuit_open",
                }:
                    provider_state = observed_state
        candidate = self.bound_candidate
        return HealthResponse(
            status="ready" if ready else "not_ready",
            corpus_ready=corpus_ready,
            index_ready=index_ready,
            provider_configured=self.provider_configured,
            zdr_required=self.config.require_zdr,
            zdr_policy_state=self.zdr_policy_state,
            provider_state=provider_state,
            corpus_version=self.corpus_version,
            chunk_count=len(self.chunks) if self.chunks else None,
            release_version=self.config.release_version,
            build_commit=self.config.build_commit,
            deployment_id=self.config.deployment_id,
            candidate_id=None if candidate is None else candidate["candidate_id"],
            candidate_sha256=(
                None if candidate is None else sha256_bytes(canonical_json(candidate))
            ),
            embedding_model=self.config.embedding_model,
            rerank_model=self.config.rerank_model,
            generation_model=self.config.generation_model,
            retrieval_text_strategy=self.config.retrieval_text_strategy.value,
            problems=self.problems,
        )

    def apply_bound_candidate(self) -> list[str]:
        """Bind once after validation. A raised production failure stays fail-closed."""

        if self.candidate_binding_applied:
            return []
        problems = apply_runtime_candidate_binding(
            self.config, corpus_version=self.corpus_version
        )
        if not problems:
            path = self.config.project_root / CANDIDATE_RELATIVE_PATH
            if path.is_file():
                self.bound_candidate = load_runtime_candidate_document(path)
        self.candidate_binding_applied = True
        return problems

    async def aclose(self) -> None:
        close = getattr(self.provider, "aclose", None)
        if close is not None:
            await close()


def load_corpus_resources(
    config: FireLensConfig,
) -> tuple[tuple[ChunkRecord, ...], str]:
    if not config.corpus_path.is_file() or not config.corpus_manifest_path.is_file():
        raise CorpusValidationError("Static corpus or manifest is missing.")
    manifest = _load_corpus_manifest(config.corpus_manifest_path)
    chunks = tuple(load_chunk_records(config.corpus_path))
    corpus_version = _validate_corpus_manifest(manifest, chunks)
    _validate_corpus_repairs(config, chunks)
    _validate_corpus_admission(chunks)
    return chunks, corpus_version


def _load_corpus_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusValidationError("Static corpus manifest is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise CorpusValidationError("Static corpus manifest must be an object.")
    return payload


def _validate_corpus_manifest(manifest: dict[str, Any], chunks: tuple[ChunkRecord, ...]) -> str:
    corpus_version = manifest.get("corpus_version")
    if not isinstance(corpus_version, str) or not corpus_version:
        raise CorpusValidationError("Static corpus manifest has no version.")
    if manifest.get("combined_chunk_count") != len(chunks):
        raise CorpusValidationError("Static corpus count does not match manifest.")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise CorpusValidationError("Static corpus contains duplicate chunk IDs.")
    if any(chunk.temporal_class != "stable_guidance" for chunk in chunks):
        raise CorpusValidationError("Static corpus contains non-static evidence.")
    included = [
        source
        for source in manifest.get("sources", [])
        if source.get("corpus_action") == "include"
    ]
    if not included or any(
        source.get("review_status") != "approved_static" for source in included
    ):
        raise CorpusValidationError("Static corpus includes an unapproved source.")
    if manifest.get("included_source_count") != len(included):
        raise CorpusValidationError("Static source count does not match manifest.")
    approved_source_ids = {source.get("source_id") for source in included}
    if any(chunk.source_id not in approved_source_ids for chunk in chunks):
        raise CorpusValidationError("Static corpus contains an unapproved source.")
    if manifest.get("repair_provenance_policy") != "human_verified_only.v1":
        raise CorpusValidationError("Static corpus repair provenance policy is missing.")
    return corpus_version


def _validate_corpus_repairs(config: FireLensConfig, chunks: tuple[ChunkRecord, ...]) -> None:
    try:
        repairs = load_text_repairs(config.project_root / "data/repairs/text_overrides.yaml")
        validate_chunk_repair_provenance(chunks, repairs)
    except (IngestionError, OSError, ValueError) as exc:
        raise CorpusValidationError(str(exc)) from exc


def _validate_corpus_admission(chunks: tuple[ChunkRecord, ...]) -> None:
    admission_findings = blocking_findings(audit_corpus_admission(chunks))
    if admission_findings:
        first = admission_findings[0]
        raise CorpusValidationError(
            "Static corpus failed deterministic admission: "
            f"{first.source_id}/{first.chunk_id or 'source'} ({first.code})."
        )


def load_runtime(
    config: FireLensConfig,
    *,
    provider: AIProvider | None = None,
) -> Runtime:
    runtime = Runtime(
        config=config,
        provider_configured=provider is not None or config.openrouter_api_key is not None,
        zdr_policy_state="required_unprobed" if config.require_zdr else "disabled",
    )
    try:
        chunks, corpus_version = load_corpus_resources(config)
        runtime.chunks = chunks
        runtime.corpus_version = corpus_version
    except (CorpusValidationError, OSError, ValueError) as exc:
        runtime.problems.append(str(exc))
        runtime.problems.extend(runtime.apply_bound_candidate())
        return runtime

    try:
        vector_index = VectorIndex.load(
            chunks,
            matrix_path=config.vector_matrix_path,
            manifest_path=config.vector_manifest_path,
            corpus_path=config.corpus_path,
            corpus_version=corpus_version,
            embedding_model=config.embedding_model,
            retrieval_text_strategy=config.retrieval_text_strategy,
        )
    except IndexValidationError as exc:
        runtime.problems.append(str(exc))
        runtime.problems.extend(runtime.apply_bound_candidate())
        return runtime

    active_provider = provider or OpenRouterProvider(config)
    runtime.provider = active_provider
    retrieval = RetrievalPipeline(
        chunks,
        vector_index=vector_index,
        provider=active_provider,
        config=config,
    )
    runtime.service = StaticRAGService(
        chunks,
        corpus_version=corpus_version,
        retrieval=retrieval,
        provider=active_provider,
        config=config,
    )
    runtime.problems.extend(runtime.apply_bound_candidate())
    return runtime
