"""Internal V1.6.0 release-promotion binding. Not a deployment or GO claim."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, get_args

from firelens.contracts import ClaimSupport, EvidenceStatus, PublicClaim, ResponseMode
from firelens.evaluation.candidate_evidence_common import file_record
from firelens.evaluation.candidate_evidence_validation import nonempty_string
from firelens.evaluation.common import file_sha256
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE
from firelens.proof_contracts import ProofCard, SupportState
from firelens.publication_contracts import PublicationKind

SCHEMA_VERSION = "firelens.v1_6_release_promotion.v1"
MANIFEST_RELATIVE = "config/firelens.v1_6_release_promotion.v1.json"
FROM_VERSION = "1.6.0-rc.1"
TO_VERSION = "1.6.0"
FROZEN_STANDARD_RELEASE_TARGET = "1.6.0-rc.1"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def normalize_release_version(value: str, *, label: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} is invalid")
    normalized = re.sub(r"(?<=\d)[.-]?rc[.-]?(?=\d)", "rc", value.casefold())
    if re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+)?", normalized) is None:
        raise ValueError(f"{label} is invalid")
    return normalized


ALLOWED_PROMOTION_PATHS: tuple[str, ...] = (
    MANIFEST_RELATIVE,
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "src/firelens/config.py",
    "Dockerfile",
    "render.yaml",
    "docs/openapi.v1.json",
    "apps/web/src/shared/api/api-schema.d.ts",
    ".github/workflows/candidate.yml",
    "README.md",
    "docs/ARCHITECTURE_V1_6.md",
    "docs/releases/V1_6_RUNBOOK.md",
    "CHANGELOG.md",
    "tests/test_documentation_consistency.py",
    "tests/test_runtime_candidate_build.py",
    "tests/test_candidate_evidence.py",
)

PUBLIC_CLAIM_FIELDS: tuple[str, ...] = tuple(sorted(PublicClaim.model_fields))
CLAIM_SUPPORT_FIELDS: tuple[str, ...] = tuple(sorted(ClaimSupport.model_fields))
PROOF_CARD_FIELDS: tuple[str, ...] = tuple(sorted(ProofCard.model_fields))
EVIDENCE_STATUS_VALUES: tuple[str, ...] = tuple(sorted(item.value for item in EvidenceStatus))
RESPONSE_MODE_VALUES: tuple[str, ...] = tuple(sorted(item.value for item in ResponseMode))
PUBLICATION_KIND_VALUES: tuple[str, ...] = tuple(sorted(item.value for item in PublicationKind))
SUPPORT_STATE_VALUES: tuple[str, ...] = tuple(sorted(get_args(SupportState)))


def promotion_manifest_document(
    *,
    frozen_standard_sha256: str,
    functional_parent_commit: str,
    functional_parent_tree: str,
) -> dict[str, Any]:
    surface = public_contract_surface()
    return {
        "schema_version": SCHEMA_VERSION,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "frozen_standard_path": STANDARD_RELATIVE,
        "frozen_standard_sha256": frozen_standard_sha256,
        "functional_parent_commit": functional_parent_commit,
        "functional_parent_tree": functional_parent_tree,
        "allowed_paths": list(ALLOWED_PROMOTION_PATHS),
        "public_claim_fields": list(surface["public_claim_fields"]),
        "claim_support_fields": list(surface["claim_support_fields"]),
        "proof_card_fields": list(surface["proof_card_fields"]),
        "evidence_status_values": list(surface["evidence_status_values"]),
        "response_mode_values": list(surface["response_mode_values"]),
        "publication_kind_values": list(surface["publication_kind_values"]),
        "support_state_values": list(surface["support_state_values"]),
    }


def load_promotion_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("release-promotion manifest is missing or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("release-promotion manifest must be an object")
    return payload


def public_contract_surface() -> dict[str, tuple[str, ...]]:
    return {
        "public_claim_fields": PUBLIC_CLAIM_FIELDS,
        "claim_support_fields": CLAIM_SUPPORT_FIELDS,
        "proof_card_fields": PROOF_CARD_FIELDS,
        "evidence_status_values": EVIDENCE_STATUS_VALUES,
        "response_mode_values": RESPONSE_MODE_VALUES,
        "publication_kind_values": PUBLICATION_KIND_VALUES,
        "support_state_values": SUPPORT_STATE_VALUES,
    }


def version_surfaces(root: Path) -> dict[str, str]:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    package = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    config = (root / "src/firelens/config.py").read_text(encoding="utf-8")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    render = (root / "render.yaml").read_text(encoding="utf-8")
    openapi = json.loads((root / "docs/openapi.v1.json").read_text(encoding="utf-8"))
    workflow = (root / ".github/workflows/candidate.yml").read_text(encoding="utf-8")
    python_match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    config_match = re.search(
        r'DEFAULT_RELEASE_VERSION = "([^"]+)"',
        config,
    )
    docker_match = re.search(r"ARG FIRELENS_RELEASE_VERSION=(\S+)", dockerfile)
    render_match = re.search(r'key: FIRELENS_RELEASE_VERSION\n\s+value: "([^"]+)"', render)
    workflow_versions = {
        token.strip("\",'") for token in re.findall(r"--release-version ([^\s\\]+)", workflow)
    }
    if (
        python_match is None
        or config_match is None
        or docker_match is None
        or render_match is None
    ):
        raise ValueError("release version surfaces cannot be read")
    if len(workflow_versions) != 1:
        raise ValueError("candidate workflow must declare exactly one release version")
    info = openapi.get("info") if isinstance(openapi, dict) else None
    openapi_version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(openapi_version, str):
        raise ValueError("OpenAPI version is missing")
    package_version = package.get("version") if isinstance(package, dict) else None
    lock_version = lock.get("version") if isinstance(lock, dict) else None
    if not isinstance(package_version, str) or not isinstance(lock_version, str):
        raise ValueError("web package versions are missing")
    return {
        "pyproject": python_match.group(1),
        "web_package": package_version,
        "web_lock": lock_version,
        "config_default": config_match.group(1),
        "dockerfile": docker_match.group(1),
        "render": render_match.group(1),
        "openapi": openapi_version,
        "workflow": next(iter(workflow_versions)),
    }


def _require_git(root: Path) -> bool:
    return (root / ".git").exists() or (root / ".git").is_file()


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return env


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "-c", "core.commitGraph=false", *args],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if completed.returncode != 0:
        raise ValueError(f"release-promotion git command failed: git {' '.join(args)}")
    return completed.stdout.strip()


def bind_functional_parent(
    root: Path, *, parent_commit: str, parent_tree: str, commit: str
) -> None:
    """Require the recorded functional parent to precede this commit in Git.

    After a merge to main, first-parent HEAD^ is the previous main tip, not the
    promotion parent. Ancestry plus an exact parent-tree match is the
    merge-safe identity check. It does not relax the allowlisted tree diff.

    Reachability uses ``rev-list``, not ``merge-base --is-ancestor``. Git 2.55.0
    on GitHub-hosted ubuntu-24.04 can false-negative merge-base through the
    commit-graph; inherited GIT_DIR/GIT_WORK_TREE can also point at a decoy.
    """

    if COMMIT_RE.fullmatch(parent_commit) is None or COMMIT_RE.fullmatch(parent_tree) is None:
        raise ValueError("functional parent identities must be full lowercase Git SHAs")
    observed_parent_tree = _git(root, "rev-parse", f"{parent_commit}^{{tree}}")
    if observed_parent_tree != parent_tree:
        raise ValueError("functional parent tree does not match the promotion manifest")
    if _git(root, "rev-list", "--max-count=1", parent_commit, "--not", commit):
        raise ValueError("functional parent does not precede the promotion commit")


def unique_promotion_commit(root: Path, *, parent_commit: str, commit: str) -> str:
    """Return the unique descendant whose first parent is the functional parent."""

    listing = _git(root, "rev-list", "--parents", f"{parent_commit}..{commit}")
    matches: list[str] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == parent_commit:
            matches.append(parts[0])
    if len(matches) != 1:
        raise ValueError("functional parent does not precede a unique promotion commit")
    return matches[0]


def validate_release_promotion(
    root: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
) -> dict[str, Any]:
    manifest = load_promotion_manifest(root)
    required = {
        "schema_version",
        "from_version",
        "to_version",
        "frozen_standard_path",
        "frozen_standard_sha256",
        "functional_parent_commit",
        "functional_parent_tree",
        "allowed_paths",
        "public_claim_fields",
        "claim_support_fields",
        "proof_card_fields",
        "evidence_status_values",
        "response_mode_values",
        "publication_kind_values",
        "support_state_values",
    }
    if set(manifest) != required:
        raise ValueError("release-promotion manifest fields are invalid")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("release-promotion schema is invalid")
    if manifest["from_version"] != FROM_VERSION or manifest["to_version"] != TO_VERSION:
        raise ValueError("release-promotion versions are invalid")
    if manifest["frozen_standard_path"] != STANDARD_RELATIVE:
        raise ValueError("release-promotion frozen standard path is invalid")
    observed_standard = file_sha256(root / STANDARD_RELATIVE)
    if manifest["frozen_standard_sha256"] != observed_standard:
        raise ValueError("frozen V1.6 standard hash changed")
    standard_text = (root / STANDARD_RELATIVE).read_text(encoding="utf-8")
    if f"release_target: {FROZEN_STANDARD_RELEASE_TARGET}" not in standard_text:
        raise ValueError("frozen V1.6 standard release target changed")
    parent_commit = nonempty_string(
        manifest["functional_parent_commit"], "functional parent commit"
    )
    parent_tree = nonempty_string(manifest["functional_parent_tree"], "functional parent tree")
    if COMMIT_RE.fullmatch(parent_commit) is None or COMMIT_RE.fullmatch(parent_tree) is None:
        raise ValueError("functional parent identities must be full lowercase Git SHAs")
    allowed = manifest["allowed_paths"]
    if not isinstance(allowed, list) or tuple(allowed) != ALLOWED_PROMOTION_PATHS:
        raise ValueError("release-promotion allowlist is invalid")
    surface = public_contract_surface()
    for key, expected in surface.items():
        observed = manifest.get(key)
        if not isinstance(observed, list) or tuple(observed) != expected:
            raise ValueError(f"release-promotion {key.replace('_', ' ')} drifted")
    if (
        normalize_release_version(release_version, label="requested release version")
        != TO_VERSION
    ):
        raise ValueError("requested release version is not the promoted identity")
    surfaces = version_surfaces(root)
    if {normalize_release_version(value, label=name) for name, value in surfaces.items()} != {
        TO_VERSION
    }:
        raise ValueError(
            "Python/web/runtime/Docker/Render/OpenAPI/workflow versions do not agree"
        )
    if any(value != TO_VERSION for name, value in surfaces.items() if name != "pyproject"):
        raise ValueError("non-PEP440 version surfaces must use 1.6.0")
    if surfaces["pyproject"] != TO_VERSION:
        raise ValueError("Python package version must be 1.6.0")
    if _require_git(root):
        head = _git(root, "rev-parse", "HEAD")
        head_tree = _git(root, "rev-parse", "HEAD^{tree}")
        if head != commit or head_tree != tree:
            raise ValueError("release-promotion checkout does not match candidate identity")
        bind_functional_parent(
            root,
            parent_commit=parent_commit,
            parent_tree=parent_tree,
            commit=commit,
        )
        promotion_commit = unique_promotion_commit(
            root, parent_commit=parent_commit, commit=commit
        )
        changed = [
            line
            for line in _git(
                root, "diff", "--name-only", parent_commit, promotion_commit
            ).splitlines()
            if line
        ]
        extra = [path for path in changed if path not in ALLOWED_PROMOTION_PATHS]
        if extra:
            raise ValueError("promotion diff contains non-allowlisted paths")
    else:
        promotion_commit = None
    return {
        "schema_version": SCHEMA_VERSION,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "frozen_standard_sha256": observed_standard,
        "functional_parent_commit": parent_commit,
        "functional_parent_tree": parent_tree,
        "promotion_commit": promotion_commit,
        "allowed_paths": list(ALLOWED_PROMOTION_PATHS),
        "version_surfaces": surfaces,
    }


def promotion_material_record(root: Path) -> dict[str, object]:
    return file_record(root, MANIFEST_RELATIVE)
