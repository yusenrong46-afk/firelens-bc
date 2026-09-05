#!/usr/bin/env python3
"""Build deterministic, offline repository-intelligence artifacts for FireLens."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__:
    from . import docs_drift
    from .impact import CAPABILITIES, INVARIANTS, OWNERSHIP
    from .validate_map import (
        SOURCE_PREFIXES,
        evaluation_families,
        python_data,
        resolve_python,
        source_digest,
        source_files,
    )
else:
    import docs_drift
    from impact import CAPABILITIES, INVARIANTS, OWNERSHIP
    from validate_map import (
        SOURCE_PREFIXES,
        evaluation_families,
        python_data,
        resolve_python,
        source_digest,
        source_files,
    )

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_NAMES = (
    "README.md",
    "module-index.json",
    "symbol-index.json",
    "import-graph.json",
    "test-map.json",
    "ownership.yaml",
    "invariants.yaml",
    "capability-map.yaml",
    "complexity.json",
    "request-lifecycle.md",
)


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_artifacts(root: Path = ROOT) -> dict[str, str]:
    paths = source_files(root)
    digest = source_digest(paths, root)
    modules, symbols, raw_by_path = [], [], {}
    for path in paths:
        record, found, raw = (
            python_data(path, root)
            if path.suffix == ".py"
            else docs_drift.typescript_data(path, root)
        )
        modules.append(record)
        raw_by_path[record["path"]] = raw
        symbols.extend(
            {
                **item,
                "id": f"{record['path']}::{item['qualname']}:{item['line']}",
                "module_path": record["path"],
                "language": record["language"],
            }
            for item in found
        )
    modules.sort(key=lambda item: item["path"])
    symbols.sort(key=lambda item: item["id"])
    by_path = {item["path"]: item for item in modules}
    python_known = {
        item["module"]: item["path"] for item in modules if item["language"] == "python"
    }
    edge_lines: dict[tuple[str, str], set[int]] = defaultdict(set)
    unresolved = []
    for source in modules:
        for raw in raw_by_path[source["path"]]:
            targets = (
                resolve_python(source, raw, python_known)
                if source["language"] == "python"
                else [docs_drift.resolve_typescript(source["path"], raw["name"], set(by_path))]
            )
            resolved = [target for target in targets if target and target != source["path"]]
            for target in resolved:
                edge_lines[(source["path"], target)].add(raw["line"])
            if not resolved and raw["name"].startswith("."):
                unresolved.append(
                    {"source": source["path"], "specifier": raw["name"], "line": raw["line"]}
                )
    edge_rows = [
        {"source": source, "target": target, "lines": sorted(lines), "kind": "static"}
        for (source, target), lines in sorted(edge_lines.items())
    ]
    fan_in = Counter(edge["target"] for edge in edge_rows)
    fan_out = Counter(edge["source"] for edge in edge_rows)
    production_fan_in = Counter(
        edge["target"] for edge in edge_rows if by_path[edge["source"]]["kind"] == "production"
    )
    test_fan_in = Counter(
        edge["target"] for edge in edge_rows if by_path[edge["source"]]["kind"] == "test"
    )
    for module in modules:
        module["import_specifiers"] = sorted(
            {item["name"] for item in raw_by_path[module["path"]]}
        )
        module["imports"] = sorted(
            {edge["target"] for edge in edge_rows if edge["source"] == module["path"]}
        )
        module["fan_in"] = fan_in[module["path"]]
        module["fan_out"] = fan_out[module["path"]]
        module["production_fan_in"] = production_fan_in[module["path"]]
        module["test_fan_in"] = test_fan_in[module["path"]]
        module["statically_unreferenced"] = fan_in[module["path"]] == 0
    openapi = json.loads((root / "docs/openapi.v1.json").read_text(encoding="utf-8"))
    endpoints = sorted(
        f"{method.upper()} {route}"
        for route, methods in openapi["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    )
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    tests = []
    for module in modules:
        if module["kind"] != "test":
            continue
        text = (root / module["path"]).read_text(encoding="utf-8")
        cases = (
            [
                item["qualname"]
                for item in symbols
                if item["module_path"] == module["path"] and item["name"].startswith("test")
            ]
            if module["language"] == "python"
            else [
                f"test_call_{index}"
                for index in range(
                    1, len(re.findall(r"\b(?:test|it)(?:\.(?:skip|only|todo))?\s*\(", text)) + 1
                )
            ]
        )
        tests.append(
            {
                "path": module["path"],
                "language": module["language"],
                "cases": cases,
                "direct_targets": [
                    target
                    for target in module["imports"]
                    if by_path[target]["kind"] == "production"
                ],
                "endpoints": [
                    endpoint for endpoint in endpoints if endpoint.split(" ", 1)[1] in text
                ],
                "evaluation_families": evaluation_families(module["path"], text),
            }
        )
    envelope = {
        "source_digest": digest,
        "generator": "scripts/firelens_agent/build_map.py",
    }
    module_index = {
        **envelope,
        "schema_version": "firelens.module_index.v1",
        "roots": list(SOURCE_PREFIXES),
        "modules": modules,
        "endpoints": endpoints,
        "dependencies": {
            "python": pyproject["project"]["dependencies"],
            "python_optional": pyproject["project"].get("optional-dependencies", {}),
            "web": package["dependencies"],
            "web_dev": package["devDependencies"],
        },
    }
    symbol_index = {
        **envelope,
        "schema_version": "firelens.symbol_index.v1",
        "symbols": symbols,
    }
    graph = {
        **envelope,
        "schema_version": "firelens.import_graph.v1",
        "nodes": [item["path"] for item in modules],
        "edges": edge_rows,
        "scope_note": "CSS, JSON, and other non-code relative imports are intentionally unresolved.",
        "unresolved_relative_imports": sorted(
            unresolved, key=lambda item: tuple(item.values())
        ),
    }
    test_map = {
        **envelope,
        "schema_version": "firelens.test_map.v1",
        "tests": tests,
        "coverage_note": "Cases are static declarations/call sites; family labels are substring hints and direct imports are not proof of semantic coverage.",
    }
    hotspot_rows = [
        {key: item[key] for key in ("path", "loc", "branch_score")}
        for item in modules
        if item["kind"] == "production" and not item["generated"]
    ]
    complexity = {
        **envelope,
        "schema_version": "firelens.complexity.v1",
        "metric": {
            "python": "AST decision-node count",
            "typescript": "lexical decision-token count",
        },
        "thresholds": {
            "production_python_loc": 800,
            "feature_tsx_loc": 300,
            "agent_loop_loc": 350,
        },
        "top_production_by_loc": sorted(
            hotspot_rows, key=lambda item: (-item["loc"], item["path"])
        )[:25],
        "top_production_by_branch": sorted(
            hotspot_rows, key=lambda item: (-item["branch_score"], item["path"])
        )[:25],
        "modules": [
            {key: item[key] for key in ("path", "loc", "branch_score")} for item in modules
        ],
        "symbols": [
            {key: item[key] for key in ("id", "module_path", "branch_score")}
            for item in symbols
            if item["kind"] in {"function", "method"}
        ],
    }
    semantic = {
        "source_digest": digest,
        "authority_note": "These are engineering navigation contracts, not qualification or release evidence.",
    }
    ownership = {
        "schema_version": "firelens.ownership.v1",
        **semantic,
        "domains": list(OWNERSHIP),
    }
    invariants = {
        "schema_version": "firelens.invariants.v1",
        **semantic,
        "invariants": list(INVARIANTS),
    }
    capabilities = {
        "schema_version": "firelens.capability_map.v1",
        **semantic,
        "capabilities": list(CAPABILITIES),
    }
    prod_py = sum(
        item["language"] == "python" and item["kind"] == "production" for item in modules
    )
    prod_ts = sum(
        item["language"] == "typescript" and item["kind"] == "production" for item in modules
    )
    readme = docs_drift.render_readme(digest, prod_py, prod_ts, len(tests), len(edge_rows))
    lifecycle = docs_drift.render_lifecycle(digest)
    return {
        "README.md": readme,
        "module-index.json": _json(module_index),
        "symbol-index.json": _json(symbol_index),
        "import-graph.json": _json(graph),
        "test-map.json": _json(test_map),
        "ownership.yaml": docs_drift.render_yaml(ownership),
        "invariants.yaml": docs_drift.render_yaml(invariants),
        "capability-map.yaml": docs_drift.render_yaml(capabilities),
        "complexity.json": _json(complexity),
        "request-lifecycle.md": lifecycle,
    }


def write_artifacts(root: Path = ROOT, output: Path | None = None) -> list[Path]:
    destination = output or root / "docs/firelens-map"
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts(root)
    written = []
    for name in OUTPUT_NAMES:
        path = destination / name
        path.write_text(artifacts[name], encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    for path in write_artifacts(ROOT, args.output):
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


if __name__ == "__main__":
    main()
