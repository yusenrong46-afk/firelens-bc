#!/usr/bin/env python3
"""Measure FireLens code-shape metrics so refactors can be compared honestly.

The numbers are deliberately mechanical (line counts, regex literals, decision
sites) and are meant as a baseline, not a target. Run before and after a change
and diff the two JSON files.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "firelens"
FRONTEND = ROOT / "apps" / "web" / "src"
TESTS = ROOT / "tests"
DIST = ROOT / "apps" / "web" / "dist" / "client"

SEMANTIC_HINTS = ("intent", "grammar", "facet", "location", "clause", "question", "plan")
FALLBACK_NAMES = ("fallback", "compensat", "legacy", "compat")


def _lines(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def _iter_py(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


_REGEX_MARKERS = ("\\b", "(?", "\\s", "\\w", "[^", "\\d", ".*", "|")


class _PyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.regex_literals = 0
        self.pattern_strings = 0
        self.branches = 0
        self.functions = 0
        self.fallback_names = 0

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        value = node.value
        if isinstance(value, str) and len(value) > 3:
            hits = sum(1 for marker in _REGEX_MARKERS if marker in value)
            if hits >= 2 or "(?" in value or "\\b" in value:
                self.pattern_strings += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        name = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "re":
                name = func.attr
        if name in {
            "compile",
            "search",
            "match",
            "fullmatch",
            "sub",
            "findall",
            "finditer",
            "split",
        }:
            self.regex_literals += 1
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self.branches += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:  # noqa: N802
        self.branches += 1
        self.generic_visit(node)

    def _function(self, node: ast.AST) -> None:
        self.functions += 1
        name = getattr(node, "name", "").lower()
        if any(hint in name for hint in FALLBACK_NAMES):
            self.fallback_names += 1
        self.generic_visit(node)

    visit_FunctionDef = _function  # type: ignore[assignment]
    visit_AsyncFunctionDef = _function  # type: ignore[assignment]


def backend_metrics() -> dict[str, object]:
    files = _iter_py(BACKEND)
    per_module: list[dict[str, object]] = []
    totals = {
        "loc": 0,
        "regex_calls": 0,
        "pattern_strings": 0,
        "branches": 0,
        "functions": 0,
        "fallback_named_functions": 0,
    }
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        loc = source.count("\n") + (0 if source.endswith("\n") else 1)
        visitor = _PyVisitor()
        try:
            visitor.visit(ast.parse(source))
        except SyntaxError:
            pass
        rel = str(path.relative_to(ROOT))
        per_module.append(
            {
                "module": rel,
                "loc": loc,
                "regex_calls": visitor.regex_literals,
                "pattern_strings": visitor.pattern_strings,
                "branches": visitor.branches,
                "fallback_named_functions": visitor.fallback_names,
            }
        )
        for key, value in (
            ("loc", loc),
            ("regex_calls", visitor.regex_literals),
            ("pattern_strings", visitor.pattern_strings),
            ("branches", visitor.branches),
            ("functions", visitor.functions),
            ("fallback_named_functions", visitor.fallback_names),
        ):
            totals[key] += value
    production = [
        m
        for m in per_module
        if "/evaluation/" not in str(m["module"])
        and "/review_workspace/" not in str(m["module"])
    ]
    semantic_modules = [
        m["module"]
        for m in production
        if any(h in Path(str(m["module"])).name for h in SEMANTIC_HINTS)
        and (int(m["regex_calls"]) > 0 or int(m["pattern_strings"]) > 0)
    ]
    return {
        "python_loc": totals["loc"],
        "python_loc_excluding_evaluation_and_review": sum(int(m["loc"]) for m in production),
        "modules": len(files),
        "modules_over_500": sorted(str(m["module"]) for m in per_module if int(m["loc"]) > 500),
        "modules_over_650": sorted(str(m["module"]) for m in per_module if int(m["loc"]) > 650),
        "modules_over_800": sorted(str(m["module"]) for m in per_module if int(m["loc"]) > 800),
        "regex_call_sites": totals["regex_calls"],
        "regex_like_string_literals": totals["pattern_strings"],
        "regex_like_string_literals_in_question_modules": sum(
            int(m["pattern_strings"]) for m in production if m["module"] in semantic_modules
        ),
        "if_branches": totals["branches"],
        "functions": totals["functions"],
        "fallback_or_compat_named_functions": totals["fallback_named_functions"],
        "question_interpreting_modules_with_patterns": semantic_modules,
        "top_pattern_modules": sorted(
            (m for m in production if int(m["pattern_strings"]) > 0),
            key=lambda m: -int(m["pattern_strings"]),
        )[:20],
    }


def frontend_metrics() -> dict[str, object]:
    ts_files = sorted(p for p in FRONTEND.rglob("*") if p.suffix in {".ts", ".tsx"})
    css_files = sorted(FRONTEND.rglob("*.css"))
    ts_loc = sum(_lines(p) for p in ts_files if not p.name.endswith(".d.ts"))
    generated_loc = sum(_lines(p) for p in ts_files if p.name.endswith(".d.ts"))
    css_bytes = sum(p.stat().st_size for p in css_files)
    css_loc = sum(_lines(p) for p in css_files)
    css_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in css_files)
    media_queries = len(re.findall(r"@media", css_text))
    overflow_rules = len(
        re.findall(r"overflow(?:-[xy])?\s*:\s*(?:auto|scroll|hidden)", css_text)
    )
    viewport_heights = len(
        re.findall(r"\b(?:100|min-)?(?:d|s|l)?vh\b|height:\s*100(?:d|s|l)?vh", css_text)
    )
    important = len(re.findall(r"!important", css_text))
    selectors = re.findall(r"^\s*([.#][A-Za-z0-9_-]+)[^{]*\{", css_text, flags=re.M)
    from collections import Counter

    counts = Counter(selectors)
    redefined = sum(1 for _, n in counts.items() if n > 1)
    ts_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in ts_files
        if not p.name.endswith(".d.ts")
    )
    scroll_js = len(re.findall(r"scrollTo\(|scrollIntoView|scrollTop\s*[+-]?=", ts_text))
    bundle: dict[str, object] = {}
    if DIST.exists():
        assets = sorted((DIST / "assets").glob("*"))
        bundle = {
            "js": {p.name: p.stat().st_size for p in assets if p.suffix == ".js"},
            "css": {p.name: p.stat().st_size for p in assets if p.suffix == ".css"},
            "total_js_bytes": sum(p.stat().st_size for p in assets if p.suffix == ".js"),
            "total_css_bytes": sum(p.stat().st_size for p in assets if p.suffix == ".css"),
        }
    return {
        "ts_tsx_loc_handwritten": ts_loc,
        "generated_api_schema_loc": generated_loc,
        "css_files": [str(p.relative_to(ROOT)) for p in css_files],
        "css_loc": css_loc,
        "css_bytes": css_bytes,
        "media_queries": media_queries,
        "overflow_auto_scroll_hidden_rules": overflow_rules,
        "viewport_height_units": viewport_heights,
        "important_declarations": important,
        "selectors_defined_more_than_once": redefined,
        "js_scroll_corrections": scroll_js,
        "bundle": bundle,
    }


def evaluation_metrics() -> dict[str, object]:
    test_files = _iter_py(TESTS)
    test_functions = 0
    for path in test_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test"):
                test_functions += 1
    web_tests = sorted((ROOT / "apps" / "web" / "tests").rglob("*.ts*"))
    e2e = [p for p in web_tests if "e2e" in p.parts]
    return {
        "python_test_files": len(test_files),
        "python_test_functions": test_functions,
        "python_test_loc": sum(_lines(p) for p in test_files),
        "frontend_test_files": len(web_tests),
        "browser_journey_files": [str(p.relative_to(ROOT)) for p in e2e],
        "eval_scripts": len(list((ROOT / "scripts").glob("*.py"))),
    }


def main() -> int:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    report = {
        "commit": sha,
        "backend": backend_metrics(),
        "frontend": frontend_metrics(),
        "evaluation": evaluation_metrics(),
    }
    out = sys.argv[1] if len(sys.argv) > 1 else None
    text = json.dumps(report, indent=2, sort_keys=True)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
