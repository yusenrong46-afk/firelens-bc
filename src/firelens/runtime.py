"""Load and validate corpus/index resources, then assemble the application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from firelens.answering.service import StaticRAGService
from firelens.config import FireLensConfig
from firelens.contracts import HealthResponse
from firelens.corpus_admission import (
    ADMISSION_POLICY_VERSION,
    audit_corpus_admission,
    blocking_findings,
)
from firelens.errors import CorpusValidationError, IndexValidationError
from firelens.ingestion.chunking import ChunkRecord
from firelens.ingestion.pdf import IngestionError
from firelens.ingestion.repairs import load_text_repairs, validate_chunk_repair_provenance
from firelens.privacy_policy import (
    ZdrPolicyState,
    ZdrPreflightReport,
    health_stage_state,
    initial_zdr_policy_state,
)
from firelens.providers.base import AIProvider
from firelens.providers.openrouter import OpenRouterProvider
from firelens.retrieval.bm25 import load_chunk_records
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.retrieval.vector import VectorIndex
from firelens.runtime_artifact_common import (
    CANDIDATE_RELATIVE_PATH,
    RuntimeArtifactError,
    canonical_json,
    read_json,
    sha256_bytes,
    strict_json_loads,
    strict_yaml_load,
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
    zdr_policy_state: ZdrPolicyState = "disabled"
    embedding_zdr_state: Literal[
        "not_required", "unprobed", "eligible", "zdr_optional", "failed"
    ] = "not_required"
    generation_zdr_state: Literal[
        "not_required", "unprobed", "eligible", "zdr_optional", "failed"
    ] = "not_required"
    reranking_zdr_state: Literal[
        "not_required", "unprobed", "eligible", "zdr_optional", "failed"
    ] = "not_required"
    bound_candidate: dict[str, str] | None = None
    candidate_binding_applied: bool = False
    provider_preflight_succeeded: bool = False

    def __post_init__(self) -> None:
        if self.config.privacy.any_zdr_required and self.zdr_policy_state == "disabled":
            self.zdr_policy_state = "stage_bound_unprobed"
        if self.zdr_policy_state == "stage_bound_unprobed":
            self.embedding_zdr_state = "unprobed"
            self.generation_zdr_state = "unprobed"
            self.reranking_zdr_state = "unprobed"

    def apply_zdr_preflight(
        self,
        report: ZdrPreflightReport | None,
        *,
        failed: bool,
    ) -> None:
        self.provider_preflight_succeeded = report is not None and not failed
        self.zdr_policy_state = "failed" if failed else "required_stages_eligible"
        if report is None:
            self.embedding_zdr_state = (
                "failed" if self.config.privacy.embedding_zdr == "required" else "not_required"
            )
            self.generation_zdr_state = (
                "failed" if self.config.privacy.generation_zdr == "required" else "not_required"
            )
            self.reranking_zdr_state = (
                "failed"
                if self.config.privacy.reranking_zdr == "required"
                else ("unprobed" if self.config.privacy.any_zdr_required else "not_required")
            )
            return
        self.embedding_zdr_state = health_stage_state(
            self.config.privacy.embedding_zdr, report.embedding, probed=True
        )
        self.generation_zdr_state = health_stage_state(
            self.config.privacy.generation_zdr, report.generation, probed=True
        )
        self.reranking_zdr_state = health_stage_state(
            self.config.privacy.reranking_zdr, report.reranking, probed=True
        )

    @property
    def chunks_by_id(self) -> dict[str, ChunkRecord]:
        return {chunk.chunk_id: chunk for chunk in self.chunks}

    def health(self) -> HealthResponse:
        corpus_ready = bool(self.chunks and self.corpus_version)
        index_ready = self.service is not None
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
            if (
                provider_state == "configured_unprobed"
                and self.config.deployment_environment == "production"
                and self.provider_preflight_succeeded
            ):
                # The authenticated GET /endpoints/zdr startup preflight is a
                # successful, content-free provider observation. It does not
                # invoke a model or incur generation cost.
                provider_state = "available"
        production_zdr_ready = (
            self.config.deployment_environment != "production"
            or self.zdr_policy_state == "required_stages_eligible"
        )
        production_provider_ready = (
            self.config.deployment_environment != "production" or provider_state == "available"
        )
        ready = (
            corpus_ready
            and index_ready
            and self.provider_configured
            and production_zdr_ready
            and production_provider_ready
        )
        candidate = self.bound_candidate
        return HealthResponse(
            status="ready" if ready else "not_ready",
            corpus_ready=corpus_ready,
            index_ready=index_ready,
            provider_configured=self.provider_configured,
            zdr_required=self.config.privacy.any_zdr_required,
            zdr_policy_state=self.zdr_policy_state,
            data_collection=self.config.privacy.data_collection,
            allow_fallbacks=self.config.privacy.allow_fallbacks,
            embedding_zdr=self.config.privacy.embedding_zdr,
            reranking_zdr=self.config.privacy.reranking_zdr,
            generation_zdr=self.config.privacy.generation_zdr,
            embedding_zdr_state=self.embedding_zdr_state,
            generation_zdr_state=self.generation_zdr_state,
            reranking_zdr_state=self.reranking_zdr_state,
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
    _validate_governed_corpus_json(config.corpus_path)
    chunks = tuple(load_chunk_records(config.corpus_path))
    corpus_version = _validate_corpus_manifest(manifest, chunks)
    _validate_corpus_repairs(config, chunks, manifest)
    _validate_corpus_admission(chunks, manifest)
    return chunks, corpus_version


def _load_corpus_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = read_json(path, context="static corpus manifest")
    except RuntimeArtifactError as exc:
        raise CorpusValidationError("Static corpus manifest is invalid JSON.") from exc
    return payload


def _validate_governed_corpus_json(path: Path) -> None:
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if line.strip():
                    strict_json_loads(line, context=f"static corpus line {line_number}")
    except (OSError, UnicodeDecodeError, RuntimeArtifactError) as exc:
        raise CorpusValidationError(
            "Static corpus contains invalid or ambiguous JSON."
        ) from exc


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
        if source.get("corpus_action") in {"include", "include_quote_only"}
    ]
    if not included or any(
        source.get("review_status") not in {"approved_static", "approved_quote_only"}
        for source in included
    ):
        raise CorpusValidationError("Static corpus includes an unapproved source.")
    if manifest.get("included_source_count") != len(included):
        raise CorpusValidationError("Static source count does not match manifest.")
    approved_source_ids = {source.get("source_id") for source in included}
    if any(chunk.source_id not in approved_source_ids for chunk in chunks):
        raise CorpusValidationError("Static corpus contains an unapproved source.")
    if manifest.get("repair_provenance_policy") != "human_verified_only.v1":
        raise CorpusValidationError("Static corpus repair provenance policy is missing.")
    admission_policy = manifest.get("admission_policy_version")
    if admission_policy is not None and admission_policy != ADMISSION_POLICY_VERSION:
        raise CorpusValidationError("Static corpus admission policy is unsupported.")
    warnings = manifest.get("admission_warnings")
    if warnings is not None and (
        not isinstance(warnings, list) or any(not isinstance(item, dict) for item in warnings)
    ):
        raise CorpusValidationError("Static corpus admission warnings are malformed.")
    warning_fields = {"source_id", "chunk_id", "code", "detail", "blocking"}
    if any(
        set(item) != warning_fields
        or not isinstance(item["source_id"], str)
        or not isinstance(item["code"], str)
        or not isinstance(item["detail"], str)
        or (item["chunk_id"] is not None and not isinstance(item["chunk_id"], str))
        or item["blocking"] is not False
        for item in (warnings or [])
    ):
        raise CorpusValidationError("Static corpus admission warnings are invalid.")
    quarantined = manifest.get("quarantined_pages")
    if quarantined is not None and (
        not isinstance(quarantined, list)
        or any(not isinstance(item, dict) for item in quarantined)
    ):
        raise CorpusValidationError("Static corpus quarantined-page records are malformed.")
    quarantine_fields = {
        "source_id",
        "page_number",
        "document_sha256",
        "review_status",
        "reason",
    }
    if any(
        set(item) != quarantine_fields
        or not isinstance(item["source_id"], str)
        or isinstance(item["page_number"], bool)
        or not isinstance(item["page_number"], int)
        or not isinstance(item["document_sha256"], str)
        or not isinstance(item["review_status"], str)
        or not isinstance(item["reason"], str)
        for item in (quarantined or [])
    ):
        raise CorpusValidationError("Static corpus quarantined-page records are invalid.")
    return corpus_version


def _validate_corpus_repairs(
    config: FireLensConfig,
    chunks: tuple[ChunkRecord, ...],
    manifest: dict[str, Any],
) -> None:
    try:
        path = config.project_root / "data/repairs/text_overrides.yaml"
        strict_yaml_load(path.read_text(encoding="utf-8"), context="text repair registry")
        repairs = load_text_repairs(path)
        validate_chunk_repair_provenance(chunks, repairs)
        expected_quarantine = {
            (
                str(repair["source_id"]),
                int(repair["page_number"]),
                str(repair["document_sha256"]),
                str(repair["review_status"]),
                str(repair["reason"]),
            )
            for repair in repairs
            if repair["review_status"] != "human_verified"
        }
        if len(expected_quarantine) != sum(
            repair["review_status"] != "human_verified" for repair in repairs
        ):
            raise CorpusValidationError(
                "Text repair registry has duplicate quarantine targets."
            )
        recorded_rows = manifest.get("quarantined_pages", [])
        recorded_quarantine = {
            (
                str(item.get("source_id")),
                item.get("page_number"),
                str(item.get("document_sha256")),
                str(item.get("review_status")),
                str(item.get("reason")),
            )
            for item in recorded_rows
        }
        if len(recorded_quarantine) != len(recorded_rows):
            raise CorpusValidationError("Static corpus has duplicate quarantined-page records.")
        if recorded_quarantine != expected_quarantine:
            raise CorpusValidationError(
                "Static corpus quarantined-page records differ from the repair registry."
            )
    except (IngestionError, OSError, UnicodeDecodeError, ValueError) as exc:
        raise CorpusValidationError(str(exc)) from exc


def _validate_corpus_admission(
    chunks: tuple[ChunkRecord, ...], manifest: dict[str, Any]
) -> None:
    all_findings = audit_corpus_admission(chunks)
    expected_warnings = [finding.as_dict() for finding in all_findings if not finding.blocking]
    actual_warnings = manifest.get("admission_warnings")
    if actual_warnings is not None and actual_warnings != expected_warnings:
        raise CorpusValidationError(
            "Static corpus admission warnings differ from the admitted corpus."
        )
    admission_findings = blocking_findings(all_findings)
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
        zdr_policy_state=initial_zdr_policy_state(config.privacy),
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
