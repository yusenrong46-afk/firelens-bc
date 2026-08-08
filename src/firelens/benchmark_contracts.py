"""Strict dataset contracts and loaders for FireLens benchmark generations."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.contracts import ConversationTurn, QueryRelation, QueryRoute, ResponseMode


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldEvidence(BenchmarkModel):
    source_id: str
    pages: list[int] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class BenchmarkCase(BenchmarkModel):
    id: str = Field(pattern=r"^V1-[A-Z]+-[0-9]{3}$")
    split: Literal["development", "holdout", "red_team"]
    category: Literal[
        "single_source",
        "multi_source",
        "paraphrase_ambiguity",
        "insufficient_evidence",
        "false_premise",
        "live_status",
        "personalized_safety",
        "prompt_injection",
    ]
    risk_level: Literal["ordinary", "high"]
    question: str = Field(min_length=1, max_length=2_000)
    expected_route: QueryRoute
    expected_status: Literal["answer", "abstention"]
    acceptable_evidence: list[GoldEvidence] = Field(default_factory=list)
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_limitations: list[str] = Field(default_factory=list)
    adjudication_status: Literal["automated_draft", "owner_approved"] = "automated_draft"
    reviewer_notes: str = ""

    @model_validator(mode="after")
    def evidence_matches_expected_status(self) -> BenchmarkCase:
        if self.expected_status == "answer" and not self.acceptable_evidence:
            raise ValueError("answer cases require acceptable evidence")
        if self.expected_route != QueryRoute.STATIC and self.acceptable_evidence:
            raise ValueError("non-static routes cannot use static acceptable evidence")
        return self


class BenchmarkDataset(BenchmarkModel):
    dataset_version: str
    frozen_at: str
    cases: list[BenchmarkCase]

    @model_validator(mode="after")
    def unique_case_ids(self) -> BenchmarkDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case IDs must be unique")
        return self


class RelevanceJudgment(BenchmarkModel):
    case_id: str = Field(pattern=r"^V1-[A-Z]+-[0-9]{3}$")
    rationale: str = Field(min_length=20, max_length=1_000)
    added_evidence: list[GoldEvidence] = Field(min_length=1)


class RelevanceAddendum(BenchmarkModel):
    addendum_version: Literal["firelens_relevance_addendum.v1"]
    base_dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_status: Literal["automated_evidence_audited", "owner_approved"]
    judgments: list[RelevanceJudgment] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> RelevanceAddendum:
        case_ids = [item.case_id for item in self.judgments]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("relevance addendum case IDs must be unique")
        return self


PaidProviderStage = Literal[
    "planner",
    "embeddings",
    "reranker",
    "grounded_generation",
    "background_generation",
]
ExpectedEvidenceStatus = Literal["verified_corpus", "general_background", "none"]


class ConversationBenchmarkCase(BenchmarkModel):
    """One strictly labelled V1.1 conversation case."""

    id: str = Field(pattern=r"^V1\.1-(DEV|HOLD|RED)-[0-9]{3}$")
    split: Literal["development", "holdout", "red_team"]
    category: Literal[
        "capability",
        "contextual_followup",
        "adjacent_background",
        "tangent",
        "mixed_adversarial",
    ]
    risk_level: Literal["ordinary", "high"]
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)
    expected_route: QueryRoute
    expected_planning_relation: QueryRelation | None
    expected_status: Literal["answer", "abstention"]
    expected_response_mode: ResponseMode
    acceptable_evidence: list[GoldEvidence] = Field(default_factory=list)
    expected_evidence_status: ExpectedEvidenceStatus
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_limitations: list[str] = Field(default_factory=list)
    expected_paid_provider_stages: list[PaidProviderStage] = Field(default_factory=list)
    adjudication_status: Literal["automated_draft", "owner_approved"] = "automated_draft"
    reviewer_notes: str = ""

    @model_validator(mode="after")
    def validate_expected_path(self) -> ConversationBenchmarkCase:
        answer_modes = {
            ResponseMode.CAPABILITY,
            ResponseMode.GROUNDED,
            ResponseMode.BACKGROUND,
            ResponseMode.SCOPE_REDIRECT,
        }
        if (self.expected_status == "answer") != (self.expected_response_mode in answer_modes):
            raise ValueError("expected status and response mode describe different outcomes")
        relation_routes = {QueryRoute.RELATED, QueryRoute.TANGENT}
        if (self.expected_planning_relation is None) != (
            self.expected_route not in relation_routes
        ):
            raise ValueError("planning relation must be present exactly for planned routes")
        if self.expected_route == QueryRoute.TANGENT and (
            self.expected_planning_relation != QueryRelation.TANGENT
        ):
            raise ValueError("tangent routes require a tangent planning relation")
        if (
            self.expected_route == QueryRoute.RELATED
            and self.expected_planning_relation
            not in {QueryRelation.GROUNDED_CANDIDATE, QueryRelation.ADJACENT}
        ):
            raise ValueError("related routes require a grounded or adjacent relation")
        expected_evidence_by_mode: dict[ResponseMode, ExpectedEvidenceStatus] = {
            ResponseMode.GROUNDED: "verified_corpus",
            ResponseMode.BACKGROUND: "general_background",
            ResponseMode.CAPABILITY: "none",
            ResponseMode.SCOPE_REDIRECT: "none",
            ResponseMode.ABSTENTION: "none",
        }
        if (
            self.expected_evidence_status
            != expected_evidence_by_mode[self.expected_response_mode]
        ):
            raise ValueError("expected evidence status does not match response mode")
        if (self.expected_response_mode == ResponseMode.GROUNDED) != bool(
            self.acceptable_evidence
        ):
            raise ValueError("only grounded cases may require acceptable corpus evidence")
        paid_path: dict[ResponseMode, list[PaidProviderStage]] = {
            ResponseMode.CAPABILITY: [],
            ResponseMode.ABSTENTION: [],
            ResponseMode.SCOPE_REDIRECT: ["planner"],
            ResponseMode.GROUNDED: [
                "planner",
                "embeddings",
                "reranker",
                "grounded_generation",
            ],
            ResponseMode.BACKGROUND: [
                "planner",
                "embeddings",
                "reranker",
                "background_generation",
            ],
        }
        if self.expected_paid_provider_stages != paid_path[self.expected_response_mode]:
            raise ValueError("expected provider stages do not match the expected path")
        return self


class ConversationBenchmarkDataset(BenchmarkModel):
    dataset_version: str
    frozen_at: str
    cases: list[ConversationBenchmarkCase]

    @model_validator(mode="after")
    def unique_case_ids(self) -> ConversationBenchmarkDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("conversation benchmark case IDs must be unique")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_benchmark(path: Path, *, require_release_shape: bool = True) -> BenchmarkDataset:
    dataset = BenchmarkDataset.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if require_release_shape:
        splits = Counter(case.split for case in dataset.cases)
        expected = {"development": 60, "holdout": 20, "red_team": 20}
        if len(dataset.cases) != 100 or dict(splits) != expected:
            raise ValueError(
                f"V1 benchmark must contain exactly {expected}; got {dict(splits)}"
            )
    return dataset


def load_relevance_addendum(path: Path, *, dataset_path: Path) -> RelevanceAddendum:
    addendum = RelevanceAddendum.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if addendum.base_dataset_sha256 != file_sha256(dataset_path):
        raise ValueError("relevance addendum does not match the locked benchmark hash")
    return addendum


def apply_relevance_addendum(
    dataset: BenchmarkDataset, addendum: RelevanceAddendum
) -> BenchmarkDataset:
    cases_by_id = {case.id: case for case in dataset.cases}
    unknown = {item.case_id for item in addendum.judgments} - cases_by_id.keys()
    if unknown:
        raise ValueError(f"relevance addendum contains unknown cases: {sorted(unknown)}")
    additions = {item.case_id: item.added_evidence for item in addendum.judgments}
    updated_cases = []
    for case in dataset.cases:
        evidence = [*case.acceptable_evidence, *additions.get(case.id, [])]
        identities = [item.model_dump_json() for item in evidence]
        if len(identities) != len(set(identities)):
            raise ValueError(f"relevance addendum duplicates evidence for {case.id}")
        updated_cases.append(case.model_copy(update={"acceptable_evidence": evidence}))
    return dataset.model_copy(update={"cases": updated_cases})


def load_conversation_benchmark(
    path: Path, *, require_release_shape: bool = True
) -> ConversationBenchmarkDataset:
    """Load the V1.1 addendum without weakening the frozen V1 schema."""

    dataset = ConversationBenchmarkDataset.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if require_release_shape:
        splits = Counter(case.split for case in dataset.cases)
        categories = Counter(case.category for case in dataset.cases)
        expected_splits = {"development": 30, "holdout": 10, "red_team": 10}
        expected_categories = {
            "capability": 10,
            "contextual_followup": 10,
            "adjacent_background": 10,
            "tangent": 10,
            "mixed_adversarial": 10,
        }
        if len(dataset.cases) != 50 or dict(splits) != expected_splits:
            raise ValueError(
                "V1.1 conversation benchmark must contain exactly "
                f"{expected_splits}; got {dict(splits)}"
            )
        if dict(categories) != expected_categories:
            raise ValueError(
                "V1.1 conversation benchmark must contain exactly "
                f"{expected_categories}; got {dict(categories)}"
            )
        if any(
            (case.split == "red_team") != (case.risk_level == "high") for case in dataset.cases
        ):
            raise ValueError("V1.1 red-team cases must be high risk and only those cases")
    return dataset
