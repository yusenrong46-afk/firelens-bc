from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from firelens.api import create_app
from firelens.config import DEFAULT_RELEASE_VERSION, FireLensConfig
from firelens_eval import inventory
from scripts.export_openapi import build_export_config
from scripts.firelens_agent.docs_drift import documentation_reference_findings

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_documentation_links_images_and_linked_symbols_are_current() -> None:
    assert documentation_reference_findings(ROOT) == []
    screenshots = sorted((ROOT / "docs/product/screenshots").glob("*.png"))
    assert screenshots
    for screenshot in screenshots:
        assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_documentation_reference_drift_reports_mechanical_failures(tmp_path: Path) -> None:
    (tmp_path / "docs/firelens-map").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.py").write_text("def kept():\n    pass\n", encoding="utf-8")
    (tmp_path / "docs/empty.png").write_bytes(b"")
    (tmp_path / "docs/guide.md").write_text(
        "[missing](missing.md)\n"
        "![shot](empty.png)\n"
        "[code](../src/example.py) `gone`\n"
        "[nested](../src/example.py) `install_answer_routes.ask`\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/firelens-map/symbol-index.json").write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "module_path": "src/example.py",
                        "name": "kept",
                        "qualname": "kept",
                    },
                    {
                        "module_path": "src/example.py",
                        "name": "ask",
                        "qualname": "install_answer_routes.ask",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert documentation_reference_findings(tmp_path) == [
        "broken internal link: docs/guide.md:1 -> docs/missing.md",
        "empty linked image: docs/guide.md:2 -> docs/empty.png",
        "deleted linked symbol: docs/guide.md:3 -> src/example.py::gone",
    ]


def test_openapi_and_generated_types_match_executable_contract(
    tmp_path: Path,
) -> None:
    schema = create_app(build_export_config(ROOT)).openapi()
    rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    assert (ROOT / "docs/openapi.v1.json").read_text(encoding="utf-8") == rendered

    generator = ROOT / "apps/web/node_modules/.bin/openapi-typescript"
    assert generator.is_file()
    output = tmp_path / "api-schema.d.ts"
    subprocess.run(
        [str(generator), "docs/openapi.v1.json", "-o", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        output.read_bytes() == (ROOT / "apps/web/src/shared/api/api-schema.d.ts").read_bytes()
    )


def test_release_and_provider_defaults_match_current_system_card() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == package["version"] == DEFAULT_RELEASE_VERSION

    system_card = (ROOT / "docs/system-card/FIRELENS_SYSTEM_CARD.md").read_text(
        encoding="utf-8"
    )
    assert f"| Tracked release label | `{DEFAULT_RELEASE_VERSION}`" in system_card
    for label, relative in (
        ("validate_map.py", "scripts/firelens_agent/validate_map.py"),
        ("tests/test_firelens_map.py", "tests/test_firelens_map.py"),
    ):
        assert f"`{label}` SHA-256 `{_sha256(ROOT / relative)}`" in system_card
    for field in ("embedding_model", "rerank_model", "generation_model"):
        assert f"`{FireLensConfig.model_fields[field].default}`" in system_card
    assert FireLensConfig.model_fields["openrouter_base_url"].default == (
        "https://openrouter.ai/api/v1"
    )

    dependency_names = {
        re.split(r"[\s<=>~!\[]", value, maxsplit=1)[0].casefold()
        for value in pyproject["project"]["dependencies"]
    }
    dependency_names.update(package["dependencies"])
    dependency_names.update(package["devDependencies"])
    direct_sdks = {
        "@ai-sdk/anthropic",
        "@ai-sdk/openai",
        "@google/generative-ai",
        "anthropic",
        "cohere",
        "google-generativeai",
        "groq",
        "mistralai",
        "openai",
        "replicate",
        "together",
    }
    assert dependency_names.isdisjoint(direct_sdks)
    direct_hosts = (
        "api.anthropic.com",
        "api.cohere.com",
        "api.groq.com",
        "api.mistral.ai",
        "api.openai.com",
        "api.together.xyz",
        "generativelanguage.googleapis.com",
    )
    offenders = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src/firelens").rglob("*.py")
        if any(host in path.read_text(encoding="utf-8") for host in direct_hosts)
    }
    assert offenders == set()


def test_static_corpus_and_vector_index_identity_are_consistent() -> None:
    corpus_manifest = json.loads(
        (ROOT / "data/processed/firelens_static_corpus.manifest.json").read_text()
    )
    vector_manifest = json.loads(
        (ROOT / "data/index/firelens_vectors.manifest.json").read_text()
    )
    corpus = ROOT / corpus_manifest["combined_chunk_file"]
    rows = [json.loads(line) for line in corpus.read_text().splitlines() if line.strip()]
    chunk_ids = [row["chunk_id"] for row in rows]

    assert corpus_manifest["corpus_version"] == vector_manifest["corpus_version"]
    assert len(rows) == corpus_manifest["combined_chunk_count"]
    assert sum(item.get("chunk_count", 0) for item in corpus_manifest["sources"]) == len(rows)
    assert chunk_ids == vector_manifest["chunk_ids"]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert _sha256(corpus) == vector_manifest["corpus_sha256"]
    assert _sha256(ROOT / "data/index/firelens_vectors.npy") == vector_manifest["matrix_sha256"]
    assert vector_manifest["embedding_model"] == (
        FireLensConfig.model_fields["embedding_model"].default
    )


def test_executable_evaluation_inventory_materials_exist() -> None:
    payload = inventory(ROOT)
    for suite in payload["suites"].values():
        for adapter in suite["adapters"]:
            if adapter["status"] != "executable":
                continue
            assert adapter["effective_status"] == "executable"
            assert all(adapter["material_presence"].values())


def test_pr_main_docs_and_eval_gates_are_explicit_and_fail_closed() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    docs_target = makefile.split("docs-check:", 1)[1].split("\n\n", 1)[0]
    assert "scripts/firelens_agent/docs_drift.py" in docs_target
    assert "tests/test_documentation_consistency.py" in docs_target
    assert "tests/test_firelens_map.py" in docs_target
    assert "check: secret-scan openapi docs-check" in makefile

    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    assert "pull_request:" in workflow
    assert "branches:\n      - main" in workflow
    assert "run: make docs-check" in workflow
    gate = workflow.split("Run zero-cost EvalLab core engineering gate", 1)[1].split(
        "      - name:", 1
    )[0]
    assert "python -m firelens_eval run" in gate and "--suite core" in gate
    assert 'envelope.get("status") == "PASS"' in gate
    assert 'envelope.get("qualification_role") == "zero_cost_engineering_evidence"' in gate
    assert 'identity.get("dirty") is False' in gate
    assert 'execution.get("network_allowed") is False' in gate
    assert 'execution.get("provider_calls_allowed") is False' in gate
    assert 'execution.get("cost_ceiling_usd") == 0.0' in gate
    assert "continue-on-error" not in gate
    assert "|| true" not in gate


def test_agent_guide_commands_match_the_repository_clis() -> None:
    guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    expected = (
        "PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py",
        "PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>",
        'PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "..."',
        "PYTHONPATH=src:tests .venv/bin/python -m firelens_eval inventory",
    )
    assert all(command in guide for command in expected)
    assert "--require-clean" not in guide
    assert "trace_case.py --question" not in guide

    interpreter = ROOT / ".venv/bin/python"
    assert interpreter.is_file()
    environment = {**os.environ, "PYTHONPATH": "src:tests"}
    commands = (
        [str(interpreter), "scripts/firelens_agent/validate_map.py"],
        [
            str(interpreter),
            "scripts/firelens_agent/impact.py",
            "src/firelens/understanding/place.py",
        ],
        [
            str(interpreter),
            "scripts/firelens_agent/trace_case.py",
            "What fires are near Kelowna?",
        ],
        [str(interpreter), "-m", "firelens_eval", "inventory"],
    )
    for command in commands:
        subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
