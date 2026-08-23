"""Generate deterministic SBOM, provenance, security, and qualification documents."""

from __future__ import annotations

import re
import tomllib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from firelens.evaluation.candidate_evidence_common import (
    BUILD_TYPE,
    COMMIT,
    EXACT_REQUIREMENT,
    MATERIAL_PATHS,
    QUALIFICATION_SCHEMA_VERSION,
    SECURITY_SCHEMA_VERSION,
    SUBJECT_FILE,
    SUBJECT_TREE,
    file_record,
    load_json,
    strict_file,
    tree_record,
)
from firelens.evaluation.candidate_evidence_validation import (
    validate_build_environment,
    validate_checkout_state,
    validate_command_outcomes,
    validate_credential_absence,
    validate_hard_probe,
    validate_limitations,
    validate_structured_eval,
    validate_timestamp,
    validate_workflow_identity,
)


def _python_components(root: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in strict_file(root, "requirements.lock").read_text(encoding="utf-8").splitlines():
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
    lock = load_json(strict_file(root, "apps/web/package-lock.json"), "npm lockfile")
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


def _normalized_release_version(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} is invalid")
    normalized = re.sub(r"(?<=\d)[.-]?rc[.-]?(?=\d)", "rc", value.casefold())
    if re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+)?", normalized) is None:
        raise ValueError(f"{label} is invalid")
    return normalized


def _validate_release_version(root: Path, release_version: str) -> None:
    try:
        pyproject = tomllib.loads(
            strict_file(root, "pyproject.toml").read_text(encoding="utf-8")
        )
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("pyproject release version cannot be read") from exc
    package = load_json(strict_file(root, "apps/web/package.json"), "web package manifest")
    runtime = load_json(strict_file(root, SUBJECT_FILE), "runtime candidate")
    versions = {
        "requested release version": release_version,
        "pyproject project.version": (
            pyproject.get("project", {}).get("version")
            if isinstance(pyproject.get("project"), dict)
            else None
        ),
        "web package version": package.get("version") if isinstance(package, dict) else None,
        "runtime candidate release version": (
            runtime.get("release_version") if isinstance(runtime, dict) else None
        ),
    }
    normalized = {
        label: _normalized_release_version(value, label=label)
        for label, value in versions.items()
    }
    if len(set(normalized.values())) != 1:
        raise ValueError("candidate evidence release version identities do not match")


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


def documents(
    root: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    python_audit: Any,
    npm_audit: Any,
    licenses: Any,
    checkout_state: Any,
    build_environment: Any,
    command_outcomes: Any,
    credential_absence: Any,
    workflow_identity: Any,
    structured_eval: Any,
    hard_probe: Any,
    hard_probe_baseline: Any,
    limitations: list[str],
    evidence_hashes: dict[str, str],
) -> dict[str, dict[str, object]]:
    if COMMIT.fullmatch(commit) is None or COMMIT.fullmatch(tree) is None:
        raise ValueError("candidate evidence commit and tree must be full lowercase Git SHAs")
    validate_timestamp(generated_at)
    _validate_release_version(root, release_version)
    if not builder_id or not invocation_id:
        raise ValueError("candidate evidence requires builder and invocation identities")

    limitations = validate_limitations(limitations)
    validate_checkout_state(checkout_state, commit=commit, tree=tree)
    environment = validate_build_environment(build_environment)
    validate_command_outcomes(command_outcomes)
    credentials = validate_credential_absence(credential_absence)
    workflow = validate_workflow_identity(workflow_identity, commit=commit, tree=tree)
    expected_builder = (
        f"https://github.com/{workflow['repository']}/actions/workflows/candidate.yml"
    )
    expected_invocation = f"{workflow['run_id']}:{workflow['run_attempt']}"
    if builder_id != expected_builder or invocation_id != expected_invocation:
        raise ValueError(
            "candidate evidence builder/invocation does not match workflow identity"
        )
    validate_structured_eval(structured_eval, root=root)
    _, hard_probe_summary = validate_hard_probe(
        hard_probe,
        hard_probe_baseline,
        root=root,
        commit=commit,
        tree=tree,
    )

    materials = [file_record(root, name) for name in MATERIAL_PATHS]
    subjects = [file_record(root, SUBJECT_FILE), tree_record(root, SUBJECT_TREE)]
    components = sorted(
        [*_python_components(root), *_node_components(root)],
        key=lambda item: str(item["bom-ref"]),
    )
    lock_identity = ":".join(
        str(item["sha256"])
        for item in materials
        if item["name"] in {"requirements.lock", "apps/web/package-lock.json"}
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"firelens:{commit}:{tree}:{lock_identity}")
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
                    {"name": "firelens:candidate-tree", "value": tree},
                ],
            },
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "firelens-candidate-evidence",
                        "version": "2",
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
                    "candidate_tree": tree,
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
    qualification: dict[str, object] = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "candidate_identity": {"commit": commit, "tree": tree},
        "clean_starting_state": True,
        "environment": environment,
        "commands_passed": True,
        "structured_publication": {
            "executed": True,
            "structural_pass": True,
            "structural_leaks": 0,
        },
        "hard_probe": hard_probe_summary,
        "credentials": {
            "required_credentials_absent": True,
            "provider_calls": credentials["provider_calls"],
            "paid_cost_usd": credentials["paid_cost_usd"],
            "sealed_labels_accessed": credentials["sealed_labels_accessed"],
        },
        "limitations": limitations,
        "gate_passed": bool(security["gate_passed"]),
    }
    return {
        "candidate-sbom.cdx.json": sbom,
        "candidate-provenance.intoto.json": provenance,
        "candidate-security-summary.json": security,
        "candidate-qualification-summary.json": qualification,
    }
