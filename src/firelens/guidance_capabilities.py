"""Hash-bound, application-owned guided-question catalogue.

The catalogue is a navigation and routing contract, not evidence. It may select
deterministic retrieval aspects, but it never grants publication authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field

from firelens.answering.typed_records import load_inventory
from firelens.contract_base import FrozenStrictModel

REGISTRY_RELATIVE_PATH = "data/capabilities/guided_questions.v1.json"
MANIFEST_RELATIVE_PATH = "data/capabilities/guided_questions.v1.manifest.json"
CAPABILITY_REGISTRY_RELATIVE_PATH = "data/capabilities/firelens.guidance_capabilities.v1.json"

SourceLane = Literal["official_live", "reviewed_guidance", "official_quote"]
LocationMode = Literal["none", "required"]
SourceMode = Literal["corpus", "official_live"]


class GuidedQuestion(FrozenStrictModel):
    id: str = Field(pattern=r"^GQ-[0-9]{2}$")
    label: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=240)
    location_mode: LocationMode
    source_lane: SourceLane
    required_aspects: tuple[str, ...] = Field(default=(), max_length=6)


class GuidedCategory(FrozenStrictModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=120)
    questions: tuple[GuidedQuestion, ...] = Field(min_length=1, max_length=8)


class GuidedQuestionRegistry(FrozenStrictModel):
    schema_version: Literal["firelens.guided_questions.v1"]
    categories: tuple[GuidedCategory, ...] = Field(min_length=1, max_length=8)

    @property
    def questions(self) -> tuple[GuidedQuestion, ...]:
        return tuple(
            question for category in self.categories for question in category.questions
        )


class GuidedQuestionManifest(FrozenStrictModel):
    schema_version: Literal["firelens.guided_questions.manifest.v1"]
    registry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    question_count: int = Field(ge=1, le=64)


class CapabilityAspect(FrozenStrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    text: str = Field(min_length=2, max_length=160)


class CapabilityBinding(FrozenStrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    category: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    source_mode: SourceMode
    coverage_state: Literal["structured_ready", "quote_ready", "handoff_only"]
    match_kind: Literal[
        "exact_normalized_whitespace_case", "conservative_immediate_danger_contact"
    ]
    canonical_questions: tuple[str, ...] = Field(min_length=1, max_length=3)
    retrieval_queries: tuple[str, ...] = Field(min_length=1, max_length=3)
    aspects: tuple[CapabilityAspect, ...] = Field(min_length=1, max_length=6)
    required_authority_classes: tuple[str, ...] = Field(min_length=1, max_length=4)
    typed_claim_ids: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()
    exact_quote_texts: tuple[str, ...] = Field(default=(), max_length=6)
    accepted_paraphrases: tuple[str, ...] = Field(default=(), max_length=16)
    live_layers: tuple[str, ...] = ()
    guided_eligible: bool = True
    guided_question_ids: tuple[str, ...] = ()


class CapabilityRegistry(FrozenStrictModel):
    schema_version: Literal["firelens.guidance_capabilities.v1"]
    corpus_chunks_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    typed_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capabilities: tuple[CapabilityBinding, ...]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_guided_question(value: str) -> str:
    """Normalize only whitespace and case for an exact catalogue lookup."""

    return " ".join(value.split()).casefold()


@lru_cache(maxsize=4)
def load_guided_question_registry(root: str | None = None) -> GuidedQuestionRegistry:
    base = Path(root) if root else _project_root()
    registry_path = base / REGISTRY_RELATIVE_PATH
    manifest_path = base / MANIFEST_RELATIVE_PATH
    raw = registry_path.read_bytes()
    manifest = GuidedQuestionManifest.model_validate_json(manifest_path.read_text("utf-8"))
    if hashlib.sha256(raw).hexdigest() != manifest.registry_sha256:
        raise ValueError("guided-question registry hash does not match its manifest")
    registry = GuidedQuestionRegistry.model_validate(json.loads(raw))
    if len(registry.questions) != manifest.question_count:
        raise ValueError("guided-question registry count does not match its manifest")
    if len({question.id for question in registry.questions}) != len(registry.questions):
        raise ValueError("guided-question registry has duplicate question IDs")
    return registry


def guided_catalogue_sha256(root: str | None = None) -> str:
    base = Path(root) if root else _project_root()
    return hashlib.sha256((base / REGISTRY_RELATIVE_PATH).read_bytes()).hexdigest()


def _corpus_chunks(root: Path) -> dict[str, dict[str, object]]:
    corpus = root / "data/processed/firelens_static_corpus.chunks.jsonl"
    return {
        str(record["chunk_id"]): record
        for line in corpus.read_text("utf-8").splitlines()
        if line.strip()
        for record in (json.loads(line),)
    }


def _expected_source_lane(binding: CapabilityBinding) -> SourceLane:
    if binding.source_mode == "official_live":
        return "official_live"
    if binding.coverage_state == "quote_ready":
        return "official_quote"
    return "reviewed_guidance"


@lru_cache(maxsize=4)
def load_validated_capabilities(root: str | None = None) -> dict[str, CapabilityBinding]:
    """Validate every binding against the current admitted corpus and inventory."""

    base = Path(root) if root else _project_root()
    registry = CapabilityRegistry.model_validate_json(
        (base / CAPABILITY_REGISTRY_RELATIVE_PATH).read_text("utf-8")
    )
    identities = {
        "corpus_chunks_sha256": hashlib.sha256(
            (base / "data/processed/firelens_static_corpus.chunks.jsonl").read_bytes()
        ).hexdigest(),
        "corpus_manifest_sha256": hashlib.sha256(
            (base / "data/processed/firelens_static_corpus.manifest.json").read_bytes()
        ).hexdigest(),
        "typed_inventory_sha256": hashlib.sha256(
            (base / "data/typed_claims/high_risk_v1.yaml").read_bytes()
        ).hexdigest(),
    }
    if any(getattr(registry, name) != value for name, value in identities.items()):
        raise ValueError(
            "capability registry identity does not match current corpus or inventory"
        )
    chunks = _corpus_chunks(base)
    inventory = {
        record.claim_id: record
        for record in load_inventory(str(base)).records
        if record.production_supported()
    }
    result: dict[str, CapabilityBinding] = {}
    guided = {item.id: item for item in load_guided_question_registry(str(base)).questions}
    for binding in registry.capabilities:
        if binding.id in result:
            raise ValueError("capability registry has duplicate IDs")
        if any(
            layer not in {"incident", "perimeter", "evacuation"}
            for layer in binding.live_layers
        ):
            raise ValueError(f"{binding.id} uses an unsupported live layer")
        if any(question_id not in guided for question_id in binding.guided_question_ids):
            raise ValueError(f"{binding.id} references an unknown guided question")
        if binding.guided_eligible != bool(binding.guided_question_ids):
            raise ValueError(f"{binding.id} has inconsistent guided eligibility")
        if len({aspect.id for aspect in binding.aspects}) != len(binding.aspects):
            raise ValueError(f"{binding.id} has duplicate aspect IDs")
        if binding.source_mode == "official_live" and (
            not binding.live_layers or binding.typed_claim_ids or binding.chunk_ids
        ):
            raise ValueError(f"{binding.id} has inconsistent live source bindings")
        if binding.source_mode == "corpus" and binding.live_layers:
            raise ValueError(f"{binding.id} mixes corpus and live source bindings")
        if binding.coverage_state == "structured_ready" and not (
            binding.typed_claim_ids or binding.live_layers
        ):
            raise ValueError(f"{binding.id} lacks structured source bindings")
        if binding.coverage_state == "quote_ready" and (
            not binding.chunk_ids or not binding.exact_quote_texts
        ):
            raise ValueError(f"{binding.id} lacks atomic quote source bindings")
        if binding.source_mode != "corpus" and binding.exact_quote_texts:
            raise ValueError(f"{binding.id} has quotes outside corpus coverage")
        if set(binding.typed_claim_ids) - inventory.keys():
            raise ValueError(f"{binding.id} references an unknown or unapproved typed claim")
        if set(binding.chunk_ids) - chunks.keys():
            raise ValueError(f"{binding.id} references an unknown corpus chunk")
        typed_chunks = {
            chunk_id
            for claim_id in binding.typed_claim_ids
            for chunk_id in inventory[claim_id].source_span_ids
        }
        if typed_chunks - set(binding.chunk_ids):
            raise ValueError(f"{binding.id} omits a typed claim's bound corpus chunk")
        if any(
            str(chunks[chunk_id]["authority_class"]) not in binding.required_authority_classes
            for chunk_id in binding.chunk_ids
        ):
            raise ValueError(f"{binding.id} has a chunk outside its authority classes")
        if any(
            not any(quote in str(chunks[chunk_id]["text"]) for chunk_id in binding.chunk_ids)
            for quote in binding.exact_quote_texts
        ):
            raise ValueError(f"{binding.id} has an exact quote outside its bound chunks")
        for question_id in binding.guided_question_ids:
            item = guided[question_id]
            if item.source_lane != _expected_source_lane(binding):
                raise ValueError(f"{binding.id} does not match its advertised source lane")
            if item.required_aspects != tuple(aspect.text for aspect in binding.aspects):
                raise ValueError(f"{binding.id} does not match its advertised aspects")
        result[binding.id] = binding
    return result


def advertised_guided_questions(root: str | None = None) -> tuple[GuidedQuestion, ...]:
    """Return only validated, non-handoff catalogue entries."""

    bindings = load_validated_capabilities(root)
    return tuple(
        item
        for item in load_guided_question_registry(root).questions
        if any(
            item.id in binding.guided_question_ids
            and binding.guided_eligible
            and binding.coverage_state != "handoff_only"
            for binding in bindings.values()
        )
    )


_FIRE_CONTEXT = re.compile(r"\b(?:wildfire|wild fire|fire|flames?)\b", re.IGNORECASE)
_IMMEDIATE_EMERGENCY_CONDITION = re.compile(
    r"\b(?:immediate\s+danger|trapped|(?:unable\s+to|cannot|can't)\s+evacuate|"
    r"medical\s+emergency|safety\s+emergency)\b",
    re.IGNORECASE,
)
_STRUCTURE_FIRE_EMERGENCY = re.compile(
    r"\b(?:flames?|fire|wildfire)\b.{0,48}\b(?:near|at|by|beside|against)\b.{0,32}"
    r"\b(?:houses?|homes?|buildings?|structures?)\b|"
    r"\b(?:houses?|homes?|buildings?|structures?)\b.{0,40}"
    r"\b(?:on fire|burning|in flames)\b",
    re.IGNORECASE,
)
_CONTACT_ACTION = re.compile(
    r"\b(?:who\s+(?:should|do|can)\s+i\s+(?:call|contact)|who\s+to\s+(?:call|contact)|"
    r"call|contact|9[ -]?1[ -]?1|emergency\s+(?:number|contact))\b",
    re.IGNORECASE,
)


def capability_for_guided_question(
    guided_question_id: str, *, root: str | None = None
) -> CapabilityBinding | None:
    return next(
        (
            binding
            for binding in load_validated_capabilities(root).values()
            if guided_question_id in binding.guided_question_ids
        ),
        None,
    )


def resolve_capability(
    question: str,
    *,
    place_label: str | None = None,
    root: str | None = None,
) -> CapabilityBinding | None:
    """Resolve only exact guided questions or one conservative safety capability."""

    guided = exact_guided_question(question, place_label=place_label, root=root)
    if guided is not None:
        return capability_for_guided_question(guided.id, root=root)
    capabilities = load_validated_capabilities(root)
    normalized = normalize_guided_question(question)
    for binding in capabilities.values():
        accepted = {
            normalize_guided_question(candidate)
            for candidate in (*binding.canonical_questions, *binding.accepted_paraphrases)
        }
        if normalized in accepted:
            return binding
    if _CONTACT_ACTION.search(question) and (
        (_FIRE_CONTEXT.search(question) and _IMMEDIATE_EMERGENCY_CONDITION.search(question))
        or _STRUCTURE_FIRE_EMERGENCY.search(question)
    ):
        return capabilities.get("immediate_danger_contact")
    return None


def exact_guided_question(
    question: str,
    *,
    place_label: str | None = None,
    root: str | None = None,
) -> GuidedQuestion | None:
    """Return a catalogue item only for an exact canonical question.

    Location templates deliberately do not match until the client has expanded
    ``{place}`` from the existing location value.
    """

    normalized = normalize_guided_question(question)
    advertised = {item.id for item in advertised_guided_questions(root)}
    for item in load_guided_question_registry(root).questions:
        if item.id not in advertised:
            continue
        template = item.question
        if "{place}" in template:
            if not place_label:
                continue
            template = template.replace("{place}", place_label)
        if normalized == normalize_guided_question(template):
            return item
    return None
