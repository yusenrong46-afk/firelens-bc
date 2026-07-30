"""Explicit, environment-backed configuration for the FireLens static RAG."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from firelens.contracts import RetrievalTextStrategy


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read a small dotenv file without adding another runtime dependency."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _bool_value(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_value(value: str | None, default: int) -> int:
    return int(value) if value is not None else default


class FireLensConfig(BaseModel):
    """Versioned experimental defaults for the first complete static pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_root: Path
    corpus_path: Path
    corpus_manifest_path: Path
    vector_matrix_path: Path
    vector_manifest_path: Path
    embedding_cache_path: Path
    document_context_path: Path
    trace_dir: Path
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-small"
    retrieval_text_strategy: RetrievalTextStrategy = RetrievalTextStrategy.METADATA_CONTEXT_V1
    rerank_model: str = "cohere/rerank-4-pro"
    generation_model: str = "google/gemini-3.5-flash-lite"
    generation_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    bm25_top_k: int = Field(default=30, gt=0)
    vector_top_k: int = Field(default=30, gt=0)
    fused_top_k: int = Field(default=30, gt=0)
    rerank_top_k: int = Field(default=5, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    neighbor_window: int = Field(default=1, ge=0)
    max_evidence_spans: int = Field(default=5, gt=0)
    max_context_chars: int = Field(default=8_000, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    provider_max_attempts: int = Field(default=3, ge=1, le=3)
    provider_retry_base_seconds: float = Field(default=0.25, ge=0)
    provider_max_concurrency: int = Field(default=4, ge=1, le=16)
    embedding_batch_size: int = Field(default=64, gt=0)
    query_embedding_cache_size: int = Field(default=256, ge=0, le=4_096)
    trace_max_files: int = Field(default=250, ge=1)
    trace_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    anonymous_rate_limit: int = Field(default=30, ge=1, le=1_000)
    anonymous_rate_window_seconds: int = Field(default=60, ge=1, le=3_600)
    max_request_body_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    release_version: str = "1.5.0-rc.1"
    build_commit: str | None = None
    deployment_id: str | None = None
    frontend_dist_path: Path | None = None
    require_zdr: bool = False
    debug: bool = False
    trace_content: bool = False
    deployment_environment: Literal["local", "preview", "production"] = "local"
    trusted_proxy_platform: Literal["none", "vercel"] = "none"

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> FireLensConfig:
        root = (project_root or Path.cwd()).resolve()
        file_values = _read_dotenv(root / ".env")

        def setting(name: str) -> str | None:
            return os.environ.get(name, file_values.get(name))

        key = setting("OPENROUTER_API_KEY")
        frontend_dist = root / "prototype/firelens-rag-ui/dist/client"
        configured_trace_dir = setting("FIRELENS_TRACE_DIR")
        configured_document_context = setting("FIRELENS_DOCUMENT_CONTEXT_PATH")
        environment_setting = setting("FIRELENS_ENVIRONMENT") or setting("VERCEL_ENV")
        configured_environment: Literal["local", "preview", "production"]
        if environment_setting == "preview":
            configured_environment = "preview"
        elif environment_setting == "production" or setting("RENDER"):
            configured_environment = "production"
        else:
            configured_environment = "local"
        return cls(
            project_root=root,
            corpus_path=root / "data/processed/firelens_static_corpus.chunks.jsonl",
            corpus_manifest_path=(root / "data/processed/firelens_static_corpus.manifest.json"),
            vector_matrix_path=root / "data/index/firelens_vectors.npy",
            vector_manifest_path=root / "data/index/firelens_vectors.manifest.json",
            embedding_cache_path=root / "data/index/embedding_cache.jsonl",
            document_context_path=(
                Path(configured_document_context).expanduser().resolve()
                if configured_document_context
                else root / "data/index/document_context_v2.jsonl"
            ),
            trace_dir=(
                Path(configured_trace_dir).expanduser().resolve()
                if configured_trace_dir
                else Path("/tmp/firelens-traces")
                if setting("VERCEL")
                else root / "output/traces"
            ),
            frontend_dist_path=frontend_dist,
            openrouter_api_key=SecretStr(key) if key else None,
            retrieval_text_strategy=RetrievalTextStrategy(
                setting("FIRELENS_RETRIEVAL_TEXT_STRATEGY")
                or RetrievalTextStrategy.METADATA_CONTEXT_V1
            ),
            require_zdr=_bool_value(setting("FIRELENS_REQUIRE_ZDR")),
            debug=_bool_value(setting("FIRELENS_DEBUG")),
            trace_content=_bool_value(setting("FIRELENS_TRACE_CONTENT")),
            anonymous_rate_limit=_int_value(setting("FIRELENS_RATE_LIMIT"), 30),
            anonymous_rate_window_seconds=_int_value(
                setting("FIRELENS_RATE_WINDOW_SECONDS"), 60
            ),
            max_request_body_bytes=_int_value(
                setting("FIRELENS_MAX_REQUEST_BODY_BYTES"), 65_536
            ),
            release_version=setting("FIRELENS_RELEASE_VERSION") or "1.5.0-rc.1",
            build_commit=setting("VERCEL_GIT_COMMIT_SHA") or setting("FIRELENS_BUILD_COMMIT"),
            deployment_id=setting("VERCEL_DEPLOYMENT_ID") or setting("VERCEL_URL"),
            deployment_environment=configured_environment,
            trusted_proxy_platform="vercel" if setting("VERCEL") else "none",
        )
