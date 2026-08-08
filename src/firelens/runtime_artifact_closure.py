"""Compute the exact Python and frontend dependency closure of a staged artifact."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from firelens.runtime_artifact_common import (
    CSS_REFERENCE_PATTERN,
    JS_REFERENCE_PATTERNS,
    HTMLReferences,
    RuntimeArtifactError,
    logical_path,
    read_json,
)


def _module_paths(module: str, files: dict[str, Path], source_root: str) -> set[str]:
    module_parts = module.split(".")
    base = PurePosixPath(source_root, *module_parts)
    candidates = {f"{base.as_posix()}.py", (base / "__init__.py").as_posix()}
    resolved = candidates & set(files)
    if not resolved:
        raise RuntimeArtifactError(
            f"runtime Python import is missing from the artifact: {module}"
        )
    result = set(resolved)
    for depth in range(1, len(module_parts) + 1):
        initializer = PurePosixPath(
            source_root, *module_parts[:depth], "__init__.py"
        ).as_posix()
        if initializer in files:
            result.add(initializer)
    return result


def _python_closure(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    python_contract = contract["python"]
    entrypoint = python_contract["entrypoint"]
    source_root = python_contract["source_root"]
    package = python_contract["package"]
    closure = {entrypoint}
    queue = [entrypoint]
    entry_tree: ast.AST | None = None
    while queue:
        logical = queue.pop()
        try:
            tree = ast.parse(files[logical].read_text(encoding="utf-8"), filename=logical)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise RuntimeArtifactError(
                f"runtime Python file cannot be parsed: {logical}"
            ) from exc
        if logical == entrypoint:
            entry_tree = tree
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(
                    alias.name for alias in node.names if alias.name.startswith(package)
                )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise RuntimeArtifactError(
                        f"relative runtime import is not supported by the verifier: {logical}"
                    )
                if node.module and node.module.startswith(package):
                    modules.add(node.module)
                    for alias in node.names:
                        possible = f"{node.module}.{alias.name}"
                        possible_path = PurePosixPath(source_root, *possible.split("."))
                        if (
                            f"{possible_path.as_posix()}.py" in files
                            or (possible_path / "__init__.py").as_posix() in files
                        ):
                            modules.add(possible)
        for module in modules:
            for dependency in _module_paths(module, files, source_root):
                if dependency not in closure:
                    closure.add(dependency)
                    queue.append(dependency)
    if entry_tree is None:
        raise RuntimeArtifactError("runtime Python entrypoint was not inspected")
    app_values: list[ast.expr | None] = []
    for node in ast.walk(entry_tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "app" for target in node.targets
        ):
            app_values.append(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "app"
        ):
            app_values.append(node.value)
    if not app_values:
        raise RuntimeArtifactError("runtime Python entrypoint does not export app")
    if not any(
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "create_app"
        for value in app_values
    ):
        raise RuntimeArtifactError(
            "runtime Python entrypoint app is not constructed by create_app"
        )
    if not any(path.startswith(f"{source_root}/{package}/") for path in closure):
        raise RuntimeArtifactError("runtime Python entrypoint is not connected to the package")
    return closure


def _resource_path(reference: str, *, source: str, frontend_root: str) -> str | None:
    value = reference.strip()
    if not value or value.startswith("#") or value.lower().startswith("data:"):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("//"):
        raise RuntimeArtifactError(f"frontend reference must be local: {reference}")
    path_value = parsed.path
    if not path_value:
        return None
    if "\\" in path_value or "\x00" in path_value:
        raise RuntimeArtifactError(f"frontend reference is not a POSIX path: {reference}")
    if path_value.startswith("/"):
        candidate = PurePosixPath(frontend_root, path_value.lstrip("/"))
    else:
        candidate = PurePosixPath(source).parent / path_value
    if ".." in candidate.parts:
        raise RuntimeArtifactError(f"frontend reference contains path traversal: {reference}")
    normalized = candidate.as_posix()
    logical_path(normalized, context="frontend reference")
    if normalized != frontend_root and not normalized.startswith(frontend_root + "/"):
        raise RuntimeArtifactError(f"frontend reference escapes its root: {reference}")
    return normalized


def _frontend_closure(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    frontend = contract["frontend"]
    root = frontend["root"]
    index_path = frontend["index"]
    manifest_path = frontend["vite_manifest"]
    frontend_files = {
        logical for logical in files if logical == root or logical.startswith(root + "/")
    }
    allowed_suffixes = tuple(frontend["allowed_suffixes"])
    for logical in frontend_files:
        if not logical.lower().endswith(allowed_suffixes):
            raise RuntimeArtifactError(
                f"frontend artifact has a prohibited file type: {logical}"
            )

    closure = {index_path, manifest_path}
    parser = HTMLReferences()
    try:
        parser.feed(files[index_path].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeArtifactError("frontend index is not readable UTF-8 HTML") from exc
    for reference in parser.references:
        resolved = _resource_path(reference, source=index_path, frontend_root=root)
        if resolved is not None:
            closure.add(resolved)

    manifest = read_json(files[manifest_path], context="Vite manifest")
    if not manifest or "index.html" not in manifest:
        raise RuntimeArtifactError("Vite manifest lacks its index.html entry")
    allowed_entry_fields = {
        "file",
        "name",
        "names",
        "src",
        "isEntry",
        "isDynamicEntry",
        "imports",
        "dynamicImports",
        "css",
        "assets",
    }
    manifest_relations: dict[str, list[str]] = {}
    manifest_outputs: dict[str, list[str]] = {}
    for key, entry in manifest.items():
        if not isinstance(key, str) or not key or not isinstance(entry, dict):
            raise RuntimeArtifactError("Vite manifest entries must be named objects")
        extra = set(entry) - allowed_entry_fields
        if extra:
            raise RuntimeArtifactError(
                f"Vite manifest entry {key} has unsupported fields: {extra}"
            )
        file_value = entry.get("file")
        if not isinstance(file_value, str) or not file_value:
            raise RuntimeArtifactError(f"Vite manifest entry {key} has no output file")
        output_groups: list[list[str]] = []
        for field in ("css", "assets"):
            values = entry.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(reference, str) for reference in values
            ):
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} has invalid {field} outputs"
                )
            output_groups.append(values)
        manifest_outputs[key] = [file_value, *output_groups[0], *output_groups[1]]
        relations: list[str] = []
        for relation in ("imports", "dynamicImports"):
            related = entry.get(relation, [])
            if not isinstance(related, list) or any(
                not isinstance(reference, str) for reference in related
            ):
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} has invalid {relation} references"
                )
            missing_keys = sorted(set(related) - set(manifest))
            if missing_keys:
                raise RuntimeArtifactError(
                    f"Vite manifest entry {key} references missing entries: {missing_keys}"
                )
            relations.extend(related)
        manifest_relations[key] = relations
    if manifest["index.html"].get("isEntry") is not True:
        raise RuntimeArtifactError("Vite index.html entry is not marked as an entrypoint")

    reachable_entries: set[str] = set()
    manifest_queue = ["index.html"]
    while manifest_queue:
        key = manifest_queue.pop()
        if key in reachable_entries:
            continue
        reachable_entries.add(key)
        manifest_queue.extend(manifest_relations[key])
        for reference in manifest_outputs[key]:
            resolved = _resource_path(
                "/" + reference.lstrip("/"), source=index_path, frontend_root=root
            )
            if resolved is not None:
                closure.add(resolved)
    unreachable_entries = sorted(set(manifest) - reachable_entries)
    if unreachable_entries:
        raise RuntimeArtifactError(
            f"Vite manifest contains unreachable entries: {unreachable_entries}"
        )

    queue = list(closure)
    inspected: set[str] = set()
    while queue:
        logical = queue.pop()
        if logical in inspected or logical not in files:
            continue
        inspected.add(logical)
        suffix = PurePosixPath(logical).suffix.lower()
        references: list[str] = []
        if suffix == ".css":
            try:
                text = files[logical].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeArtifactError(f"frontend CSS is not readable: {logical}") from exc
            for match in CSS_REFERENCE_PATTERN.finditer(text):
                references.append(match.group(2) or match.group(4))
        elif suffix == ".js":
            try:
                text = files[logical].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeArtifactError(f"frontend JS is not readable: {logical}") from exc
            for pattern in JS_REFERENCE_PATTERNS:
                references.extend(match.group(2) for match in pattern.finditer(text))
        for reference in references:
            resolved = _resource_path(reference, source=logical, frontend_root=root)
            if resolved is not None and resolved not in closure:
                closure.add(resolved)
                queue.append(resolved)

    missing = sorted(closure - set(files))
    if missing:
        raise RuntimeArtifactError(f"frontend reference closure is missing files: {missing}")
    orphaned = sorted(frontend_files - closure)
    if orphaned:
        raise RuntimeArtifactError(f"frontend bundle contains unreferenced files: {orphaned}")
    return closure


def allowed_files(files: dict[str, Path], contract: dict[str, Any]) -> set[str]:
    """Return the complete frozen allowlist closure for one staged artifact."""

    required = set(contract["required_files"])
    missing = sorted(required - set(files))
    if missing:
        raise RuntimeArtifactError(f"artifact is missing required files: {missing}")
    conditional_path = contract["conditional_files"][0]["logical_path"]
    allowed = required | _python_closure(files, contract) | _frontend_closure(files, contract)
    if conditional_path in files:
        allowed.add(conditional_path)
    return allowed
