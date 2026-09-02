from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src/firelens"
WEB_ROOT = ROOT / "apps/web/src"
SCRIPTS_ROOT = ROOT / "scripts"
V16_STARTING_COMMIT = "3de745a22ad0801e19563f90ac64f18609ecae03"
# Documented in docs/ARCHITECTURE_V1_6.md. These files were already large
# before V1.6; the campaign edited them without a full rewrite.
V16_MODIFIED_MODULE_EXCEPTIONS = frozenset(
    {
        "src/firelens/agent/compose.py",
        "src/firelens/answering/live_analysis.py",
        "src/firelens/answering/service.py",
        "src/firelens/contracts.py",
        "src/firelens/evaluation/capture.py",
        "src/firelens/evaluation/release_surfaces.py",
        "src/firelens/live.py",
        "src/firelens/review_workspace/cli.py",
        "src/firelens/review_workspace/inputs.py",
        "src/firelens/runtime_artifact.py",
    }
)


def _local_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name.startswith("firelens")
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("firelens"):
                imports.add(node.module)
    return imports


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(("firelens", *parts))


def test_python_package_has_no_circular_imports() -> None:
    files = tuple(PACKAGE_ROOT.rglob("*.py"))
    known = {_module_name(path): path for path in files}
    graph = {
        module: {dependency for dependency in _local_imports(path) if dependency in known}
        for module, path in known.items()
    }
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            cycle = " -> ".join((*visiting[visiting.index(module) :], module))
            raise AssertionError(f"circular FireLens import: {cycle}")
        if module in visited:
            return
        visiting.append(module)
        for dependency in sorted(graph[module]):
            visit(dependency)
        visiting.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)


def test_foundation_packages_do_not_import_high_level_product_layers() -> None:
    forbidden_roots = {
        "contracts.py": ("firelens.api", "firelens.answering", "firelens.live"),
        "providers": ("firelens.api", "firelens.answering", "firelens.live"),
        "retrieval": ("firelens.api", "firelens.answering", "firelens.live"),
        "ingestion": ("firelens.api", "firelens.answering", "firelens.live"),
    }
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        boundary = relative.parts[0]
        prefixes = forbidden_roots.get(boundary)
        if prefixes is None:
            continue
        for imported in sorted(_local_imports(path)):
            if any(
                imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes
            ):
                violations.append(f"{relative}: {imported}")
    assert not violations, "forbidden dependency direction:\n" + "\n".join(violations)


def test_react_feature_components_stay_below_300_lines() -> None:
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in (WEB_ROOT / "features").rglob("*.tsx")
        if len(path.read_text(encoding="utf-8").splitlines()) > 300
    }
    assert not violations, f"React feature components exceed 300 lines: {violations}"


def test_api_modules_stay_below_300_lines() -> None:
    api_root = PACKAGE_ROOT / "api"
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in api_root.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 300
    }
    assert not violations, f"API modules exceed 300 lines: {violations}"


def test_all_production_python_modules_stay_below_800_lines() -> None:
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in PACKAGE_ROOT.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"production Python modules exceed 800 lines: {violations}"


def test_agent_loop_stays_below_350_lines() -> None:
    path = PACKAGE_ROOT / "agent/loop.py"
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 350, f"src/firelens/agent/loop.py is {lines} lines"


def _v16_modified_production_modules() -> frozenset[str]:
    named = subprocess.run(
        ["git", "diff", "--name-only", V16_STARTING_COMMIT, "--", "src/firelens"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "src/firelens"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {
        relative
        for relative in (*named.stdout.splitlines(), *untracked.stdout.splitlines())
        if relative.endswith(".py") and (ROOT / relative).is_file()
    }
    return frozenset(paths)


def test_v1_6_modified_modules_stay_below_650_unless_excepted() -> None:
    violations: dict[str, int] = {}
    excepted: dict[str, int] = {}
    for relative in sorted(_v16_modified_production_modules()):
        lines = len((ROOT / relative).read_text(encoding="utf-8").splitlines())
        if relative in V16_MODIFIED_MODULE_EXCEPTIONS:
            excepted[relative] = lines
            continue
        if lines > 650:
            violations[relative] = lines
    assert not violations, (
        "V1.6 modified production modules exceed 650 lines without a written "
        f"exception in docs/ARCHITECTURE_V1_6.md: {violations}"
    )
    missing = V16_MODIFIED_MODULE_EXCEPTIONS - frozenset(excepted)
    assert not missing, f"documented V1.6 size exceptions are missing from the tree: {missing}"
    over_cap = {path: count for path, count in excepted.items() if count > 800}
    assert not over_cap, f"excepted modules still must stay under 800 lines: {over_cap}"


def test_upgrade_benchmark_tests_are_split_below_1200_lines() -> None:
    tests_root = ROOT / "tests"
    paths = (
        *sorted(tests_root.glob("test_upgrade_benchmark*.py")),
        *sorted(tests_root.glob("upgrade_benchmark_support*.py")),
    )
    assert (tests_root / "test_upgrade_benchmark.py").is_file()
    assert (tests_root / "upgrade_benchmark_support.py").is_file()
    assert len(tuple(tests_root.glob("test_upgrade_benchmark*.py"))) >= 5
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 1200
    }
    assert not violations, f"upgrade-benchmark test files exceed 1200 lines: {violations}"


def test_executable_scripts_stay_below_300_lines() -> None:
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in SCRIPTS_ROOT.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 300
    }
    assert not violations, f"executable scripts exceed 300 lines: {violations}"


def test_live_adapter_modules_stay_below_800_lines() -> None:
    paths = (PACKAGE_ROOT / "live.py", PACKAGE_ROOT / "live_support.py")
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"live adapter modules exceed 800 lines: {violations}"


def test_contract_modules_stay_below_800_lines() -> None:
    paths = (
        PACKAGE_ROOT / "contracts.py",
        PACKAGE_ROOT / "contract_base.py",
        PACKAGE_ROOT / "live_contracts.py",
    )
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"contract modules exceed 800 lines: {violations}"


def test_answering_modules_stay_below_800_lines() -> None:
    answering_root = PACKAGE_ROOT / "answering"
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in answering_root.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"answering modules exceed 800 lines: {violations}"


def test_provider_modules_stay_below_800_lines() -> None:
    provider_root = PACKAGE_ROOT / "providers"
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in provider_root.rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"provider modules exceed 800 lines: {violations}"


def test_runtime_artifact_modules_stay_below_800_lines() -> None:
    paths = PACKAGE_ROOT.glob("runtime_artifact*.py")
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"runtime artifact modules exceed 800 lines: {violations}"


def test_benchmark_modules_stay_below_800_lines() -> None:
    paths = PACKAGE_ROOT.glob("benchmark*.py")
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"benchmark modules exceed 800 lines: {violations}"


def test_review_input_modules_stay_below_800_lines() -> None:
    paths = (PACKAGE_ROOT / "review_workspace").glob("input*.py")
    violations = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not violations, f"review input modules exceed 800 lines: {violations}"


def test_frontend_features_do_not_depend_on_app_or_prototype_paths() -> None:
    violations: list[str] = []
    for path in WEB_ROOT.rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        is_feature = (WEB_ROOT / "features") in path.parents
        if (is_feature and "/app/" in text) or "prototype/" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"frontend boundary violation: {violations}"
