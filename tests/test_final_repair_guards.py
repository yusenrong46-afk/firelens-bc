from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scripts.report_dependency_licenses as license_report
import scripts.v1_6_round2_retrieval as retrieval_report
from firelens.answering.critical_fields import _OPPOSITE, Comparator
from firelens.evaluation import preview_probe

ROOT = Path(__file__).resolve().parents[1]


def test_authorized_retrieval_dry_run_remains_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retrieval_report, "_authorized", lambda: True)
    monkeypatch.setattr(retrieval_report, "_ceiling", lambda: 100.0)
    monkeypatch.setattr(retrieval_report, "development_roster", lambda _root: [object()])
    monkeypatch.setattr(
        retrieval_report,
        "cost_estimate",
        lambda _count: {"estimated_maximum_usd": 0.01},
    )

    payload = retrieval_report.dry_run(ROOT)

    assert payload["mode"] == "authorized_not_executed_here"
    assert payload["evidence_class"] == "BLOCKED"
    assert payload["provider_metrics"] == "BLOCKED"


@pytest.mark.parametrize(
    "expression",
    [
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "GPL-3.0+",
        "MIT OR GPL-3.0-or-later",
        "AGPL-3.0-only",
        "SSPL-1.0",
    ],
)
def test_prohibited_license_expressions_include_spdx_suffixes(expression: str) -> None:
    assert license_report.is_prohibited_license_expression(expression)


def test_license_expression_matching_does_not_treat_lgpl_as_gpl() -> None:
    assert not license_report.is_prohibited_license_expression("LGPL-3.0-only")


@pytest.mark.parametrize("field", ["fail", "blocked"])
def test_preview_probe_returns_nonzero_for_failed_or_blocked_rows(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    async def fake_run(_args: object) -> int:
        return 2

    monkeypatch.setattr(preview_probe, "run", fake_run)

    assert preview_probe.main(["--base-url", "https://preview.example.test"]) == 2
    report = {
        "pass": 0,
        "fail": int(field == "fail"),
        "blocked": int(field == "blocked"),
    }
    assert preview_probe._exit_code(report) == 2


def test_comparator_beyond_has_one_explicit_opposite_definition() -> None:
    source = (ROOT / "src/firelens/answering/critical_fields.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    mapping = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == "_OPPOSITE" for target in targets):
            mapping = node.value
            break
    assert isinstance(mapping, ast.Dict)
    beyond_keys = [
        key
        for item in mapping.keys
        if isinstance(item, ast.Attribute) and item.attr == "BEYOND"
        for key in [item]
    ]

    assert len(beyond_keys) == 1
    assert _OPPOSITE[Comparator.BEYOND] == {
        Comparator.WITHIN,
        Comparator.AT_MOST,
        Comparator.BETWEEN,
    }
