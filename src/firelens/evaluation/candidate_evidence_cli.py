"""Build and verify a commit-bound FireLens candidate evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

SCHEMA_VERSION = "firelens.candidate_evidence.v1"
SECURITY_SCHEMA_VERSION = "firelens.candidate_security.v1"
BUILD_TYPE = "https://firelens-bc.local/build-types/candidate-evidence/v1"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")

MATERIAL_PATHS = (
    "requirements.lock",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "Dockerfile",
    "vercel.json",
    "render.yaml",
    "config/runtime_artifact_allowlist.v1.json",
    "data/processed/firelens_static_corpus.manifest.json",
    "data/index/firelens_vectors.manifest.json",
    "docs/reports/V1_5_2_BENCHMARK.md",
    "docs/reports/V1_5_2_GATE_LEDGER.yaml",
)
REPORT_PATHS = (
    "docs/reports/V1_5_2_BENCHMARK.md",
    "docs/reports/V1_5_2_GATE_LEDGER.yaml",
)
SUBJECT_FILE = "config/runtime_candidate.v1.json"
SUBJECT_TREE = "apps/web/dist/client"
RAW_EVIDENCE_NAMES = (
    "python-audit.json",
    "npm-audit.json",
    "dependency-licenses.json",
)
GENERATED_NAMES = (
    "candidate-sbom.cdx.json",
    "candidate-provenance.intoto.json",
    "candidate-security-summary.json",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _strict_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe evidence path: {relative}")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"candidate evidence requires a regular file: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"candidate evidence path escapes its root: {relative}")
    return path


def _file_record(root: Path, relative: str) -> dict[str, object]:
    data = _strict_file(root, relative).read_bytes()
    return {"name": relative, "sha256": _sha256_bytes(data), "size_bytes": len(data)}


def _tree_record(root: Path, relative: str) -> dict[str, object]:
    tree = root / relative
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError(f"candidate evidence requires a regular directory: {relative}")
    files: list[dict[str, object]] = []
    total_size = 0
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"candidate subject tree contains a symlink: {path}")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        total_size += len(data)
        files.append({"name": name, "sha256": _sha256_bytes(data), "size_bytes": len(data)})
    if not files:
        raise ValueError(f"candidate subject tree is empty: {relative}")
    digest = _sha256_bytes(_canonical_bytes(files))
    return {
        "name": relative,
        "sha256": digest,
        "size_bytes": total_size,
        "file_count": len(files),
        "files": files,
    }


def _load_json(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular JSON file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc


def _validate_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("candidate evidence timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("candidate evidence timestamp requires a timezone")
    return value


def _python_components(root: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in _strict_file(root, "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT_REQUIREMENT.fullmatch(line)
        if match is None:
            raise ValueError(f"requirements.lock contains a non-exact entry: {line}")
        name, version = match.groups()
        key = name.casefold().replace("_", "-")
        if key in seen:
            raise ValueError(f"requirements.lock contains a duplicate dependency: {name}")
        seen.add(key)
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/{quote(key)}@{quote(version)}",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{quote(key)}@{quote(version)}",
                "scope": "required",
                "properties": [{"name": "firelens:ecosystem", "value": "python"}],
            }
        )
    return components


def _node_components(root: Path) -> list[dict[str, object]]:
    lock = _load_json(
        _strict_file(root, "apps/web/package-lock.json"),
        "npm lockfile",
    )
    if not isinstance(lock, dict) or lock.get("lockfileVersion") != 3:
        raise ValueError("npm lockfile must use lockfileVersion 3")
    components: list[dict[str, object]] = []
    for package_path, metadata in sorted((lock.get("packages") or {}).items()):
        if not package_path:
            continue
        if not isinstance(metadata, dict):
            raise ValueError(f"npm lock entry is invalid: {package_path}")
        name = metadata.get("name") or package_path.rsplit("node_modules/", 1)[-1]
        version = metadata.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise ValueError(f"npm lock entry lacks name/version: {package_path}")
        purl = f"pkg:npm/{quote(name, safe='@/')}@{quote(version)}"
        component: dict[str, object] = {
            "type": "library",
            "bom-ref": f"{purl}?path={quote(package_path, safe='@/')}",
            "name": name,
            "version": version,
            "purl": purl,
            "scope": "optional" if metadata.get("dev") is True else "required",
            "properties": [
                {"name": "firelens:ecosystem", "value": "npm"},
                {"name": "firelens:lock-path", "value": package_path},
            ],
        }
        license_name = metadata.get("license")
        if isinstance(license_name, str) and license_name:
            component["licenses"] = [{"license": {"name": license_name}}]
        components.append(component)
    return components


def _python_audit_summary(report: Any) -> dict[str, object]:
    dependencies = report.get("dependencies") if isinstance(report, dict) else report
    if not isinstance(dependencies, list):
        raise ValueError("pip-audit evidence has no dependency roster")
    findings: list[dict[str, str]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ValueError("pip-audit dependency entry is invalid")
        name = dependency.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("pip-audit dependency entry has no name")
        vulns = dependency.get("vulns") or []
        if not isinstance(vulns, list):
            raise ValueError("pip-audit vulnerability roster is invalid")
        for vulnerability in vulns:
            if not isinstance(vulnerability, dict) or not isinstance(
                vulnerability.get("id"), str
            ):
                raise ValueError("pip-audit vulnerability entry is invalid")
            findings.append({"dependency": name, "id": vulnerability["id"]})
    return {"vulnerability_count": len(findings), "findings": findings}


def _npm_audit_summary(report: Any) -> dict[str, int]:
    if not isinstance(report, dict):
        raise ValueError("npm audit evidence must be an object")
    vulnerabilities = (report.get("metadata") or {}).get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise ValueError("npm audit evidence has no vulnerability summary")
    summary: dict[str, int] = {}
    for severity in ("info", "low", "moderate", "high", "critical", "total"):
        value = vulnerabilities.get(severity, 0)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"npm audit {severity} count is invalid")
        summary[severity] = value
    return summary


def _license_summary(report: Any) -> dict[str, object]:
    if not isinstance(report, dict) or not isinstance(report.get("prohibited"), list):
        raise ValueError("license evidence has no prohibited-license roster")
    python_rows = report.get("python")
    node_rows = report.get("node")
    if not isinstance(python_rows, list) or not isinstance(node_rows, list):
        raise ValueError("license evidence has no dependency rosters")
    prohibited = report["prohibited"]
    if any(not isinstance(item, str) for item in prohibited):
        raise ValueError("license evidence contains an invalid prohibited-license item")
    return {
        "python_dependency_count": len(python_rows),
        "npm_dependency_count": len(node_rows),
        "prohibited_count": len(prohibited),
        "prohibited": prohibited,
    }


def _security_document(
    python_audit: Any,
    npm_audit: Any,
    licenses: Any,
    *,
    evidence_hashes: dict[str, str],
) -> dict[str, object]:
    python_summary = _python_audit_summary(python_audit)
    npm_summary = _npm_audit_summary(npm_audit)
    license_summary = _license_summary(licenses)
    blockers = []
    if python_summary["vulnerability_count"]:
        blockers.append("python_vulnerabilities")
    if npm_summary["high"]:
        blockers.append("npm_high_vulnerabilities")
    if npm_summary["critical"]:
        blockers.append("npm_critical_vulnerabilities")
    if license_summary["prohibited_count"]:
        blockers.append("prohibited_licenses")
    return {
        "schema_version": SECURITY_SCHEMA_VERSION,
        "gate_policy": {
            "python_vulnerabilities_max": 0,
            "npm_high_max": 0,
            "npm_critical_max": 0,
            "prohibited_licenses_max": 0,
        },
        "input_sha256": evidence_hashes,
        "python": python_summary,
        "npm": npm_summary,
        "licenses": license_summary,
        "blockers": blockers,
        "gate_passed": not blockers,
    }


def _documents(
    root: Path,
    *,
    commit: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    python_audit: Any,
    npm_audit: Any,
    licenses: Any,
    evidence_hashes: dict[str, str],
) -> dict[str, dict[str, object]]:
    if COMMIT.fullmatch(commit) is None:
        raise ValueError("candidate evidence commit must be a full lowercase Git SHA")
    _validate_timestamp(generated_at)
    if not release_version or release_version != release_version.strip():
        raise ValueError("candidate evidence release version is invalid")
    if not builder_id or not invocation_id:
        raise ValueError("candidate evidence requires builder and invocation identities")

    materials = [_file_record(root, name) for name in MATERIAL_PATHS]
    subjects = [_file_record(root, SUBJECT_FILE), _tree_record(root, SUBJECT_TREE)]
    components = sorted(
        [*_python_components(root), *_node_components(root)],
        key=lambda item: str(item["bom-ref"]),
    )
    lock_identity = ":".join(
        str(item["sha256"])
        for item in materials
        if item["name"] in {"requirements.lock", "apps/web/package-lock.json"}
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"firelens:{commit}:{lock_identity}")
    sbom: dict[str, object] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": generated_at,
            "component": {
                "type": "application",
                "bom-ref": f"firelens-bc@{commit}",
                "name": "firelens-bc",
                "version": release_version,
                "properties": [
                    {"name": "firelens:candidate-commit", "value": commit},
                ],
            },
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "firelens-candidate-evidence",
                        "version": "1",
                    }
                ]
            },
        },
        "components": components,
    }
    provenance: dict[str, object] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": item["name"], "digest": {"sha256": item["sha256"]}} for item in subjects
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": BUILD_TYPE,
                "externalParameters": {
                    "candidate_commit": commit,
                    "release_version": release_version,
                },
                "internalParameters": {},
                "resolvedDependencies": [
                    {"uri": f"file:{item['name']}", "digest": {"sha256": item["sha256"]}}
                    for item in materials
                ],
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {
                    "invocationId": invocation_id,
                    "startedOn": generated_at,
                    "finishedOn": generated_at,
                },
            },
        },
    }
    security = _security_document(
        python_audit,
        npm_audit,
        licenses,
        evidence_hashes=evidence_hashes,
    )
    return {
        "candidate-sbom.cdx.json": sbom,
        "candidate-provenance.intoto.json": provenance,
        "candidate-security-summary.json": security,
    }


def _manifest(
    bundle: Path,
    *,
    commit: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    gate_passed: bool,
) -> dict[str, object]:
    artifact_names = [
        *RAW_EVIDENCE_NAMES,
        *GENERATED_NAMES,
        *(f"reports/{Path(name).name}" for name in REPORT_PATHS),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_commit": commit,
        "release_version": release_version,
        "generated_at": generated_at,
        "builder_id": builder_id,
        "invocation_id": invocation_id,
        "security_gate_passed": gate_passed,
        "artifacts": [_file_record(bundle, name) for name in artifact_names],
    }


def build_candidate_evidence(
    root: Path,
    output_dir: Path,
    *,
    commit: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    python_audit_path: Path,
    npm_audit_path: Path,
    licenses_path: Path,
) -> bool:
    """Create a closed candidate bundle and return its security-gate disposition."""

    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("candidate evidence output must not already exist")
    if output_dir.parent.is_symlink():
        raise ValueError("candidate evidence output parent cannot be a symlink")
    inputs = {
        "python-audit.json": python_audit_path,
        "npm-audit.json": npm_audit_path,
        "dependency-licenses.json": licenses_path,
    }
    raw_values = {name: _load_json(path, name) for name, path in inputs.items()}
    raw_bytes = {name: path.read_bytes() for name, path in inputs.items()}
    evidence_hashes = {name: _sha256_bytes(value) for name, value in raw_bytes.items()}
    documents = _documents(
        root,
        commit=commit,
        release_version=release_version,
        generated_at=generated_at,
        builder_id=builder_id,
        invocation_id=invocation_id,
        python_audit=raw_values["python-audit.json"],
        npm_audit=raw_values["npm-audit.json"],
        licenses=raw_values["dependency-licenses.json"],
        evidence_hashes=evidence_hashes,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".candidate-evidence-", dir=output_dir.parent))
    try:
        for name, value in raw_bytes.items():
            (temporary / name).write_bytes(value)
        reports = temporary / "reports"
        reports.mkdir()
        for relative in REPORT_PATHS:
            shutil.copyfile(_strict_file(root, relative), reports / Path(relative).name)
        for name, document in documents.items():
            (temporary / name).write_bytes(_canonical_bytes(document))
        security = documents["candidate-security-summary.json"]
        manifest = _manifest(
            temporary,
            commit=commit,
            release_version=release_version,
            generated_at=generated_at,
            builder_id=builder_id,
            invocation_id=invocation_id,
            gate_passed=bool(security["gate_passed"]),
        )
        (temporary / "candidate-evidence-manifest.json").write_bytes(_canonical_bytes(manifest))
        os.replace(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return bool(documents["candidate-security-summary.json"]["gate_passed"])


def _load_candidate_manifest(bundle: Path, expected_commit: str) -> dict[str, Any]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("candidate evidence bundle must be a regular directory")
    manifest = _load_json(
        _strict_file(bundle, "candidate-evidence-manifest.json"),
        "candidate evidence manifest",
    )
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("candidate evidence manifest schema is invalid")
    if manifest.get("candidate_commit") != expected_commit:
        raise ValueError("candidate evidence commit does not match the expected commit")
    return manifest


def _verify_artifact_roster(bundle: Path, manifest: dict[str, Any]) -> set[str]:
    expected_names = {
        "candidate-evidence-manifest.json",
        *RAW_EVIDENCE_NAMES,
        *GENERATED_NAMES,
        *(f"reports/{Path(name).name}" for name in REPORT_PATHS),
    }
    observed_names = {
        path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()
    }
    if observed_names != expected_names:
        raise ValueError("candidate evidence bundle has a missing or unexpected file")
    if any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("candidate evidence bundle cannot contain symlinks")

    recorded_artifacts = manifest.get("artifacts")
    if not isinstance(recorded_artifacts, list):
        raise ValueError("candidate evidence manifest has no artifact roster")
    actual_records = [
        _file_record(bundle, name)
        for name in sorted(expected_names - {"candidate-evidence-manifest.json"})
    ]
    if sorted(recorded_artifacts, key=lambda item: str(item.get("name"))) != actual_records:
        raise ValueError("candidate evidence artifact identity does not match the manifest")
    return expected_names


def verify_candidate_evidence(root: Path, bundle: Path, *, expected_commit: str) -> None:
    """Recompute every generated document and reject an incomplete or changed bundle."""

    root = root.resolve()
    bundle = bundle.resolve()
    manifest = _load_candidate_manifest(bundle, expected_commit)
    _verify_artifact_roster(bundle, manifest)

    raw_values = {
        name: _load_json(_strict_file(bundle, name), name) for name in RAW_EVIDENCE_NAMES
    }
    evidence_hashes = {
        name: _file_record(bundle, name)["sha256"] for name in RAW_EVIDENCE_NAMES
    }
    documents = _documents(
        root,
        commit=expected_commit,
        release_version=str(manifest.get("release_version") or ""),
        generated_at=str(manifest.get("generated_at") or ""),
        builder_id=str(manifest.get("builder_id") or ""),
        invocation_id=str(manifest.get("invocation_id") or ""),
        python_audit=raw_values["python-audit.json"],
        npm_audit=raw_values["npm-audit.json"],
        licenses=raw_values["dependency-licenses.json"],
        evidence_hashes={name: str(value) for name, value in evidence_hashes.items()},
    )
    for name, expected in documents.items():
        observed = _load_json(_strict_file(bundle, name), name)
        if observed != expected:
            raise ValueError(f"candidate evidence document does not recompute: {name}")
    for source in REPORT_PATHS:
        copied = f"reports/{Path(source).name}"
        if _strict_file(root, source).read_bytes() != _strict_file(bundle, copied).read_bytes():
            raise ValueError(f"candidate evidence report copy changed: {copied}")
    gate_passed = bool(documents["candidate-security-summary.json"]["gate_passed"])
    if manifest.get("security_gate_passed") is not gate_passed:
        raise ValueError("candidate evidence security disposition is inconsistent")
    if not gate_passed:
        raise ValueError("candidate evidence security gate did not pass")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--project-root", type=Path, default=Path("."))
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--commit", default=os.environ.get("GITHUB_SHA"), required=False)
    build.add_argument("--release-version", default="1.5.3-rc.1")
    build.add_argument("--generated-at", required=True)
    build.add_argument("--builder-id", required=True)
    build.add_argument("--invocation-id", required=True)
    build.add_argument("--python-audit", type=Path, required=True)
    build.add_argument("--npm-audit", type=Path, required=True)
    build.add_argument("--licenses", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--project-root", type=Path, default=Path("."))
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--expected-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            passed = build_candidate_evidence(
                args.project_root,
                args.output_dir,
                commit=args.commit or "",
                release_version=args.release_version,
                generated_at=args.generated_at,
                builder_id=args.builder_id,
                invocation_id=args.invocation_id,
                python_audit_path=args.python_audit,
                npm_audit_path=args.npm_audit,
                licenses_path=args.licenses,
            )
            print(args.output_dir)
            return 0 if passed else 2
        verify_candidate_evidence(
            args.project_root,
            args.bundle,
            expected_commit=args.expected_commit,
        )
    except (OSError, ValueError) as exc:
        print(f"candidate evidence refused: {exc}")
        return 2
    print(args.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
