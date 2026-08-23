"""Hash-bound datasets, expectation profiles, and invariants for the hard probe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.contracts import ConversationTurn, ResponseMode

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data/evaluation/hard_probe.v1.yaml"
DEFAULT_MANIFEST = ROOT / "data/evaluation/hard_probe.v1.manifest.json"
DEFAULT_RC2_EXPECTATIONS = ROOT / "data/evaluation/hard_probe_rc2_expectations.v1.yaml"
DEFAULT_RC2_EXPECTATIONS_MANIFEST = (
    ROOT / "data/evaluation/hard_probe_rc2_expectations.v1.manifest.json"
)
HARD_PROBE_MINIMUM_PASSED = 86
RC2_MIGRATION_IDS = (
    "A04",
    "A05",
    "A07",
    "A08",
    "A09",
    "A10",
    "I01",
    "I02",
    "J01",
    "J02",
)
RC2_QUOTE_ONLY_IDS = frozenset(RC2_MIGRATION_IDS) - {"J01"}
OFFICIAL_HANDOFF_ANSWER = (
    "FireLens does not have a reviewed structured claim for this high-risk question. "
    "Use the issuing authority for official wording."
)
RC2_QUOTE_ONLY_RATIONALE = (
    "Accept the deterministic official-quote-only downgrade required by structured publication."
)
RC2_HANDOFF_RATIONALE = (
    "Accept the deterministic official issuing-authority handoff when no reviewed "
    "structured claim is available."
)


class ProbeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HardProbeCase(ProbeModel):
    id: str = Field(pattern=r"^[A-M][0-9]{2}$")
    section: str = Field(pattern=r"^[A-M]$")
    question: str = Field(min_length=1, max_length=5_000)
    expected_text: str = Field(min_length=1)
    priority: Literal["MED", "HIGH", "CRITICAL"]
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)
    allowed_modes: list[ResponseMode] = Field(min_length=1)
    constructed_input: bool = False

    @model_validator(mode="after")
    def id_matches_section(self) -> HardProbeCase:
        if not self.id.startswith(self.section):
            raise ValueError("case ID and section do not match")
        return self


class ReferencedCase(ProbeModel):
    id: str
    playwright_file: str | None = None
    suite: str | None = None
    scenario: str | None = None


class HardProbeDataset(ProbeModel):
    dataset_version: Literal["hard_probe.v1"]
    description: str
    cases: list[HardProbeCase] = Field(min_length=105, max_length=105)
    browser_cases: list[ReferencedCase] = Field(min_length=7, max_length=7)
    fixture_cases: list[ReferencedCase] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def unique_ids(self) -> HardProbeDataset:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("hard-probe case IDs must be unique")
        return self


class HardProbeExpectationMigration(ProbeModel):
    id: str = Field(pattern=r"^[A-M][0-9]{2}$")
    add_allowed_modes: list[ResponseMode] = Field(min_length=1, max_length=1)
    required_publication_kinds: list[Literal["official_quote_only"]] = Field(max_length=1)
    require_validation_accepted: bool
    require_exact_quote_support: bool
    require_zero_generation: bool
    require_zero_claims: bool
    require_zero_evidence: bool
    require_official_handoff: bool
    required_reason_code: Literal["high_risk_claim_not_structured"] | None
    rationale: str = Field(min_length=1)


class HardProbeExpectationOverlay(ProbeModel):
    schema_version: Literal["firelens.hard_probe_expectations.v1"]
    profile: Literal["rc2"]
    base_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimum_passed: int
    migrations: list[HardProbeExpectationMigration] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def frozen_rc2_contract(self) -> HardProbeExpectationOverlay:
        if self.minimum_passed != HARD_PROBE_MINIMUM_PASSED:
            raise ValueError("RC2 expectation profile has the wrong pass floor")
        ids = [migration.id for migration in self.migrations]
        if ids != list(RC2_MIGRATION_IDS):
            raise ValueError("RC2 expectation profile has the wrong migration IDs or order")
        for migration in self.migrations:
            actual = migration.model_dump(mode="json")
            expected = _expected_rc2_migration(migration.id)
            if actual != expected:
                raise ValueError(
                    f"RC2 expectation profile migration {migration.id} is not frozen"
                )
        return self


class HardProbeExpectationManifest(ProbeModel):
    schema_version: Literal["firelens.hard_probe_expectations_manifest.v1"]
    profile: Literal["rc2"]
    expectations_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    migration_count: int
    migration_ids: list[str]
    minimum_passed: int

    @model_validator(mode="after")
    def frozen_rc2_contract(self) -> HardProbeExpectationManifest:
        if self.migration_count != len(RC2_MIGRATION_IDS):
            raise ValueError("RC2 expectation manifest has the wrong migration count")
        if self.migration_ids != sorted(RC2_MIGRATION_IDS):
            raise ValueError("RC2 expectation manifest has the wrong migration IDs")
        if self.minimum_passed != HARD_PROBE_MINIMUM_PASSED:
            raise ValueError("RC2 expectation manifest has the wrong pass floor")
        return self


class LoadedExpectationProfile(ProbeModel):
    profile: Literal["historical", "rc2"]
    base_dataset_sha256: str
    minimum_passed: int
    expectation_overlay_sha256: str | None
    migrations: dict[str, HardProbeExpectationMigration]


def _expected_rc2_migration(case_id: str) -> dict[str, Any]:
    if case_id in RC2_QUOTE_ONLY_IDS:
        return {
            "id": case_id,
            "add_allowed_modes": ["partial"],
            "required_publication_kinds": ["official_quote_only"],
            "require_validation_accepted": True,
            "require_exact_quote_support": True,
            "require_zero_generation": True,
            "require_zero_claims": False,
            "require_zero_evidence": False,
            "require_official_handoff": False,
            "required_reason_code": None,
            "rationale": RC2_QUOTE_ONLY_RATIONALE,
        }
    if case_id == "J01":
        return {
            "id": case_id,
            "add_allowed_modes": ["scope_redirect"],
            "required_publication_kinds": [],
            "require_validation_accepted": False,
            "require_exact_quote_support": False,
            "require_zero_generation": True,
            "require_zero_claims": True,
            "require_zero_evidence": True,
            "require_official_handoff": True,
            "required_reason_code": "high_risk_claim_not_structured",
            "rationale": RC2_HANDOFF_RATIONALE,
        }
    raise ValueError(f"unknown RC2 hard-probe migration ID: {case_id}")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON value with the repository's deterministic canonical encoding."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_dataset(path: Path, manifest_path: Path) -> HardProbeDataset:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_hash = file_sha256(path)
    if manifest.get("dataset_sha256") != actual_hash:
        raise ValueError("hard-probe dataset hash does not match its manifest")
    dataset = HardProbeDataset.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if manifest.get("case_count") != len(dataset.cases):
        raise ValueError("hard-probe case count does not match its manifest")
    return dataset


def load_expectation_profile(
    profile: Literal["historical", "rc2"],
    dataset: HardProbeDataset,
    *,
    dataset_path: Path = DEFAULT_DATASET,
    rc2_expectations_path: Path = DEFAULT_RC2_EXPECTATIONS,
    rc2_manifest_path: Path = DEFAULT_RC2_EXPECTATIONS_MANIFEST,
) -> LoadedExpectationProfile:
    """Load the one named overlay, failing closed on every frozen binding."""

    base_dataset_sha256 = file_sha256(dataset_path)
    if profile == "historical":
        return LoadedExpectationProfile(
            profile="historical",
            base_dataset_sha256=base_dataset_sha256,
            minimum_passed=HARD_PROBE_MINIMUM_PASSED,
            expectation_overlay_sha256=None,
            migrations={},
        )
    if profile != "rc2":
        raise ValueError(f"unknown hard-probe expectation profile: {profile}")

    expectations_sha256 = file_sha256(rc2_expectations_path)
    manifest = HardProbeExpectationManifest.model_validate(
        json.loads(rc2_manifest_path.read_text(encoding="utf-8"))
    )
    overlay = HardProbeExpectationOverlay.model_validate(
        yaml.safe_load(rc2_expectations_path.read_text(encoding="utf-8"))
    )
    if manifest.expectations_sha256 != expectations_sha256:
        raise ValueError("RC2 expectation overlay hash does not match its manifest")
    if manifest.base_dataset_sha256 != base_dataset_sha256:
        raise ValueError("RC2 expectation manifest is bound to the wrong base dataset")
    if overlay.base_dataset_sha256 != base_dataset_sha256:
        raise ValueError("RC2 expectation overlay is bound to the wrong base dataset")
    if overlay.minimum_passed != manifest.minimum_passed:
        raise ValueError("RC2 expectation overlay and manifest pass floors differ")
    migration_ids = [migration.id for migration in overlay.migrations]
    if sorted(migration_ids) != manifest.migration_ids:
        raise ValueError("RC2 expectation overlay and manifest migration IDs differ")
    if len(overlay.migrations) != manifest.migration_count:
        raise ValueError("RC2 expectation overlay and manifest migration counts differ")
    dataset_ids = {case.id for case in dataset.cases}
    unknown_ids = sorted(set(migration_ids) - dataset_ids)
    if unknown_ids:
        raise ValueError(
            "RC2 expectation overlay references unknown base cases: " + ", ".join(unknown_ids)
        )
    return LoadedExpectationProfile(
        profile="rc2",
        base_dataset_sha256=base_dataset_sha256,
        minimum_passed=overlay.minimum_passed,
        expectation_overlay_sha256=expectations_sha256,
        migrations={migration.id: migration for migration in overlay.migrations},
    )


def effective_allowed_modes(
    case: HardProbeCase, migration: HardProbeExpectationMigration | None
) -> list[ResponseMode]:
    modes = list(case.allowed_modes)
    if migration is not None:
        modes.extend(mode for mode in migration.add_allowed_modes if mode not in modes)
    return modes


def effective_expectations_payload(
    dataset: HardProbeDataset, profile: LoadedExpectationProfile
) -> dict[str, Any]:
    """Return the exact canonical input used by downstream RC2 validators."""

    cases: list[dict[str, Any]] = []
    for case in dataset.cases:
        migration = profile.migrations.get(case.id)
        cases.append(
            {
                "id": case.id,
                "allowed_modes": [
                    mode.value for mode in effective_allowed_modes(case, migration)
                ],
                "migration": migration.model_dump(mode="json") if migration else None,
            }
        )
    return {
        "schema_version": "firelens.hard_probe_effective_expectations.v1",
        "profile": profile.profile,
        "base_dataset_sha256": profile.base_dataset_sha256,
        "minimum_passed": profile.minimum_passed,
        "cases": cases,
    }


def _invariant_result(name: str, *, expected: Any, actual: Any, passed: bool) -> dict[str, Any]:
    return {"name": name, "expected": expected, "actual": actual, "passed": passed}


def _generation_provider_stages(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        stage
        for stage in stages
        if str(stage.get("stage", "")).endswith(("_generation", "_repair"))
        or stage.get("stage") == "generation"
    ]


def _exact_quote_support(response: dict[str, Any]) -> bool:
    evidence_by_id = {item.get("evidence_id"): item for item in response.get("evidence") or []}
    claims = response.get("claims") or []
    return bool(claims) and all(
        claim.get("supports")
        and all(
            (item := evidence_by_id.get(support.get("evidence_id"))) is not None
            and bool(support.get("quote"))
            and support["quote"] in (item.get("primary_text") or "")
            for support in claim.get("supports") or []
        )
        for claim in claims
    )


def _migration_invariant_checks(
    migration: HardProbeExpectationMigration | None,
    response: dict[str, Any],
    stages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if migration is None:
        return []
    checks: list[dict[str, Any]] = []
    claims = response.get("claims") or []
    evidence = response.get("evidence") or []
    if migration.required_publication_kinds:
        actual_kinds = [(claim.get("publication") or {}).get("kind") for claim in claims]
        checks.extend(
            [
                _invariant_result(
                    "at_least_one_claim",
                    expected=True,
                    actual=bool(claims),
                    passed=bool(claims),
                ),
                _invariant_result(
                    "at_least_one_evidence",
                    expected=True,
                    actual=bool(evidence),
                    passed=bool(evidence),
                ),
                _invariant_result(
                    "required_publication_kinds",
                    expected=migration.model_dump(mode="json")["required_publication_kinds"],
                    actual=actual_kinds,
                    passed=bool(claims)
                    and all(
                        kind in migration.required_publication_kinds for kind in actual_kinds
                    ),
                ),
            ]
        )
    if migration.require_validation_accepted:
        accepted = bool(
            isinstance(response.get("validation"), dict)
            and response["validation"].get("accepted")
        )
        checks.append(
            _invariant_result(
                "validation_accepted", expected=True, actual=accepted, passed=accepted
            )
        )
    if migration.require_exact_quote_support:
        exact = _exact_quote_support(response)
        checks.append(
            _invariant_result("exact_quote_support", expected=True, actual=exact, passed=exact)
        )
    if migration.require_zero_generation:
        generation_stages = _generation_provider_stages(stages)
        generation_attempts = sum(
            int(stage.get("attempts") or 0) for stage in generation_stages
        )
        generation_cost = sum(
            (float(stage.get("cost_usd") or 0) for stage in generation_stages), 0.0
        )
        checks.extend(
            [
                _invariant_result(
                    "zero_generation_attempts",
                    expected=0,
                    actual=generation_attempts,
                    passed=generation_attempts == 0,
                ),
                _invariant_result(
                    "zero_generation_cost_usd",
                    expected=0.0,
                    actual=generation_cost,
                    passed=generation_cost == 0.0,
                ),
            ]
        )
    if migration.require_zero_claims:
        checks.append(
            _invariant_result("zero_claims", expected=0, actual=len(claims), passed=not claims)
        )
    if migration.require_zero_evidence:
        checks.append(
            _invariant_result(
                "zero_evidence", expected=0, actual=len(evidence), passed=not evidence
            )
        )
    if migration.require_official_handoff:
        answer = response.get("answer")
        checks.append(
            _invariant_result(
                "official_handoff",
                expected=OFFICIAL_HANDOFF_ANSWER,
                actual=answer,
                passed=answer == OFFICIAL_HANDOFF_ANSWER,
            )
        )
    if migration.required_reason_code is not None:
        actual_reason = response.get("reason_code")
        checks.append(
            _invariant_result(
                "required_reason_code",
                expected=migration.required_reason_code,
                actual=actual_reason,
                passed=actual_reason == migration.required_reason_code,
            )
        )
    return checks
