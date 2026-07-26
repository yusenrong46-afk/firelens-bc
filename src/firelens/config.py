"""Explicit, environment-backed configuration for the FireLens static RAG."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr


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


class FireLensConfig(BaseModel):
    """Versioned experimental defaults for the first complete static pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_root: Path
    corpus_path: Path
    corpus_manifest_path: Path
    vector_matrix_path: Path
    vector_manifest_path: Path
    embedding_cache_path: Path
    trace_dir: Path
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-small"
    rerank_model: str = "cohere/rerank-4-pro"
    generation_model: str = "google/gemini-3.5-flash-lite"
    bm25_top_k: int = Field(default=20, gt=0)
    vector_top_k: int = Field(default=20, gt=0)
    fused_top_k: int = Field(default=20, gt=0)
    rerank_top_k: int = Field(default=5, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    neighbor_window: int = Field(default=1, ge=0)
    max_evidence_spans: int = Field(default=5, gt=0)
    max_context_chars: int = Field(default=8_000, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_batch_size: int = Field(default=64, gt=0)
    require_zdr: bool = False
    debug: bool = False
    trace_content: bool = False

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "FireLensConfig":
        root = (project_root or Path.cwd()).resolve()
        file_values = _read_dotenv(root / ".env")

        def setting(name: str) -> str | None:
            return os.environ.get(name, file_values.get(name))

        key = setting("OPENROUTER_API_KEY")
        return cls(
            project_root=root,
            corpus_path=root / "data/processed/firelens_static_corpus.chunks.jsonl",
            corpus_manifest_path=(
                root / "data/processed/firelens_static_corpus.manifest.json"
            ),
            vector_matrix_path=root / "data/index/firelens_vectors.npy",
            vector_manifest_path=root / "data/index/firelens_vectors.manifest.json",
            embedding_cache_path=root / "data/index/embedding_cache.jsonl",
            trace_dir=root / "output/traces",
            openrouter_api_key=SecretStr(key) if key else None,
            require_zdr=_bool_value(setting("FIRELENS_REQUIRE_ZDR")),
            debug=_bool_value(setting("FIRELENS_DEBUG")),
            trace_content=_bool_value(setting("FIRELENS_TRACE_CONTENT")),
        )
