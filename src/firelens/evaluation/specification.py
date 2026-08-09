"""Load and validate the frozen upgrade benchmark specification."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from firelens.evaluation.spec_models import BenchmarkSpec, DatasetRoleRegistry


def load_dataset_role_registry(
    path: Path,
    *,
    repository_root: Path,
) -> DatasetRoleRegistry:
    """Load dataset roles and reject declared inputs that are not present."""

    registry = DatasetRoleRegistry.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    for dataset in registry.datasets:
        if dataset.status != "available":
            continue
        for relative in dataset.inputs:
            if not (repository_root / relative).is_file():
                raise ValueError(f"available dataset-role input does not exist: {relative}")
    return registry


def load_benchmark_spec(
    path: Path,
    *,
    repository_root: Path,
    seal_path_resolver: Callable[[BenchmarkSpec], tuple[Path, str]],
) -> BenchmarkSpec:
    """Load one benchmark specification and validate every frozen dependency."""

    spec = BenchmarkSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    registry_path = repository_root / spec.dataset_role_registry
    registry = load_dataset_role_registry(registry_path, repository_root=repository_root)
    if registry.registry_id != spec.benchmark_id:
        raise ValueError("dataset-role registry does not match benchmark_id")
    if spec.frozen_before_upgrade and registry.ratification_status != "ratified":
        raise ValueError("a frozen benchmark requires a ratified dataset-role registry")
    if spec.frozen_before_upgrade:
        planned = [dataset.id for dataset in registry.datasets if dataset.status == "planned"]
        if planned:
            raise ValueError(
                "a frozen benchmark cannot retain planned evaluation datasets; "
                f"unresolved={planned}"
            )
        sealed_datasets = [
            dataset
            for dataset in registry.datasets
            if dataset.role == "sealed_release_qualification"
        ]
        if not sealed_datasets:
            raise ValueError("a frozen benchmark requires a sealed release dataset")
        sealed_inputs = {relative for dataset in sealed_datasets for relative in dataset.inputs}
        missing_sealed_inputs = sorted(sealed_inputs - set(spec.identity_inputs))
        if missing_sealed_inputs:
            raise ValueError(
                "sealed qualification inputs must be frozen benchmark identities; "
                f"missing={missing_sealed_inputs}"
            )
    if spec.dataset_role_registry not in spec.identity_inputs:
        raise ValueError("dataset-role registry must be a frozen identity input")
    seal_path_resolver(spec)
    for relative in [*spec.identity_inputs, *spec.harness_inputs]:
        if not (repository_root / relative).is_file():
            raise ValueError(f"benchmark input does not exist: {relative}")
    return spec
