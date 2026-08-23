from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_batch_export_contains_bound_cards_and_blank_decisions(tmp_path: Path) -> None:
    output = tmp_path / "batch-2.html"
    decisions = tmp_path / "batch-2-decisions.yaml"
    manifest = tmp_path / "batch-2-manifest.json"
    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/typed_claim_review_export.py"),
            "--output",
            str(output),
            "--batch",
            "2",
            "--decision-template",
            str(decisions),
            "--manifest",
            str(manifest),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = output.read_text(encoding="utf-8")
    assert rendered.count("<article class='card'>") == 10
    assert "Document SHA-256" in rendered
    assert "Typed fields" in rendered
    assert "pending_review" in rendered
    payload = yaml.safe_load(decisions.read_text(encoding="utf-8"))
    assert payload["batch"] == 2
    assert len(payload["decisions"]) == 10
    assert all(row["decision"] is None for row in payload["decisions"])
    assert all(row["reviewer"] is None for row in payload["decisions"])
    assert all(row["decision_time"] is None for row in payload["decisions"])
    hashes = json.loads(manifest.read_text(encoding="utf-8"))
    assert hashes["record_count"] == 10
    assert hashes["contains_reviewer_identity"] is False
    assert hashes["decision_fields_blank"] is True
    assert hashes["html_sha256"] == sha256(output.read_bytes()).hexdigest()
    assert hashes["decision_template_sha256"] == sha256(decisions.read_bytes()).hexdigest()
