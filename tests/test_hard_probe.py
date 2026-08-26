from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.run_hard_probe import (
    DEFAULT_RC2_1_EXPECTATIONS,
    DEFAULT_RC2_1_EXPECTATIONS_MANIFEST,
    DEFAULT_RC2_EXPECTATIONS,
    DEFAULT_RC2_EXPECTATIONS_MANIFEST,
    OFFICIAL_HANDOFF_ANSWER,
    RC2_1_MIGRATION_IDS,
    RC2_MIGRATION_IDS,
    _cost_limit_reached,
    _migration_invariant_checks,
    _semantic_checks,
    canonical_json_sha256,
    effective_expectations_payload,
    file_sha256,
    load_dataset,
    load_expectation_profile,
    parse_args,
)
from scripts.run_hard_probe import (
    run as run_probe,
)


class HardProbeDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.dataset_path = self.root / "data/evaluation/hard_probe.v1.yaml"
        self.manifest_path = self.root / "data/evaluation/hard_probe.v1.manifest.json"

    def test_dataset_shape_and_manifest_hash_are_locked(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(len(dataset.cases), 105)
        self.assertEqual(len(dataset.browser_cases), 7)
        self.assertEqual(len(dataset.fixture_cases), 10)
        self.assertEqual(manifest["dataset_sha256"], file_sha256(self.dataset_path))
        self.assertEqual(
            file_sha256(self.dataset_path),
            "ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035",
        )
        self.assertEqual(
            file_sha256(self.manifest_path),
            "7f051c79169b7a31fae8c6d6e71dd064cbd501280794d62467e114e6635404d5",
        )
        self.assertFalse(manifest["sealed_release_holdout"])

    def test_modified_dataset_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "hard_probe.v1.yaml"
            changed.write_bytes(self.dataset_path.read_bytes() + b"\n")

            with self.assertRaisesRegex(ValueError, "hash"):
                load_dataset(changed, self.manifest_path)

    def test_zero_cost_ceiling_does_not_block_offline_mode(self) -> None:
        self.assertFalse(
            _cost_limit_reached(mode="offline", current_cost=0.0, max_cost_usd=0.0)
        )
        self.assertTrue(
            _cost_limit_reached(mode="qualified", current_cost=0.0, max_cost_usd=0.0)
        )

    def test_named_rc2_profile_is_hash_bound_and_changes_exactly_ten_cases(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        historical = load_expectation_profile(
            "historical", dataset, dataset_path=self.dataset_path
        )
        rc2 = load_expectation_profile("rc2", dataset, dataset_path=self.dataset_path)

        self.assertIsNone(historical.expectation_overlay_sha256)
        self.assertEqual(rc2.expectation_overlay_sha256, file_sha256(DEFAULT_RC2_EXPECTATIONS))
        self.assertEqual(tuple(rc2.migrations), RC2_MIGRATION_IDS)
        effective = effective_expectations_payload(dataset, rc2)
        self.assertEqual(
            canonical_json_sha256(effective),
            "9ba2751f5e81ce30fdb59616541a085c0de12dfab7ba2e273bc6c1d69a448e7f",
        )
        by_id = {case["id"]: case for case in effective["cases"]}
        self.assertEqual(by_id["A01"]["allowed_modes"], ["grounded"])
        self.assertIsNone(by_id["A01"]["migration"])
        self.assertEqual(by_id["A04"]["allowed_modes"], ["grounded", "partial"])
        self.assertEqual(
            by_id["J01"]["allowed_modes"], ["background", "grounded", "scope_redirect"]
        )

    def test_named_rc2_1_profile_is_hash_bound_and_adds_only_a01(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        rc2 = load_expectation_profile("rc2", dataset, dataset_path=self.dataset_path)
        rc2_1 = load_expectation_profile("rc2.1", dataset, dataset_path=self.dataset_path)

        self.assertEqual(
            rc2_1.expectation_overlay_sha256,
            file_sha256(DEFAULT_RC2_1_EXPECTATIONS),
        )
        self.assertEqual(tuple(rc2_1.migrations), RC2_1_MIGRATION_IDS)
        self.assertEqual(tuple(rc2_1.migrations)[:-1], tuple(rc2.migrations))
        self.assertEqual(tuple(rc2_1.migrations)[-1], "A01")
        effective = effective_expectations_payload(dataset, rc2_1)
        self.assertEqual(
            canonical_json_sha256(effective),
            "717cbfbf09482af9ed0baf615c8e306622d57eb9a35d86cc9882d9cdc9380d49",
        )
        by_id = {case["id"]: case for case in effective["cases"]}
        self.assertEqual(by_id["A01"]["allowed_modes"], ["grounded", "partial"])
        self.assertEqual(
            by_id["A01"]["migration"]["required_publication_kinds"],
            ["structured_reviewed", "official_quote_only"],
        )
        self.assertEqual(
            by_id["A01"]["migration"]["required_reason_code"],
            "high_risk_claim_not_structured",
        )

        manifest = json.loads(DEFAULT_RC2_1_EXPECTATIONS_MANIFEST.read_text())
        self.assertEqual(
            manifest["expectations_sha256"], file_sha256(DEFAULT_RC2_1_EXPECTATIONS)
        )
        self.assertEqual(manifest["migration_count"], 11)

    def test_rc2_profile_fails_closed_on_contract_drift(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        source_overlay = yaml.safe_load(DEFAULT_RC2_EXPECTATIONS.read_text(encoding="utf-8"))
        source_manifest = json.loads(
            DEFAULT_RC2_EXPECTATIONS_MANIFEST.read_text(encoding="utf-8")
        )
        mutations = {
            "unknown field": lambda overlay, manifest: overlay.update({"unknown": True}),
            "wrong ID": lambda overlay, manifest: overlay["migrations"][0].update(
                {"id": "A06"}
            ),
            "wrong mode": lambda overlay, manifest: overlay["migrations"][0].update(
                {"add_allowed_modes": ["grounded"]}
            ),
            "wrong floor": lambda overlay, manifest: (
                overlay.update({"minimum_passed": 85}),
                manifest.update({"minimum_passed": 85}),
            ),
            "wrong base hash": lambda overlay, manifest: (
                overlay.update({"base_dataset_sha256": "0" * 64}),
                manifest.update({"base_dataset_sha256": "0" * 64}),
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = json.loads(json.dumps(source_overlay))
                manifest = json.loads(json.dumps(source_manifest))
                mutate(overlay, manifest)
                overlay_path = Path(directory) / "expectations.yaml"
                manifest_path = Path(directory) / "manifest.json"
                overlay_path.write_text(
                    yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8"
                )
                manifest["expectations_sha256"] = file_sha256(overlay_path)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_expectation_profile(
                        "rc2",
                        dataset,
                        dataset_path=self.dataset_path,
                        rc2_expectations_path=overlay_path,
                        rc2_manifest_path=manifest_path,
                    )

        with tempfile.TemporaryDirectory() as directory:
            changed_overlay = Path(directory) / "expectations.yaml"
            changed_overlay.write_bytes(DEFAULT_RC2_EXPECTATIONS.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                load_expectation_profile(
                    "rc2",
                    dataset,
                    dataset_path=self.dataset_path,
                    rc2_expectations_path=changed_overlay,
                    rc2_manifest_path=DEFAULT_RC2_EXPECTATIONS_MANIFEST,
                )

    def test_rc2_1_profile_fails_closed_on_a01_contract_drift(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        overlay = yaml.safe_load(DEFAULT_RC2_1_EXPECTATIONS.read_text(encoding="utf-8"))
        manifest = json.loads(DEFAULT_RC2_1_EXPECTATIONS_MANIFEST.read_text(encoding="utf-8"))
        overlay["migrations"][-1]["required_publication_kinds"] = ["structured_reviewed"]
        with tempfile.TemporaryDirectory() as directory:
            overlay_path = Path(directory) / "expectations.yaml"
            manifest_path = Path(directory) / "manifest.json"
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
            manifest["expectations_sha256"] = file_sha256(overlay_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not frozen"):
                load_expectation_profile(
                    "rc2.1",
                    dataset,
                    dataset_path=self.dataset_path,
                    rc2_1_expectations_path=overlay_path,
                    rc2_1_manifest_path=manifest_path,
                )

    def test_rc2_migration_invariants_are_independently_reported(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        profile = load_expectation_profile("rc2", dataset, dataset_path=self.dataset_path)
        quote_response = {
            "claims": [
                {
                    "publication": {"kind": "official_quote_only"},
                    "supports": [{"evidence_id": "E1", "quote": "exact quote"}],
                }
            ],
            "evidence": [{"evidence_id": "E1", "primary_text": "An exact quote here."}],
            "validation": {"accepted": True},
        }
        checks = _migration_invariant_checks(
            profile.migrations["A04"], quote_response, [{"stage": "rerank", "attempts": 1}]
        )
        self.assertEqual(
            [check["name"] for check in checks],
            [
                "at_least_one_claim",
                "at_least_one_evidence",
                "required_publication_kinds",
                "validation_accepted",
                "exact_quote_support",
                "zero_generation_attempts",
                "zero_generation_cost_usd",
            ],
        )
        self.assertTrue(all(check["passed"] for check in checks))
        failed = _migration_invariant_checks(
            profile.migrations["A04"],
            quote_response,
            [{"stage": "grounded_generation", "attempts": 1, "cost_usd": 0.01}],
        )
        self.assertFalse(all(check["passed"] for check in failed))

        handoff_checks = _migration_invariant_checks(
            profile.migrations["J01"],
            {
                "answer": OFFICIAL_HANDOFF_ANSWER,
                "reason_code": "high_risk_claim_not_structured",
                "claims": [],
                "evidence": [],
            },
            [],
        )
        self.assertTrue(all(check["passed"] for check in handoff_checks))

        mixed_profile = load_expectation_profile(
            "rc2.1", dataset, dataset_path=self.dataset_path
        )
        mixed_response = {
            "claims": [
                {
                    "publication": {"kind": "structured_reviewed"},
                    "supports": [{"evidence_id": "E1", "quote": "reviewed quote"}],
                },
                {
                    "publication": {"kind": "official_quote_only"},
                    "supports": [{"evidence_id": "E2", "quote": "official quote"}],
                },
            ],
            "evidence": [
                {"evidence_id": "E1", "primary_text": "A reviewed quote."},
                {"evidence_id": "E2", "primary_text": "An official quote."},
            ],
            "validation": {"accepted": True},
            "reason_code": "high_risk_claim_not_structured",
        }
        mixed_checks = _migration_invariant_checks(
            mixed_profile.migrations["A01"], mixed_response, []
        )
        self.assertTrue(all(check["passed"] for check in mixed_checks))
        mixed_response["claims"] = mixed_response["claims"][:1]
        missing_kind_checks = _migration_invariant_checks(
            mixed_profile.migrations["A01"], mixed_response, []
        )
        self.assertFalse(
            next(
                check
                for check in missing_kind_checks
                if check["name"] == "required_publication_kinds"
            )["passed"]
        )

    def test_cli_exposes_only_named_expectation_profiles(self) -> None:
        self.assertEqual(parse_args([]).expectation_profile, "historical")
        self.assertEqual(
            parse_args(["--expectation-profile", "rc2"]).expectation_profile, "rc2"
        )
        self.assertEqual(
            parse_args(["--expectation-profile", "rc2.1"]).expectation_profile,
            "rc2.1",
        )
        with self.assertRaises(SystemExit):
            parse_args(["--expectation-profile", "./custom.yaml"])

    def test_rc2_run_emits_v2_identity_and_applied_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = parse_args(
                [
                    "--mode",
                    "offline",
                    "--expectation-profile",
                    "rc2",
                    "--case-id",
                    "J01",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(asyncio.run(run_probe(args)), 0)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["schema_version"], "firelens_hard_probe_report.v2")
        self.assertEqual(report["manifest"]["expectation_profile"], "rc2")
        self.assertEqual(
            report["manifest"]["effective_expectations_sha256"],
            "9ba2751f5e81ce30fdb59616541a085c0de12dfab7ba2e273bc6c1d69a448e7f",
        )
        self.assertIn("tree", report["manifest"])
        row = report["results"][0]
        self.assertEqual(row["id"], "J01")
        self.assertEqual(row["applied_migration"]["id"], "J01")
        self.assertTrue(row["passed"])
        self.assertEqual(row["semantic_checks"]["base_issues"], [])
        self.assertTrue(
            all(
                invariant["passed"]
                for invariant in row["semantic_checks"]["migration_invariants"]
            )
        )

    def test_a01_remains_failed_under_rc2_and_passes_strongly_under_rc2_1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rc2_output = Path(directory) / "rc2.json"
            rc2_args = parse_args(
                [
                    "--mode",
                    "offline",
                    "--expectation-profile",
                    "rc2",
                    "--case-id",
                    "A01",
                    "--output",
                    str(rc2_output),
                ]
            )
            self.assertEqual(asyncio.run(run_probe(rc2_args)), 1)
            rc2_report = json.loads(rc2_output.read_text(encoding="utf-8"))

            rc2_1_output = Path(directory) / "rc2-1.json"
            rc2_1_args = parse_args(
                [
                    "--mode",
                    "offline",
                    "--expectation-profile",
                    "rc2.1",
                    "--case-id",
                    "A01",
                    "--output",
                    str(rc2_1_output),
                ]
            )
            self.assertEqual(asyncio.run(run_probe(rc2_1_args)), 0)
            rc2_1_report = json.loads(rc2_1_output.read_text(encoding="utf-8"))

        self.assertFalse(rc2_report["results"][0]["passed"])
        row = rc2_1_report["results"][0]
        self.assertTrue(row["passed"])
        self.assertEqual(row["response_mode"], "partial")
        self.assertEqual(
            {claim["publication"]["kind"] for claim in row["response"]["claims"]},
            {"structured_reviewed", "official_quote_only"},
        )
        self.assertTrue(
            all(check["passed"] for check in row["semantic_checks"]["migration_invariants"])
        )

    def test_a02_semantic_invariant_rejects_one_sided_grounded_comparison(self) -> None:
        dataset = load_dataset(self.dataset_path, self.manifest_path)
        case = next(item for item in dataset.cases if item.id == "A02")
        one_sided = {
            "response_mode": "grounded",
            "status": "answer",
            "http_status": 200,
            "answer": "An evacuation order means you are at risk and must leave immediately.",
            "claims": [
                {
                    "evidence_status": "verified_corpus",
                    "publication": {"typed_claim_id": "TC-EVAC-ORDER-001"},
                    "supports": [{"evidence_id": "E1", "quote": "leave immediately"}],
                }
            ],
            "evidence": [{"evidence_id": "E1", "primary_text": "leave immediately"}],
            "limitations": ["Grounded in reviewed official sources."],
        }
        issues = _semantic_checks(case, one_sided)
        self.assertTrue(
            any("both alert and order definitions" in issue for issue in issues),
            issues,
        )

        both_sides = {
            **one_sided,
            "answer": (
                "If you are under an evacuation alert, be ready to leave on short notice. "
                "An evacuation order means you are at risk and must leave immediately."
            ),
            "claims": [
                {
                    "evidence_status": "verified_corpus",
                    "publication": {"typed_claim_id": "TC-EVAC-ALERT-001"},
                    "supports": [{"evidence_id": "E1", "quote": "short notice"}],
                },
                {
                    "evidence_status": "verified_corpus",
                    "publication": {"typed_claim_id": "TC-EVAC-ORDER-001"},
                    "supports": [{"evidence_id": "E2", "quote": "leave immediately"}],
                },
            ],
            "evidence": [
                {"evidence_id": "E1", "primary_text": "short notice"},
                {"evidence_id": "E2", "primary_text": "leave immediately"},
            ],
        }
        both_issues = _semantic_checks(case, both_sides)
        self.assertFalse(
            any("both alert and order definitions" in issue for issue in both_issues),
            both_issues,
        )

        uncovered_only = {
            **one_sided,
            "response_mode": "partial",
            "limitations": [
                "Some requested high-risk guidance has no reviewed structured claim."
            ],
        }
        uncovered_issues = _semantic_checks(case, uncovered_only)
        self.assertTrue(
            any("missing-aspect limitation" in issue for issue in uncovered_issues),
            uncovered_issues,
        )

        partial_named = {
            **one_sided,
            "response_mode": "partial",
            "limitations": ["Not supported by selected evidence: evacuation alert meaning"],
        }
        partial_issues = _semantic_checks(case, partial_named)
        self.assertFalse(
            any("missing-aspect limitation" in issue for issue in partial_issues),
            partial_issues,
        )
