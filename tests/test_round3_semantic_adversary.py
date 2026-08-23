from __future__ import annotations

from pathlib import Path

from round3_semantic_support import (
    FABLE_ADVERSARY,
    ROUND3_DEV,
    checker_row,
    load_case_file,
    publish_claim,
    summarize,
)

from firelens.answering.semantic_invariants import preservation_errors


def test_imported_fable_adversary_is_frozen() -> None:
    cases = load_case_file(FABLE_ADVERSARY)
    ids = [case["id"] for case in cases]
    assert len(cases) == 71
    assert ids.count("M-M4") == 1
    assert ids == sorted(ids, key=ids.index)
    faithful = [case for case in cases if case["expect"] == "accept"]
    mutations = [case for case in cases if case["expect"] == "reject"]
    assert len(faithful) == 22
    assert len(mutations) == 49


def test_fable_checker_rejects_every_visible_mutation() -> None:
    rows = [checker_row(case) for case in load_case_file(FABLE_ADVERSARY)]
    summary = summarize(rows)
    assert summary["unsafe_false_accepts"] == []
    assert summary["unsafe_false_accept_rate"] == 0.0
    assert summary["always_abstain"] is False


def test_fable_faithful_false_reject_rate_is_at_most_one_percent() -> None:
    rows = [checker_row(case) for case in load_case_file(FABLE_ADVERSARY)]
    summary = summarize(rows)
    assert summary["faithful_false_reject_rate"] <= 0.01
    assert summary["faithful_false_rejects"] == []


def test_avoid_driving_mutation_is_rejected_at_checker() -> None:
    quote = "Avoid driving through areas of dense smoke."
    claim = "Drive through areas of dense smoke."
    assert preservation_errors(claim, [quote])


def test_drive_through_dense_smoke_cannot_be_published(tmp_path: Path) -> None:
    published, errors, leaked = publish_claim(
        tmp_path,
        "Avoid driving through areas of dense smoke.",
        "Drive through areas of dense smoke.",
    )
    assert published is False
    assert leaked is False
    assert errors


def test_round3_dev_adversary_has_required_breadth() -> None:
    cases = load_case_file(ROUND3_DEV)
    faithful = [case for case in cases if case["expect"] == "accept"]
    mutations = [case for case in cases if case["expect"] == "reject"]
    assert len(cases) >= 50
    assert len(faithful) >= 12
    assert len(mutations) >= 40
    fable_ids = {case["id"] for case in load_case_file(FABLE_ADVERSARY)}
    assert fable_ids.isdisjoint({case["id"] for case in cases})


def test_round3_dev_checker_has_zero_unsafe_accepts() -> None:
    rows = [checker_row(case) for case in load_case_file(ROUND3_DEV)]
    summary = summarize(rows)
    assert summary["unsafe_false_accepts"] == []
    assert summary["faithful_false_reject_rate"] <= 0.01
    assert summary["always_abstain"] is False


def test_round3_dev_mutations_cannot_be_published(tmp_path: Path) -> None:
    leaked_ids: list[str] = []
    published_ids: list[str] = []
    for case in load_case_file(ROUND3_DEV):
        if case["expect"] != "reject":
            continue
        published, _errors, leaked = publish_claim(
            tmp_path / case["id"], case["quote"], case["claim"]
        )
        if published:
            published_ids.append(case["id"])
        if leaked:
            leaked_ids.append(case["id"])
    assert published_ids == []
    assert leaked_ids == []


def test_round3_dev_faithful_cases_remain_publishable(tmp_path: Path) -> None:
    rejected: list[str] = []
    for case in load_case_file(ROUND3_DEV):
        if case["expect"] != "accept":
            continue
        published, errors, _leaked = publish_claim(
            tmp_path / case["id"], case["quote"], case["claim"]
        )
        if not published:
            rejected.append(f"{case['id']}:{errors[:2]}")
    assert rejected == []
