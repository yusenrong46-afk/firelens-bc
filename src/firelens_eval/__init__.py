"""Canonical, zero-cost FireLens evaluation adapter layer."""

from __future__ import annotations

from firelens_eval.cli import main
from firelens_eval.lab import (
    DEFAULT_ARTIFACT_ROOT,
    SUITES,
    compare_runs,
    diagnose_case,
    evaluation_source_identity,
    inventory,
    run_suite,
    source_identity,
    validate_claimbench_report,
    validate_failure_record,
    validate_hard_probe_report,
    validate_run_envelope,
)

__all__ = [
    "DEFAULT_ARTIFACT_ROOT",
    "SUITES",
    "compare_runs",
    "diagnose_case",
    "evaluation_source_identity",
    "inventory",
    "main",
    "run_suite",
    "source_identity",
    "validate_claimbench_report",
    "validate_failure_record",
    "validate_hard_probe_report",
    "validate_run_envelope",
]
