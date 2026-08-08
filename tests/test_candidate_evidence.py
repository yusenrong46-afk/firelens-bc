from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.candidate_evidence import (
    MATERIAL_PATHS,
    SUBJECT_FILE,
    SUBJECT_TREE,
    build_candidate_evidence,
    verify_candidate_evidence,
)

COMMIT = "a" * 40
GENERATED_AT = "2026-08-08T20:00:00+00:00"


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _json(path: Path, value: object) -> None:
    _write(path, json.dumps(value) + "\n")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in MATERIAL_PATHS:
        _write(root / relative, f"fixture:{relative}\n")
    _write(root / "requirements.lock", "fastapi==1.2.3\nPyYAML==6.0.3\n")
    _json(
        root / "apps/web/package-lock.json",
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "ui", "version": "1.0.0"},
                "node_modules/react": {
                    "version": "19.2.0",
                    "license": "MIT",
                },
                "node_modules/vitest": {
                    "version": "4.1.10",
                    "license": "MIT",
                    "dev": True,
                },
            },
        },
    )
    _json(root / SUBJECT_FILE, {"schema_version": "firelens.runtime_candidate.v1"})
    _write(root / SUBJECT_TREE / "index.html", "<!doctype html><div>FireLens</div>\n")
    _write(root / SUBJECT_TREE / "assets/app.js", "console.log('FireLens');\n")
    return root


def _audit_inputs(
    tmp_path: Path,
    *,
    python_vulnerabilities: list[dict[str, object]] | None = None,
    npm_high: int = 0,
    npm_critical: int = 0,
    prohibited: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    inputs = tmp_path / "inputs"
    python = inputs / "python-audit.json"
    npm = inputs / "npm-audit.json"
    licenses = inputs / "dependency-licenses.json"
    _json(
        python,
        [
            {
                "name": "fastapi",
                "version": "1.2.3",
                "vulns": python_vulnerabilities or [],
            }
        ],
    )
    _json(
        npm,
        {
            "auditReportVersion": 2,
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 0,
                    "moderate": 0,
                    "high": npm_high,
                    "critical": npm_critical,
                    "total": npm_high + npm_critical,
                }
            },
        },
    )
    _json(
        licenses,
        {
            "python": [{"name": "fastapi", "version": "1.2.3", "license": "MIT"}],
            "node": [{"name": "react", "version": "19.2.0", "license": "MIT"}],
            "prohibited": prohibited or [],
        },
    )
    return python, npm, licenses


def _build(
    root: Path,
    bundle: Path,
    audits: tuple[Path, Path, Path],
) -> bool:
    python, npm, licenses = audits
    return build_candidate_evidence(
        root,
        bundle,
        commit=COMMIT,
        release_version="1.5.0-rc.1",
        generated_at=GENERATED_AT,
        builder_id="test://builder",
        invocation_id="test-run-1",
        python_audit_path=python,
        npm_audit_path=npm,
        licenses_path=licenses,
    )


def test_clean_bundle_recomputes_and_verifies(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"

    assert _build(root, bundle, _audit_inputs(tmp_path)) is True
    verify_candidate_evidence(root, bundle, expected_commit=COMMIT)

    sbom = json.loads((bundle / "candidate-sbom.cdx.json").read_text())
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert {item["properties"][0]["value"] for item in sbom["components"]} == {
        "python",
        "npm",
    }
    provenance = json.loads((bundle / "candidate-provenance.intoto.json").read_text())
    assert provenance["predicateType"] == "https://slsa.dev/provenance/v1"
    assert {subject["name"] for subject in provenance["subject"]} == {
        SUBJECT_FILE,
        SUBJECT_TREE,
    }


@pytest.mark.parametrize(
    ("audit_kwargs", "blocker"),
    [
        (
            {"python_vulnerabilities": [{"id": "PYSEC-1", "fix_versions": []}]},
            "python_vulnerabilities",
        ),
        ({"npm_high": 1}, "npm_high_vulnerabilities"),
        ({"npm_critical": 1}, "npm_critical_vulnerabilities"),
        ({"prohibited": ["python:bad:AGPL-3.0"]}, "prohibited_licenses"),
    ],
)
def test_security_findings_emit_evidence_but_fail_gate(
    tmp_path: Path,
    audit_kwargs: dict[str, object],
    blocker: str,
) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"

    assert _build(root, bundle, _audit_inputs(tmp_path, **audit_kwargs)) is False
    security = json.loads((bundle / "candidate-security-summary.json").read_text())
    assert security["gate_passed"] is False
    assert blocker in security["blockers"]
    with pytest.raises(ValueError, match="security gate did not pass"):
        verify_candidate_evidence(root, bundle, expected_commit=COMMIT)


def test_bundle_tampering_is_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    assert _build(root, bundle, _audit_inputs(tmp_path)) is True
    (bundle / "candidate-sbom.cdx.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact identity"):
        verify_candidate_evidence(root, bundle, expected_commit=COMMIT)


def test_changed_checkout_material_is_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    assert _build(root, bundle, _audit_inputs(tmp_path)) is True
    _write(root / "requirements.lock", "fastapi==9.9.9\n")

    with pytest.raises(ValueError, match="does not recompute"):
        verify_candidate_evidence(root, bundle, expected_commit=COMMIT)


def test_commit_mismatch_and_extra_file_are_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    assert _build(root, bundle, _audit_inputs(tmp_path)) is True

    with pytest.raises(ValueError, match="expected commit"):
        verify_candidate_evidence(root, bundle, expected_commit="b" * 40)
    _write(bundle / "unexpected.txt", "not allowed\n")
    with pytest.raises(ValueError, match="missing or unexpected"):
        verify_candidate_evidence(root, bundle, expected_commit=COMMIT)


def test_existing_output_and_symlinked_subject_are_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    bundle.mkdir()
    with pytest.raises(ValueError, match="must not already exist"):
        _build(root, bundle, _audit_inputs(tmp_path))

    bundle.rmdir()
    target = root / "real-candidate.json"
    _json(target, {"candidate": True})
    (root / SUBJECT_FILE).unlink()
    (root / SUBJECT_FILE).symlink_to(target)
    with pytest.raises(ValueError, match="regular file"):
        _build(root, bundle, _audit_inputs(tmp_path / "again"))
