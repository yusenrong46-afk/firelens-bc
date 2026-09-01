"""Typed static-guidance retrieval subjects used at the reviewed RAG boundary."""

from __future__ import annotations

from enum import StrEnum

from firelens.answering import intent_lexicon as lex
from firelens.answering.request_facets import contents_request_facet


class StaticGuidanceSubject(StrEnum):
    """Narrow static subjects that may supply a retrieval target.

    This classifies a request shape only. It neither admits a claim nor
    selects a source passage; those remain the reviewed-publication pipeline's
    responsibility.
    """

    EMERGENCY_KIT = "emergency_kit"
    PET_GRAB_AND_GO = "pet_grab_and_go"
    WILDFIRE_SMOKE = "wildfire_smoke"


_KIT_GUIDANCE_TOKENS = frozenset({"kit", "kits"})
_BAG_GUIDANCE_TOKENS = frozenset({"bag", "bags"})
_BAG_GUIDANCE_QUALIFIERS = frozenset({"emergency", "evacuation", "grab", "go"})
_PET_GUIDANCE_TOKENS = frozenset({"pet", "pets", "animal", "animals"})
_EVACUATION_GUIDANCE_TOKENS = frozenset({"evacuation", "evacuate", "evacuated", "evacuating"})
_SMOKE_GUIDANCE_TOKENS = frozenset({"smoke", "smoky"})
_SMOKE_RESPIRATOR_TOKENS = frozenset({"n95", "respirator", "respirators"})
_SMOKE_EFFECT_TOKENS = frozenset(
    {"effect", "effects", "health", "harm", "harmful", "impact", "impacts"}
)
_SMOKE_SPECIFIC_TOKENS = frozenset(
    {
        "baby",
        "babies",
        "child",
        "children",
        "home",
        "house",
        "indoor",
        "indoors",
        "infant",
        "infants",
        "older",
        "pregnant",
    }
)


def static_guidance_subject(question: str) -> StaticGuidanceSubject | None:
    """Resolve a bounded guidance subject across an already-composed turn.

    Conversation planning may attach the prior user subject to a short
    follow-up. Classifying the combined token set keeps a pet question
    attached to its preceding kit topic without treating pets alone as an
    admitted preparedness claim.
    """

    tokens = frozenset(lex.tokenize(question))
    if tokens & _SMOKE_GUIDANCE_TOKENS and "wildfire" in tokens:
        return StaticGuidanceSubject.WILDFIRE_SMOKE
    kit_subject = bool(tokens & _KIT_GUIDANCE_TOKENS) or bool(
        tokens & _BAG_GUIDANCE_TOKENS and tokens & _BAG_GUIDANCE_QUALIFIERS
    )
    if tokens & _PET_GUIDANCE_TOKENS and (kit_subject or tokens & _EVACUATION_GUIDANCE_TOKENS):
        return StaticGuidanceSubject.PET_GRAB_AND_GO
    if not kit_subject:
        return None
    return StaticGuidanceSubject.EMERGENCY_KIT


def static_guidance_retrieval_query(question: str) -> str | None:
    """Return the controlled retrieval target for a typed static subject."""

    subject = static_guidance_subject(question)
    if subject == StaticGuidanceSubject.PET_GRAB_AND_GO:
        # A retrieval target, not a generated recommendation: exact source
        # passage selection and quote-only publication remain mandatory.
        return "pets emergency kit grab-and-go bag food water leashes carriers"
    if subject == StaticGuidanceSubject.WILDFIRE_SMOKE:
        # Prefer the clean governed BCCDC protection section over adjacent PDF
        # fragments whose extraction order and bullet glyphs are unsuitable as
        # a reader-facing answer. Publication still requires an admitted exact
        # quotation from the returned evidence packet.
        tokens = frozenset(lex.tokenize(question))
        if tokens & _SMOKE_RESPIRATOR_TOKENS:
            return "N95 respirators wildfire smoke"
        if tokens & _SMOKE_SPECIFIC_TOKENS:
            return " ".join(question.split())
        if tokens & _SMOKE_EFFECT_TOKENS:
            return "wildfire smoke health effects"
        return "protect yourself from wildfire smoke"
    if subject == StaticGuidanceSubject.EMERGENCY_KIT:
        contents = contents_request_facet(question)
        if contents is not None:
            # Preserve the user's container while preventing a model-proposed
            # query from inheriting an unrelated subject from conversation.
            return contents.retrieval_query
        return "emergency kit contents checklist"
    return None
