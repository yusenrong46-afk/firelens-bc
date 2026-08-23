"""Build and verify a commit-bound FireLens candidate evidence bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from firelens.config import DEFAULT_RELEASE_VERSION
from firelens.evaluation.candidate_evidence_common import (
    GENERATED_NAMES,
    MATERIAL_PATHS,
    RAW_EVIDENCE_NAMES,
    SCHEMA_VERSION,
    STALE_REPORT_PATH,
    SUBJECT_FILE,
    SUBJECT_TREE,
    canonical_bytes,
    file_record,
    load_json,
    sha256_bytes,
    strict_file,
    tree_record,
)
from firelens.evaluation.candidate_evidence_common import (
    REQUIRED_COMMAND_POLICIES as _REQUIRED_COMMAND_POLICIES,
)
from firelens.evaluation.candidate_evidence_documents import documents
from firelens.evaluation.candidate_evidence_validation import exact_object

REQUIRED_COMMAND_POLICIES = _REQUIRED_COMMAND_POLICIES


def _manifest(
    bundle: Path,
    root: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    security_gate_passed: bool,
    qualification_gate_passed: bool,
    limitations: list[str],
) -> dict[str, object]:
    artifact_names = [*RAW_EVIDENCE_NAMES, *GENERATED_NAMES]
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_identity": {"commit": commit, "tree": tree},
        "clean_starting_state": True,
        "release_version": release_version,
        "generated_at": generated_at,
        "workflow_identity": {"builder_id": builder_id, "invocation_id": invocation_id},
        "security_gate_passed": security_gate_passed,
        "qualification_gate_passed": qualification_gate_passed,
        "limitations": limitations,
        "materials": [file_record(root, name) for name in MATERIAL_PATHS],
        "subjects": [file_record(root, SUBJECT_FILE), tree_record(root, SUBJECT_TREE)],
        "artifacts": [file_record(bundle, name) for name in artifact_names],
    }


def build_candidate_evidence(
    root: Path,
    output_dir: Path,
    *,
    commit: str,
    tree: str,
    release_version: str,
    generated_at: str,
    builder_id: str,
    invocation_id: str,
    python_audit_path: Path,
    npm_audit_path: Path,
    licenses_path: Path,
    checkout_state_path: Path,
    build_environment_path: Path,
    command_outcomes_path: Path,
    credential_absence_path: Path,
    workflow_identity_path: Path,
    structured_eval_path: Path,
    hard_probe_path: Path,
    limitations: list[str],
) -> bool:
    """Create a closed candidate bundle and return its complete gate disposition."""

    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("candidate evidence output must not already exist")
    if output_dir.parent.is_symlink():
        raise ValueError("candidate evidence output parent cannot be a symlink")
    inputs = {
        "inputs/python-audit.json": python_audit_path,
        "inputs/npm-audit.json": npm_audit_path,
        "inputs/dependency-licenses.json": licenses_path,
        "inputs/checkout-state.json": checkout_state_path,
        "inputs/build-environment.json": build_environment_path,
        "inputs/command-outcomes.json": command_outcomes_path,
        "inputs/credential-absence.json": credential_absence_path,
        "inputs/workflow-identity.json": workflow_identity_path,
        "inputs/structured-publication-eval.json": structured_eval_path,
        "inputs/hard-probe.json": hard_probe_path,
        "inputs/hard-probe-baseline.json": strict_file(
            root,
            "docs/reports/V1_6_STRUCTURED_PUBLICATION_HARD_PROBE.json",
        ),
    }
    raw_values = {name: load_json(path, name) for name, path in inputs.items()}
    raw_bytes = {name: path.read_bytes() for name, path in inputs.items()}
    evidence_hashes = {name: sha256_bytes(value) for name, value in raw_bytes.items()}
    generated_documents = documents(
        root,
        commit=commit,
        tree=tree,
        release_version=release_version,
        generated_at=generated_at,
        builder_id=builder_id,
        invocation_id=invocation_id,
        python_audit=raw_values["inputs/python-audit.json"],
        npm_audit=raw_values["inputs/npm-audit.json"],
        licenses=raw_values["inputs/dependency-licenses.json"],
        checkout_state=raw_values["inputs/checkout-state.json"],
        build_environment=raw_values["inputs/build-environment.json"],
        command_outcomes=raw_values["inputs/command-outcomes.json"],
        credential_absence=raw_values["inputs/credential-absence.json"],
        workflow_identity=raw_values["inputs/workflow-identity.json"],
        structured_eval=raw_values["inputs/structured-publication-eval.json"],
        hard_probe=raw_values["inputs/hard-probe.json"],
        hard_probe_baseline=raw_values["inputs/hard-probe-baseline.json"],
        limitations=limitations,
        evidence_hashes=evidence_hashes,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".candidate-evidence-", dir=output_dir.parent))
    try:
        for name, value in raw_bytes.items():
            (temporary / name).parent.mkdir(parents=True, exist_ok=True)
            (temporary / name).write_bytes(value)
        for name, document in generated_documents.items():
            (temporary / name).write_bytes(canonical_bytes(document))
        security = generated_documents["candidate-security-summary.json"]
        qualification = generated_documents["candidate-qualification-summary.json"]
        manifest = _manifest(
            temporary,
            root,
            commit=commit,
            tree=tree,
            release_version=release_version,
            generated_at=generated_at,
            builder_id=builder_id,
            invocation_id=invocation_id,
            security_gate_passed=bool(security["gate_passed"]),
            qualification_gate_passed=bool(qualification["gate_passed"]),
            limitations=limitations,
        )
        (temporary / "candidate-evidence-manifest.json").write_bytes(canonical_bytes(manifest))
        os.replace(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return bool(
        generated_documents["candidate-security-summary.json"]["gate_passed"]
        and generated_documents["candidate-qualification-summary.json"]["gate_passed"]
    )


def _load_candidate_manifest(
    bundle: Path, expected_commit: str, expected_tree: str
) -> dict[str, Any]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("candidate evidence bundle must be a regular directory")
    manifest = load_json(
        strict_file(bundle, "candidate-evidence-manifest.json"),
        "candidate evidence manifest",
    )
    manifest = exact_object(
        manifest,
        {
            "schema_version",
            "candidate_identity",
            "clean_starting_state",
            "release_version",
            "generated_at",
            "workflow_identity",
            "security_gate_passed",
            "qualification_gate_passed",
            "limitations",
            "materials",
            "subjects",
            "artifacts",
        },
        "candidate evidence manifest",
    )
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("candidate evidence manifest schema is invalid")
    if manifest.get("candidate_identity") != {
        "commit": expected_commit,
        "tree": expected_tree,
    }:
        raise ValueError("candidate evidence commit/tree does not match the expected identity")
    if manifest.get("clean_starting_state") is not True:
        raise ValueError("candidate evidence manifest lacks a clean starting state")
    path_records = [*(manifest.get("materials") or []), *(manifest.get("artifacts") or [])]
    if any(
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and STALE_REPORT_PATH.search(item["name"])
        for item in path_records
    ):
        raise ValueError("candidate evidence contains a stale V1.5 report path")
    return manifest


def _verify_artifact_roster(bundle: Path, manifest: dict[str, Any]) -> set[str]:
    expected_names = {
        "candidate-evidence-manifest.json",
        *RAW_EVIDENCE_NAMES,
        *GENERATED_NAMES,
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
        file_record(bundle, name)
        for name in sorted(expected_names - {"candidate-evidence-manifest.json"})
    ]
    if sorted(recorded_artifacts, key=lambda item: str(item.get("name"))) != actual_records:
        raise ValueError("candidate evidence artifact identity does not match the manifest")
    return expected_names


def verify_candidate_evidence(
    root: Path,
    bundle: Path,
    *,
    expected_commit: str,
    expected_tree: str,
) -> None:
    """Recompute every generated document and reject an incomplete or changed bundle."""

    root = root.resolve()
    bundle = bundle.resolve()
    manifest = _load_candidate_manifest(bundle, expected_commit, expected_tree)
    _verify_artifact_roster(bundle, manifest)
    actual_materials = [file_record(root, name) for name in MATERIAL_PATHS]
    if manifest.get("materials") != actual_materials:
        raise ValueError("candidate evidence material identity does not recompute")
    actual_subjects = [file_record(root, SUBJECT_FILE), tree_record(root, SUBJECT_TREE)]
    if manifest.get("subjects") != actual_subjects:
        raise ValueError("candidate evidence subject identity does not recompute")
    raw_values = {
        name: load_json(strict_file(bundle, name), name) for name in RAW_EVIDENCE_NAMES
    }
    evidence_hashes = {name: file_record(bundle, name)["sha256"] for name in RAW_EVIDENCE_NAMES}
    workflow = manifest.get("workflow_identity")
    if not isinstance(workflow, dict):
        raise ValueError("candidate evidence workflow identity is invalid")
    limitations = manifest.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) for item in limitations
    ):
        raise ValueError("candidate evidence limitations are invalid")
    generated_documents = documents(
        root,
        commit=expected_commit,
        tree=expected_tree,
        release_version=str(manifest.get("release_version") or ""),
        generated_at=str(manifest.get("generated_at") or ""),
        builder_id=str(workflow.get("builder_id") or ""),
        invocation_id=str(workflow.get("invocation_id") or ""),
        python_audit=raw_values["inputs/python-audit.json"],
        npm_audit=raw_values["inputs/npm-audit.json"],
        licenses=raw_values["inputs/dependency-licenses.json"],
        checkout_state=raw_values["inputs/checkout-state.json"],
        build_environment=raw_values["inputs/build-environment.json"],
        command_outcomes=raw_values["inputs/command-outcomes.json"],
        credential_absence=raw_values["inputs/credential-absence.json"],
        workflow_identity=raw_values["inputs/workflow-identity.json"],
        structured_eval=raw_values["inputs/structured-publication-eval.json"],
        hard_probe=raw_values["inputs/hard-probe.json"],
        hard_probe_baseline=raw_values["inputs/hard-probe-baseline.json"],
        limitations=limitations,
        evidence_hashes={name: str(value) for name, value in evidence_hashes.items()},
    )
    for name, expected in generated_documents.items():
        observed = load_json(strict_file(bundle, name), name)
        if observed != expected:
            raise ValueError(f"candidate evidence document does not recompute: {name}")
    security_passed = bool(
        generated_documents["candidate-security-summary.json"]["gate_passed"]
    )
    qualification_passed = bool(
        generated_documents["candidate-qualification-summary.json"]["gate_passed"]
    )
    if manifest.get("security_gate_passed") is not security_passed:
        raise ValueError("candidate evidence security disposition is inconsistent")
    if manifest.get("qualification_gate_passed") is not qualification_passed:
        raise ValueError("candidate evidence qualification disposition is inconsistent")
    if not security_passed:
        raise ValueError("candidate evidence security gate did not pass")
    if not qualification_passed:
        raise ValueError("candidate evidence qualification gate did not pass")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--project-root", type=Path, default=Path("."))
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--commit", default=os.environ.get("GITHUB_SHA"), required=False)
    build.add_argument("--tree", required=True)
    build.add_argument("--release-version", default=DEFAULT_RELEASE_VERSION)
    build.add_argument("--generated-at", required=True)
    build.add_argument("--builder-id", required=True)
    build.add_argument("--invocation-id", required=True)
    build.add_argument("--python-audit", type=Path, required=True)
    build.add_argument("--npm-audit", type=Path, required=True)
    build.add_argument("--licenses", type=Path, required=True)
    build.add_argument("--checkout-state", type=Path, required=True)
    build.add_argument("--build-environment", type=Path, required=True)
    build.add_argument("--command-outcomes", type=Path, required=True)
    build.add_argument("--credential-absence", type=Path, required=True)
    build.add_argument("--workflow-identity", type=Path, required=True)
    build.add_argument("--structured-eval", type=Path, required=True)
    build.add_argument("--hard-probe", type=Path, required=True)
    build.add_argument("--limitation", action="append", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--project-root", type=Path, default=Path("."))
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--expected-commit", required=True)
    verify.add_argument("--expected-tree", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            passed = build_candidate_evidence(
                args.project_root,
                args.output_dir,
                commit=args.commit or "",
                tree=args.tree,
                release_version=args.release_version,
                generated_at=args.generated_at,
                builder_id=args.builder_id,
                invocation_id=args.invocation_id,
                python_audit_path=args.python_audit,
                npm_audit_path=args.npm_audit,
                licenses_path=args.licenses,
                checkout_state_path=args.checkout_state,
                build_environment_path=args.build_environment,
                command_outcomes_path=args.command_outcomes,
                credential_absence_path=args.credential_absence,
                workflow_identity_path=args.workflow_identity,
                structured_eval_path=args.structured_eval,
                hard_probe_path=args.hard_probe,
                limitations=args.limitation,
            )
            print(args.output_dir)
            return 0 if passed else 2
        verify_candidate_evidence(
            args.project_root,
            args.bundle,
            expected_commit=args.expected_commit,
            expected_tree=args.expected_tree,
        )
    except (OSError, ValueError) as exc:
        print(f"candidate evidence refused: {exc}")
        return 2
    print(args.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
