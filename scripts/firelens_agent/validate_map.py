#!/usr/bin/env python3
"""Validate generated FireLens map freshness and referential integrity."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PREFIXES = (
    "app.py",
    "src/",
    "tests/",
    "scripts/",
    "apps/web/",
    "benchmarks/",
    "evals/",
    "docs/reports/",
)
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
MAP_METADATA_INPUTS = (
    "pyproject.toml",
    "apps/web/package.json",
    "docs/openapi.v1.json",
)
FAMILY_HINTS = (
    "architecture",
    "claimbench",
    "conversation",
    "fable",
    "fault",
    "firelens200",
    "frontend",
    "hard_probe",
    "intent",
    "judge",
    "live",
    "metamorphic",
    "mutation",
    "pacific_clarity",
    "performance",
    "privacy",
    "productbench",
    "provider",
    "publication",
    "rag",
    "retrieval",
    "safety",
    "source_aware",
    "spatial",
    "trajectory",
)
PY_BRANCHES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.BoolOp,
    ast.IfExp,
    ast.Match,
    ast.comprehension,
)


def source_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    names = sorted(item for item in result.stdout.decode().split("\0") if item)
    return [
        root / name
        for name in names
        if name.startswith(SOURCE_PREFIXES)
        and Path(name).suffix in SOURCE_SUFFIXES
        and (root / name).is_file()
    ]


def source_digest(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    inputs = sorted((*paths, *(root / name for name in MAP_METADATA_INPUTS)))
    for path in inputs:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if parts and parts[0] == "src":
        parts.pop(0)
    return ".".join(parts)


def module_kind(path: str) -> str:
    if path.startswith(("tests/", "apps/web/tests/")):
        return "test"
    if path.startswith(
        ("benchmarks/", "evals/", "src/firelens_eval/", "src/firelens/evaluation/")
    ):
        return "evaluation"
    if path.startswith("docs/reports/"):
        return "historical"
    if path.startswith(("scripts/", "apps/web/scripts/")):
        return "script"
    if path.startswith("apps/web/") and not path.startswith("apps/web/src/"):
        return "config"
    return "production"


def _symbol(node: ast.AST, name: str, qualname: str, kind: str) -> dict[str, Any]:
    return {
        "name": name,
        "qualname": qualname,
        "kind": kind,
        "line": node.lineno,
        "end_line": node.end_lineno,
        "public": not name.startswith("_"),
        "major": kind in {"class", "function"} and not name.startswith("_"),
        "branch_score": sum(isinstance(item, PY_BRANCHES) for item in ast.walk(node)),
    }


def python_data(
    path: Path, root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    symbols: list[dict[str, Any]] = []

    def collect(body: list[ast.stmt], prefix: str = "", in_class: bool = False) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                qualname = f"{prefix}.{node.name}" if prefix else node.name
                symbols.append(_symbol(node, node.name, qualname, "class"))
                collect(node.body, qualname, True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}.{node.name}" if prefix else node.name
                kind = "method" if in_class else "function" if not prefix else "nested_function"
                symbols.append(_symbol(node, node.name, qualname, kind))
                collect(node.body, qualname)

    collect(tree.body)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                {"name": alias.name, "level": 0, "aliases": [], "line": node.lineno}
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                {
                    "name": node.module or "",
                    "level": node.level,
                    "aliases": [alias.name for alias in node.names],
                    "line": node.lineno,
                }
            )
    relative = path.relative_to(root).as_posix()
    record = {
        "id": relative,
        "path": relative,
        "module": _module_name(path, root),
        "language": "python",
        "kind": module_kind(relative),
        "loc": len(text.splitlines()),
        "branch_score": sum(isinstance(item, PY_BRANCHES) for item in ast.walk(tree)),
        "generated": False,
        "symbols": [item["qualname"] for item in symbols],
        "major_symbols": [item["qualname"] for item in symbols if item["major"]],
    }
    return record, symbols, imports


def resolve_python(
    source: dict[str, Any], raw: dict[str, Any], known: dict[str, str]
) -> list[str]:
    package = (
        source["module"]
        if source["path"].endswith("/__init__.py")
        else source["module"].rpartition(".")[0]
    )
    name = raw["name"]
    if raw["level"]:
        try:
            name = importlib.util.resolve_name("." * raw["level"] + name, package)
        except (ImportError, ValueError):
            return []
    candidates = [f"{name}.{alias}" for alias in raw["aliases"]] or [name]
    resolved = set()
    for candidate in candidates:
        probe = candidate
        while probe:
            if probe in known:
                resolved.add(known[probe])
                break
            probe = probe.rpartition(".")[0]
    return sorted(resolved)


def evaluation_families(path: str, text: str) -> list[str]:
    haystack = f"{path}\n{text}".casefold()
    return [hint for hint in FAMILY_HINTS if hint in haystack]


def validate_repository_map(root: Path = ROOT) -> list[str]:
    if __package__:
        from .build_map import OUTPUT_NAMES, build_artifacts
        from .impact import CAPABILITIES, INVARIANTS, OWNERSHIP
    else:
        from build_map import OUTPUT_NAMES, build_artifacts
        from impact import CAPABILITIES, INVARIANTS, OWNERSHIP

    expected = build_artifacts(root)
    directory = root / "docs/firelens-map"
    findings = []
    for name in OUTPUT_NAMES:
        path = directory / name
        if not path.is_file():
            findings.append(f"missing generated artifact: {path.relative_to(root)}")
        elif path.read_text(encoding="utf-8") != expected[name]:
            findings.append(f"generated artifact drift: {path.relative_to(root)}")
    if findings:
        return findings
    modules = json.loads(expected["module-index.json"])
    symbols = json.loads(expected["symbol-index.json"])
    graph = json.loads(expected["import-graph.json"])
    tests = json.loads(expected["test-map.json"])
    paths = {item["path"] for item in modules["modules"]}
    if set(graph["nodes"]) != paths:
        findings.append("import graph nodes differ from module index")
    for edge in graph["edges"]:
        if edge["source"] not in paths or edge["target"] not in paths:
            findings.append(f"unresolved graph endpoint: {edge}")
    edge_ids = [(item["source"], item["target"]) for item in graph["edges"]]
    if len(edge_ids) != len(set(edge_ids)):
        findings.append("import graph contains duplicate source-target edges")
    for symbol in symbols["symbols"]:
        if symbol["module_path"] not in paths:
            findings.append(f"symbol references unknown module: {symbol['id']}")
    symbol_ids = [item["id"] for item in symbols["symbols"]]
    if len(symbol_ids) != len(set(symbol_ids)):
        findings.append("symbol ids are not unique")
    for test in tests["tests"]:
        if test["path"] not in paths or any(
            item not in paths for item in test["direct_targets"]
        ):
            findings.append(f"test references unknown module: {test['path']}")
    owners = {item["id"] for item in OWNERSHIP}
    for domain in OWNERSHIP:
        for path in domain["primary"] + domain["projections"] + domain["duplicates"]:
            if not (root / path).is_file():
                findings.append(f"ownership path does not exist: {path}")
    for invariant in INVARIANTS:
        if invariant["owner"] not in owners:
            findings.append(f"invariant owner does not exist: {invariant['id']}")
        for path in invariant["tests"]:
            if not (root / path).is_file():
                findings.append(f"invariant test does not exist: {path}")
    endpoints = set(modules["endpoints"])
    for capability in CAPABILITIES:
        if capability["owner"] not in owners:
            findings.append(f"capability owner does not exist: {capability['id']}")
        if capability["endpoint"] not in endpoints:
            findings.append(f"capability endpoint does not exist: {capability['endpoint']}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    findings = validate_repository_map()
    if findings:
        raise SystemExit("FireLens map validation failed:\n" + "\n".join(findings))
    print("FireLens map is deterministic, current, and internally consistent.")


if __name__ == "__main__":
    main()
