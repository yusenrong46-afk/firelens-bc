"""Versioned J01 source/explanation oracle and paired frozen-profile observation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from firelens.contracts import AskResponse, render_claim_texts

ROOT = Path(__file__).resolve().parents[3]
MISSING_EXPLANATION_LIMITATIONS = frozenset(
    {
        "The selected evidence does not explain why this matters.",
        "The supported portion does not explain why this matters.",
        "The selected evidence does not explain why grab-and-go preparedness matters.",
    }
)


def current_source_explanation_supported(
    response: dict[str, Any], *, root: Path = ROOT
) -> bool:
    """Require current corpus quotations, with rationale or explicit missing rationale."""
    try:
        payload = dict(response)
        if payload.pop("http_status", 200) != 200:
            return False
        parsed = AskResponse.model_validate(payload)
        if parsed.response_mode.value != "partial" or not parsed.claims:
            return False
        if parsed.validation is None or not parsed.validation.accepted:
            return False
        if parsed.answer_sections or parsed.live_results:
            return False
        if parsed.answer != render_claim_texts(parsed.claims):
            return False
        rows = [
            json.loads(line)
            for line in (root / "data/processed/firelens_static_corpus.chunks.jsonl")
            .read_text()
            .splitlines()
        ]
        evidence = {item.evidence_id: item for item in parsed.evidence}
        quotes = []
        for claim in parsed.claims:
            if (
                claim.publication is None
                or claim.publication.kind.value != "official_quote_only"
            ):
                return False
            if len(claim.supports) != 1 or claim.text != claim.supports[0].quote:
                return False
            support = claim.supports[0]
            item = evidence.get(support.evidence_id)
            if item is None or support.quote not in item.primary_text:
                return False
            if not any(
                row["document_sha256"] == item.document_sha256
                and row["canonical_url"] == str(item.canonical_url)
                and row["source_id"] == "preparedbc_wildfire_guide"
                and "GRAB-AND-GO" in (row.get("section_title") or "").upper()
                and support.quote in row["text"]
                for row in rows
            ):
                return False
            quotes.append(" ".join(support.quote.casefold().split()))
        # The reviewed preparation rationale is explicit source wording, not an
        # AI entailment judgement. Exact source admission was checked above.
        rationale = any("not caught off guard" in quote for quote in quotes)
        return rationale or bool(
            MISSING_EXPLANATION_LIMITATIONS.intersection(parsed.limitations)
        )
    except (ValueError, TypeError, KeyError, OSError):
        return False


def legacy_j01_result(response: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-evaluate the SAME response under the unchanged rc2.2 J01 contract."""
    from firelens.evaluation.hard_probe_cli import _semantic_checks
    from firelens.evaluation.hard_probe_expectations import (
        DEFAULT_DATASET,
        DEFAULT_MANIFEST,
        _migration_invariant_checks,
        effective_allowed_modes,
        load_dataset,
        load_expectation_profile,
    )

    dataset = load_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)
    case = next(case for case in dataset.cases if case.id == "J01")
    migration = load_expectation_profile(
        "rc2.2", dataset, dataset_path=DEFAULT_DATASET
    ).migrations["J01"]
    effective = case.model_copy(
        update={"allowed_modes": effective_allowed_modes(case, migration)}
    )
    issues = _semantic_checks(effective, response)
    invariants = _migration_invariant_checks(migration, response, stages)
    return {
        "profile": "rc2.2",
        "passed": not issues and all(c["passed"] for c in invariants),
        "question": case.question,
        "history": [turn.model_dump(mode="json") for turn in case.history],
        "base_issues": issues,
        "migration_invariants": invariants,
    }


def validate_current_j01(row: dict[str, Any], *, root: Path) -> None:
    from firelens.evaluation.candidate_evidence_common import validate_zero_generation

    validate_zero_generation(row, case_id="J01")
    if row.get("passed") is not True or not current_source_explanation_supported(
        row.get("response", {}), root=root
    ):
        raise ValueError("J01 current source/explanation contract failed")
    legacy = legacy_j01_result(row["response"], row.get("provider_stages", []))
    if row.get("legacy_profile_result") != legacy or legacy["passed"] is not False:
        raise ValueError("J01 must retain its recomputed legacy failure")
    if (
        row.get("question") != legacy["question"]
        or row.get("request_history") != legacy["history"]
    ):
        raise ValueError("J01 original question/history changed")
