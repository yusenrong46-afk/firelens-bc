"""Prepare and resume named, capability-isolated blind review sessions."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.review_workspace.exports import read_private_canonical
from firelens.review_workspace.inputs import (
    ImportedReviewSuite,
    import_conversation_suite,
    import_retrieval_suite,
    import_semantic_holdout_suite,
)
from firelens.review_workspace.journal import create_immutable_json
from firelens.review_workspace.models import ReviewActor, ReviewSession
from firelens.review_workspace.session import BlindReviewSession


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewInputRecipe(_FrozenModel):
    suite_kind: Literal["conversation", "retrieval", "semantic_holdout"]
    conversation_report: str | None = None
    retrieval_dataset: str | None = None
    corpus_chunks: str | None = None
    corpus_manifest: str | None = None
    private_holdout_payload: str | None = None
    holdout_manifest: str | None = None
    holdout_candidate_report: str | None = None
    nonqualifying_dry_run: bool = False

    @model_validator(mode="after")
    def paths_match_suite(self) -> ReviewInputRecipe:
        supplied = {
            key
            for key, value in self.model_dump().items()
            if key not in {"suite_kind", "nonqualifying_dry_run"} and value is not None
        }
        expected = {
            "conversation": {"conversation_report"},
            "retrieval": {"retrieval_dataset", "corpus_chunks", "corpus_manifest"},
            "semantic_holdout": {
                "private_holdout_payload",
                "holdout_manifest",
                "holdout_candidate_report",
            },
        }[self.suite_kind]
        if supplied != expected:
            raise ValueError("review input recipe paths do not match the selected suite")
        if self.nonqualifying_dry_run and self.suite_kind != "conversation":
            raise ValueError("only conversation imports support an explicit dry run")
        for key in supplied:
            value = getattr(self, key)
            if value is None or not Path(value).is_absolute():
                raise ValueError("review input recipe paths must be absolute")
        return self


class PreparedReviewLaunch(_FrozenModel):
    launch_version: Literal["firelens_prepared_review_launch.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session: ReviewSession
    input_recipe: ReviewInputRecipe
    protocol_absolute_path: str
    allowed_origin: str


class ActorCapability(_FrozenModel):
    capability_version: Literal["firelens_review_actor_capability.v1"]
    session_id: str
    actor_id: str
    token: str = Field(min_length=43, max_length=256)


_PLACEHOLDER_HUMAN_NAMES = frozenset(
    {
        "accessibility specialist",
        "adjudicator",
        "chatgpt",
        "human reviewer",
        "owner",
        "release adjudicator",
        "reviewer",
        "reviewer a",
        "reviewer b",
        "tbd",
        "unknown",
    }
)


def _named_human(value: str, *, context: str) -> str:
    """Require an attributable human name instead of a role or model label."""

    normalized = value.strip()
    lowered = normalized.casefold()
    if (
        len(normalized) < 3
        or lowered in _PLACEHOLDER_HUMAN_NAMES
        or lowered.startswith(("gpt-", "claude-", "gemini-", "model-"))
        or not any(character.isalpha() for character in normalized)
    ):
        raise ValueError(f"{context} must identify a named human, not a placeholder or model")
    return normalized


def import_review_suite(recipe: ReviewInputRecipe) -> ImportedReviewSuite:
    """Re-import the bound inputs from a strict, immutable launch recipe."""

    if recipe.suite_kind == "conversation":
        assert recipe.conversation_report is not None
        return import_conversation_suite(
            Path(recipe.conversation_report),
            nonqualifying_dry_run=recipe.nonqualifying_dry_run,
        )
    if recipe.suite_kind == "retrieval":
        assert recipe.retrieval_dataset is not None
        assert recipe.corpus_chunks is not None
        assert recipe.corpus_manifest is not None
        return import_retrieval_suite(
            Path(recipe.retrieval_dataset),
            Path(recipe.corpus_chunks),
            Path(recipe.corpus_manifest),
        )
    assert recipe.private_holdout_payload is not None
    assert recipe.holdout_manifest is not None
    assert recipe.holdout_candidate_report is not None
    return import_semantic_holdout_suite(
        Path(recipe.private_holdout_payload),
        Path(recipe.holdout_manifest),
        Path(recipe.holdout_candidate_report),
    )


def _protocol_sha256(protocol_path: Path) -> str:
    from firelens.benchmark import file_sha256

    resolved = protocol_path.resolve(strict=True)
    metadata = resolved.lstat()
    if protocol_path.is_symlink() or not protocol_path.is_file() or metadata.st_nlink != 1:
        raise ValueError("review protocol must be a private, single-link regular file")
    return file_sha256(resolved)


def _validated_origin(origin: str) -> str:
    normalized = origin.rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("prepared review origin must be exact loopback HTTP with a port")
    return normalized


def prepare_review_session(
    directory: Path,
    *,
    session_id: str,
    review_kind: Literal["semantic", "retrieval"],
    input_recipe: ReviewInputRecipe,
    protocol_path: Path,
    reviewer_a_name: str,
    reviewer_b_name: str,
    adjudicator_name: str,
    allowed_origin: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[BlindReviewSession, dict[str, Path]]:
    """Create a new session plus one private capability file per named actor."""

    suite = import_review_suite(input_recipe)
    reviewer_a_name = _named_human(reviewer_a_name, context="reviewer A name")
    reviewer_b_name = _named_human(reviewer_b_name, context="reviewer B name")
    adjudicator_name = _named_human(adjudicator_name, context="adjudicator name")
    if (
        len(
            {
                reviewer_a_name.casefold(),
                reviewer_b_name.casefold(),
                adjudicator_name.casefold(),
            }
        )
        != 3
    ):
        raise ValueError("reviewers and adjudicator must be three distinct named humans")
    created_at = clock()
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("review preparation clock must return an offset-aware timestamp")
    session = ReviewSession(
        session_version="firelens_review_session.v1",
        session_id=session_id,
        review_kind=review_kind,
        artifact_sha256=suite.suite_sha256,
        protocol_sha256=_protocol_sha256(protocol_path),
        created_at=created_at.astimezone(UTC),
        case_ids=tuple(case.case_id for case in suite.cases),
        actors=(
            ReviewActor(
                actor_id="reviewer-a",
                display_name=reviewer_a_name,
                role="reviewer",
            ),
            ReviewActor(
                actor_id="reviewer-b",
                display_name=reviewer_b_name,
                role="reviewer",
            ),
            ReviewActor(
                actor_id="adjudicator",
                display_name=adjudicator_name,
                role="adjudicator",
            ),
        ),
    )
    coordinator = BlindReviewSession.create(directory, session=session, suite=suite)
    launch = PreparedReviewLaunch(
        launch_version="firelens_prepared_review_launch.v1",
        implementation_status="nonqualifying_backend_scaffold",
        qualification_eligible=False,
        session=session,
        input_recipe=input_recipe,
        protocol_absolute_path=str(protocol_path.resolve(strict=True)),
        allowed_origin=_validated_origin(allowed_origin),
    )
    create_immutable_json(directory, "session/launch.json", launch)
    capability_paths: dict[str, Path] = {}
    for actor in session.actors:
        capability = ActorCapability(
            capability_version="firelens_review_actor_capability.v1",
            session_id=session.session_id,
            actor_id=actor.actor_id,
            token=secrets.token_urlsafe(48),
        )
        capability_paths[actor.actor_id] = create_immutable_json(
            directory,
            f"access/{actor.actor_id}.json",
            capability,
        )
    return coordinator, capability_paths


def resume_prepared_review(
    directory: Path,
) -> tuple[BlindReviewSession, PreparedReviewLaunch, dict[str, str]]:
    """Recheck launch, protocol, inputs, and every private actor capability."""

    launch, _ = read_private_canonical(
        directory / "session" / "launch.json",
        PreparedReviewLaunch,
    )
    if _protocol_sha256(Path(launch.protocol_absolute_path)) != launch.session.protocol_sha256:
        raise ValueError("prepared review protocol identity changed")
    suite = import_review_suite(launch.input_recipe)
    coordinator = BlindReviewSession.resume(
        directory,
        session=launch.session,
        suite=suite,
    )
    tokens: dict[str, str] = {}
    for actor in launch.session.actors:
        capability, _ = read_private_canonical(
            directory / "access" / f"{actor.actor_id}.json",
            ActorCapability,
        )
        if (
            capability.session_id != launch.session.session_id
            or capability.actor_id != actor.actor_id
        ):
            raise ValueError("prepared review actor capability binding changed")
        tokens[actor.actor_id] = capability.token
    if len(set(tokens.values())) != len(tokens):
        raise ValueError("prepared review actor capabilities are not unique")
    return coordinator, launch, tokens
