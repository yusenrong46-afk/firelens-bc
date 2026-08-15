"""Stage-specific OpenRouter privacy policy. Not a privacy certification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict

ZdrRequirement = Literal["required", "optional"]
DataCollectionPolicy = Literal["deny"]
ProviderPreferenceStage = Literal[
    "embedding",
    "reranking",
    "planning",
    "context_generation",
    "grounded_generation",
    "background_generation",
]
ZdrPolicyState = Literal[
    "disabled",
    "stage_bound_unprobed",
    "required_stages_eligible",
    "failed",
]
RequiredStageState = Literal["not_required", "unprobed", "eligible", "failed"]
RerankingStageState = Literal[
    "not_required",
    "unprobed",
    "eligible",
    "zdr_optional",
    "failed",
]
ZdrStageStatus = Literal["eligible", "zdr_optional", "failed"]
CANDIDATE_PRIVACY_FIELDS = (
    "data_collection",
    "allow_fallbacks",
    "require_parameters",
    "embedding_zdr",
    "reranking_zdr",
    "generation_zdr",
)
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "off"})
_SETTING = Callable[[str], str | None]


class OpenRouterPrivacyPolicy(BaseModel):
    """Explicit per-stage OpenRouter routing policy.

    ``data_collection="deny"`` is provider data-policy filtering. It is not ZDR.
    Account or guardrail ZDR cannot be disabled from a request; required stages
    still send ``provider.zdr=true`` and fail closed without a ZDR endpoint.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_collection: DataCollectionPolicy = "deny"
    allow_fallbacks: Literal[False] = False
    require_parameters: Literal[True] = True
    embedding_zdr: ZdrRequirement = "optional"
    reranking_zdr: ZdrRequirement = "optional"
    generation_zdr: ZdrRequirement = "optional"

    @property
    def any_zdr_required(self) -> bool:
        return "required" in {
            self.embedding_zdr,
            self.reranking_zdr,
            self.generation_zdr,
        }

    def zdr_required_for(self, stage: ProviderPreferenceStage) -> bool:
        if stage not in get_args(ProviderPreferenceStage):
            raise ValueError(f"unknown OpenRouter privacy stage: {stage}")
        if stage == "embedding":
            return self.embedding_zdr == "required"
        if stage == "reranking":
            return self.reranking_zdr == "required"
        return self.generation_zdr == "required"

    def provider_preferences(self, stage: ProviderPreferenceStage) -> dict[str, Any]:
        preferences: dict[str, Any] = {
            "require_parameters": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
        }
        if self.zdr_required_for(stage):
            preferences["zdr"] = True
        return preferences

    def candidate_fields(self) -> dict[str, str]:
        document = {
            "data_collection": self.data_collection,
            "allow_fallbacks": "false",
            "require_parameters": "true",
            "embedding_zdr": self.embedding_zdr,
            "reranking_zdr": self.reranking_zdr,
            "generation_zdr": self.generation_zdr,
        }
        if set(document) != set(CANDIDATE_PRIVACY_FIELDS):
            raise RuntimeError("privacy candidate fields drifted from the contract")
        return document


LOCAL_DEFAULT_PRIVACY = OpenRouterPrivacyPolicy()
APPROVED_PRODUCTION_PRIVACY = OpenRouterPrivacyPolicy(
    embedding_zdr="required",
    reranking_zdr="optional",
    generation_zdr="required",
)


@dataclass(frozen=True)
class ZdrPreflightReport:
    """Authenticated roster classification. Never includes credentials."""

    embedding: ZdrStageStatus
    reranking: ZdrStageStatus
    generation: ZdrStageStatus
    missing_required_models: tuple[str, ...]


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _requirement(value: str | None, *, name: str) -> ZdrRequirement | None:
    raw = _normalized(value)
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered not in {"required", "optional"}:
        raise ValueError(f"{name} must be 'required' or 'optional'")
    return lowered  # type: ignore[return-value]


def _legacy_require_zdr(value: str | None) -> bool | None:
    raw = _normalized(value)
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered in _TRUE_TOKENS:
        return True
    if lowered in _FALSE_TOKENS:
        return False
    raise ValueError("FIRELENS_REQUIRE_ZDR must be a boolean")


def _denied_collection(value: str | None) -> DataCollectionPolicy:
    raw = _normalized(value)
    if raw is None:
        return "deny"
    if raw.lower() != "deny":
        raise ValueError("FIRELENS_DATA_COLLECTION must be 'deny'")
    return "deny"


def _disabled_fallbacks(value: str | None) -> Literal[False]:
    raw = _normalized(value)
    if raw is None:
        return False
    if raw.lower() not in _FALSE_TOKENS:
        raise ValueError("FIRELENS_ALLOW_FALLBACKS must be false")
    return False


def _required_parameters(value: str | None) -> Literal[True]:
    raw = _normalized(value)
    if raw is None:
        return True
    if raw.lower() not in _TRUE_TOKENS:
        raise ValueError("FIRELENS_REQUIRE_PARAMETERS must be true")
    return True


def resolve_openrouter_privacy_from_env(
    setting: _SETTING,
    *,
    default: OpenRouterPrivacyPolicy | None = None,
) -> OpenRouterPrivacyPolicy:
    """Resolve one privacy policy from environment or dotenv values.

    ``FIRELENS_REQUIRE_ZDR`` is a migration shim, not a second source of truth:

    - true, with no stage variables: approved production mix (rerank optional)
    - false, with no stage variables: all stages optional
    - stage variables win when they are consistent with the legacy flag
    - contradictory combinations are rejected
    """

    fallback = default if default is not None else LOCAL_DEFAULT_PRIVACY
    embedding = _requirement(setting("FIRELENS_EMBEDDING_ZDR"), name="FIRELENS_EMBEDDING_ZDR")
    reranking = _requirement(setting("FIRELENS_RERANKING_ZDR"), name="FIRELENS_RERANKING_ZDR")
    generation = _requirement(
        setting("FIRELENS_GENERATION_ZDR"), name="FIRELENS_GENERATION_ZDR"
    )
    legacy = _legacy_require_zdr(setting("FIRELENS_REQUIRE_ZDR"))
    data_collection = _denied_collection(setting("FIRELENS_DATA_COLLECTION"))
    allow_fallbacks = _disabled_fallbacks(setting("FIRELENS_ALLOW_FALLBACKS"))
    require_parameters = _required_parameters(setting("FIRELENS_REQUIRE_PARAMETERS"))
    stage_configured = any(value is not None for value in (embedding, reranking, generation))
    extras_configured = any(
        _normalized(setting(name)) is not None
        for name in (
            "FIRELENS_DATA_COLLECTION",
            "FIRELENS_ALLOW_FALLBACKS",
            "FIRELENS_REQUIRE_PARAMETERS",
        )
    )
    if not stage_configured and legacy is None and not extras_configured:
        return fallback
    if not stage_configured:
        if legacy is True:
            embedding, reranking, generation = "required", "optional", "required"
        else:
            embedding, reranking, generation = "optional", "optional", "optional"
    else:
        approved = APPROVED_PRODUCTION_PRIVACY
        if embedding is None:
            embedding = approved.embedding_zdr if legacy is True else fallback.embedding_zdr
        if reranking is None:
            reranking = approved.reranking_zdr if legacy is True else fallback.reranking_zdr
        if generation is None:
            generation = approved.generation_zdr if legacy is True else fallback.generation_zdr
        if legacy is False and "required" in {embedding, reranking, generation}:
            raise ValueError(
                "FIRELENS_REQUIRE_ZDR=false cannot be combined with a required ZDR stage"
            )
        if legacy is True and embedding == "optional":
            raise ValueError(
                "FIRELENS_REQUIRE_ZDR=true cannot set FIRELENS_EMBEDDING_ZDR=optional"
            )
        if legacy is True and generation == "optional":
            raise ValueError(
                "FIRELENS_REQUIRE_ZDR=true cannot set FIRELENS_GENERATION_ZDR=optional"
            )
    if embedding is None or reranking is None or generation is None:
        raise ValueError("OpenRouter privacy stage requirements are incomplete")
    return OpenRouterPrivacyPolicy(
        data_collection=data_collection,
        allow_fallbacks=allow_fallbacks,
        require_parameters=require_parameters,
        embedding_zdr=embedding,
        reranking_zdr=reranking,
        generation_zdr=generation,
    )


def privacy_from_candidate(document: Mapping[str, str]) -> OpenRouterPrivacyPolicy:
    """Load the bound candidate privacy fields without accepting v2 aliases."""

    return OpenRouterPrivacyPolicy(
        data_collection=document["data_collection"],  # type: ignore[arg-type]
        allow_fallbacks=False,
        require_parameters=True,
        embedding_zdr=document["embedding_zdr"],  # type: ignore[arg-type]
        reranking_zdr=document["reranking_zdr"],  # type: ignore[arg-type]
        generation_zdr=document["generation_zdr"],  # type: ignore[arg-type]
    )


def _classify(requirement: ZdrRequirement, model: str, eligible: set[str]) -> ZdrStageStatus:
    if model in eligible:
        return "eligible"
    return "failed" if requirement == "required" else "zdr_optional"


def evaluate_zdr_preflight(
    policy: OpenRouterPrivacyPolicy,
    *,
    embedding_model: str,
    rerank_model: str,
    generation_model: str,
    eligible_models: set[str],
) -> ZdrPreflightReport:
    """Classify configured models against one authenticated ZDR roster."""

    embedding = _classify(policy.embedding_zdr, embedding_model, eligible_models)
    reranking = _classify(policy.reranking_zdr, rerank_model, eligible_models)
    generation = _classify(policy.generation_zdr, generation_model, eligible_models)
    missing: list[str] = []
    if policy.embedding_zdr == "required" and embedding != "eligible":
        missing.append(embedding_model)
    if policy.reranking_zdr == "required" and reranking != "eligible":
        missing.append(rerank_model)
    if policy.generation_zdr == "required" and generation != "eligible":
        missing.append(generation_model)
    return ZdrPreflightReport(
        embedding=embedding,
        reranking=reranking,
        generation=generation,
        missing_required_models=tuple(missing),
    )


def initial_zdr_policy_state(policy: OpenRouterPrivacyPolicy) -> ZdrPolicyState:
    return "stage_bound_unprobed" if policy.any_zdr_required else "disabled"


def health_stage_state(
    requirement: ZdrRequirement,
    status: ZdrStageStatus | None,
    *,
    probed: bool,
) -> Literal["not_required", "unprobed", "eligible", "zdr_optional", "failed"]:
    if not probed:
        return "unprobed" if requirement == "required" else "not_required"
    if status is None:
        return "failed"
    return status
