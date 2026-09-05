#!/usr/bin/env python3
"""Detect generated-map, code-reference, and documentation drift offline."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if __package__:
    from .validate_map import module_kind
else:
    from validate_map import module_kind

ROOT = Path(__file__).resolve().parents[2]
TS_IMPORT = re.compile(
    r"(?:\b(?:import|export)\s+(?:type\s+)?[^;]*?\sfrom\s*|\bimport\s*)"
    r"[\"'](?P<name>[^\"']+)[\"']|\bimport\(\s*[\"'](?P<dynamic>[^\"']+)[\"']"
)
TS_SYMBOL = re.compile(
    r"^(?P<export>export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?P<kind>function|class|interface|type|enum|const|let|var)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
SIZE_ROW = re.compile(
    r"^\|\s*`(?P<path>[^`]+\.py)`\s*\|\s*[^|]+\|\s*(?P<current>[0-9,]+)\s*\|",
    re.MULTILINE,
)
MARKDOWN_LINK = re.compile(r"(?P<image>!)?\[[^\]]*\]\((?P<target>[^)\n]+)\)")
LINKED_SYMBOL = re.compile(
    r"\[[^\]]+\]\((?P<target>[^)#?]+\.(?:py|js|jsx|mjs|ts|tsx))\)"
    r"\s+`(?P<symbol>[A-Za-z_$][\w.$]*)`"
)


def render_yaml(payload: dict[str, Any]) -> str:
    lines: list[str] = []

    def scalar(value: Any) -> str:
        if value == []:
            return "[]"
        if value == {}:
            return "{}"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value), ensure_ascii=False)

    def populated_container(value: Any) -> bool:
        return isinstance(value, (dict, list)) and bool(value)

    def emit(value: Any, indent: int) -> None:
        prefix = " " * indent
        if isinstance(value, dict):
            for key in sorted(value):
                child = value[key]
                if populated_container(child):
                    lines.append(f"{prefix}{key}:")
                    emit(child, indent + 2)
                else:
                    lines.append(f"{prefix}{key}: {scalar(child)}")
            return
        for child in value:
            if populated_container(child):
                lines.append(f"{prefix}-")
                emit(child, indent + 2)
            else:
                lines.append(f"{prefix}- {scalar(child)}")

    emit(payload, 0)
    return "\n".join(lines) + "\n"


def typescript_data(
    path: Path, root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    symbols = [
        {
            "name": match.group("name"),
            "qualname": match.group("name"),
            "kind": match.group("kind"),
            "line": text.count("\n", 0, match.start()) + 1,
            "end_line": text.count("\n", 0, match.start()) + 1,
            "public": match.group("export") is not None,
            "major": match.group("export") is not None
            or match.group("kind") in {"class", "interface", "type", "enum"}
            or match.group("name")[0].isupper(),
            "branch_score": 0,
        }
        for match in TS_SYMBOL.finditer(text)
    ]
    imports = [
        {
            "name": match.group("name") or match.group("dynamic"),
            "line": text.count("\n", 0, match.start()) + 1,
        }
        for match in TS_IMPORT.finditer(text)
    ]
    branch_pattern = r"\b(?:if|for|while|case|catch)\b|\?\?|&&|\|\||(?<!\?)\?(?![.?])"
    language = "typescript" if path.suffix in {".ts", ".tsx"} else "javascript"
    record = {
        "id": relative,
        "path": relative,
        "module": relative.removesuffix(".d.ts").rsplit(".", 1)[0],
        "language": language,
        "kind": module_kind(relative),
        "loc": len(text.splitlines()),
        "branch_score": len(re.findall(branch_pattern, text)),
        "generated": relative.endswith(".d.ts"),
        "symbols": [item["qualname"] for item in symbols],
        "major_symbols": [item["qualname"] for item in symbols if item["major"]],
    }
    return record, symbols, imports


def resolve_typescript(source: str, specifier: str, known: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    base = posixpath.normpath((Path(source).parent / specifier.split("?", 1)[0]).as_posix())
    candidates = (
        base,
        f"{base}.ts",
        f"{base}.tsx",
        f"{base}.d.ts",
        f"{base}.js",
        f"{base}.jsx",
        f"{base}.mjs",
        f"{base}/index.ts",
        f"{base}/index.tsx",
        f"{base}/index.js",
    )
    return next((candidate for candidate in candidates if candidate in known), None)


def render_readme(
    digest: str, python_modules: int, typescript_modules: int, tests: int, edges: int
) -> str:
    return f"""# FireLens engineering map

Deterministic, offline navigation index for the current source content. It is not runtime, qualification, deployment, or release evidence. Source digest: `{digest}`.

Inventory: {python_modules} production Python modules, {typescript_modules} production TS/TSX modules,
{tests} test modules, and {edges} resolved internal import edges.

Generate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py`; validate with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py`.
Inspect impact with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>`; inspect a planning trace with `PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "<question>"`.
Traces redact question- and location-derived values unless `--include-question` is explicitly supplied. Impact also accepts semantic owner IDs such as `location_resolution`.

Machine-generated JSON owns structure and graph facts. Semantic YAML is serialized as YAML
from curated declarations in `impact.py`; ownership cannot be inferred from fan-in alone.
Major-symbol flags are heuristic, and `statically_unreferenced` is a lead rather than proof of
dead code because framework, CLI, and dynamic entry points may not have import edges.

Fix the first structured divergence and preserve separate release authority.
"""


def render_lifecycle(digest: str) -> str:
    return f"""# Public Ask request lifecycle

Source digest: `{digest}`. This is a navigation trace, not executed evidence.

1. `api/answer_routes.py` applies readiness and deadline boundaries.
2. `agent/coordinator.py` builds the immutable `AgentQueryPlan`.
3. `agent/prefetch.py` executes plan-authorized work through `live.py`'s `LiveDataService` and `answering/service.py`'s `StaticRAGService`.
4. `agent/loop.py` skips provider prose for application-owned responses; otherwise it permits bounded
   writing, one repair, then deterministic fallback.
5. `publication/compiler.py` and `compiled_validation.py` own publishable structured facts.
6. `agent/compose.py` creates `AskResponse`; `proof_presentation.py` binds proof projections.
7. The web client renders the response and must fail closed rather than strengthen authority.

| Trigger | Result |
| --- | --- |
| Runtime absent or deadline exceeded | Typed HTTP 503 |
| Provider unavailable | Deterministic response or official-source handoff |
| Retrieval incomplete | Typed unavailable; retained candidates are not complete support |
| Generated draft rejected | One repair, safe salvage, exact-source compiler, or abstention |
| Live records empty/unavailable | Explicit limitation; never an all-clear |
| Proof authority missing/mismatched | Unknown/rejected presentation |
"""


def architecture_size_findings(root: Path = ROOT) -> list[str]:
    document = root / "docs/ARCHITECTURE_V1_6.md"
    if not document.is_file():
        return ["missing architecture authority: docs/ARCHITECTURE_V1_6.md"]
    findings = []
    for match in SIZE_ROW.finditer(document.read_text(encoding="utf-8")):
        relative = match.group("path")
        path = root / relative
        if not path.is_file():
            findings.append(f"documented module does not exist: {relative}")
            continue
        documented = int(match.group("current").replace(",", ""))
        actual = len(path.read_text(encoding="utf-8").splitlines())
        if documented != actual:
            findings.append(
                f"documented LOC drift: {relative} says {documented}, actual {actual}"
            )
    return findings


def _local_target(root: Path, document: Path, raw: str) -> Path | None:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        value = value[1 : value.index(">")]
    else:
        value = value.split(maxsplit=1)[0]
    if value.startswith("#") or re.match(r"^[a-z][a-z0-9+.-]*:", value, re.I):
        return None
    value = unquote(value.split("#", 1)[0].split("?", 1)[0])
    base = root if value.startswith("/") else document.parent
    return (base / value.lstrip("/")).resolve()


def documentation_reference_findings(root: Path = ROOT) -> list[str]:
    symbol_index = root / "docs/firelens-map/symbol-index.json"
    if not symbol_index.is_file():
        return []
    fresh_symbols = json.loads(symbol_index.read_text(encoding="utf-8"))["symbols"]
    by_path: dict[str, set[str]] = {}
    for symbol in fresh_symbols:
        by_path.setdefault(symbol["module_path"], set()).update(
            (symbol["name"], symbol["qualname"])
        )
    documents = [path for path in (root / "README.md", root / "AGENTS.md") if path.is_file()]
    documents += sorted((root / "docs").rglob("*.md"))
    documents += sorted((root / ".agents").rglob("*.md"))
    findings = []
    for document in documents:
        fenced = False
        relative_document = document.relative_to(root).as_posix()
        for line_number, line in enumerate(
            document.read_text(encoding="utf-8").splitlines(), 1
        ):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            if fenced:
                continue
            where = f"{relative_document}:{line_number}"
            for match in MARKDOWN_LINK.finditer(line):
                target = _local_target(root, document, match.group("target"))
                if target is None:
                    continue
                if not target.is_relative_to(root):
                    findings.append(f"internal link escapes repository: {where}")
                    continue
                relative = target.relative_to(root).as_posix()
                if not target.exists():
                    findings.append(f"broken internal link: {where} -> {relative}")
                elif match.group("image") and target.is_file() and target.stat().st_size == 0:
                    findings.append(f"empty linked image: {where} -> {relative}")
            for match in LINKED_SYMBOL.finditer(line):
                target = _local_target(root, document, match.group("target"))
                if target is None or not target.is_file():
                    continue
                if not target.is_relative_to(root):
                    continue
                relative = target.relative_to(root).as_posix()
                available = by_path.get(relative, set())
                named = match.group("symbol")
                if named not in available and not any(
                    item.endswith(f".{named}") for item in available
                ):
                    findings.append(f"deleted linked symbol: {where} -> {relative}::{named}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-only", action="store_true")
    args = parser.parse_args()
    if __package__:
        from .validate_map import validate_repository_map
    else:
        from validate_map import validate_repository_map

    findings = validate_repository_map()
    if not args.map_only:
        findings.extend(architecture_size_findings())
        if not findings:
            findings.extend(documentation_reference_findings())
    if findings:
        raise SystemExit("Documentation drift detected:\n" + "\n".join(findings))
    print("Generated map and checked documentation are current.")


if __name__ == "__main__":
    main()
