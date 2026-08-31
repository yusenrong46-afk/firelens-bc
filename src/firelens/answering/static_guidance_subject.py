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


_KIT_GUIDANCE_TOKENS = frozenset({"kit", "kits"})
_BAG_GUIDANCE_TOKENS = frozenset({"bag", "bags"})
_BAG_GUIDANCE_QUALIFIERS = frozenset({"emergency", "evacuation", "grab", "go"})
_PET_GUIDANCE_TOKENS = frozenset({"pet", "pets", "animal", "animals"})


def static_guidance_subject(question: str) -> StaticGuidanceSubject | None:
    """Resolve a bounded guidance subject across an already-composed turn.

    Conversation planning may attach the prior user subject to a short
    follow-up. Classifying the combined token set keeps a pet question
    attached to its preceding kit topic without treating pets alone as an
    admitted preparedness claim.
    """

    tokens = frozenset(lex.tokenize(question))
    kit_subject = bool(tokens & _KIT_GUIDANCE_TOKENS) or bool(
        tokens & _BAG_GUIDANCE_TOKENS and tokens & _BAG_GUIDANCE_QUALIFIERS
    )
    if not kit_subject:
        return None
    if tokens & _PET_GUIDANCE_TOKENS:
        return StaticGuidanceSubject.PET_GRAB_AND_GO
    return StaticGuidanceSubject.EMERGENCY_KIT


def static_guidance_retrieval_query(question: str) -> str | None:
    """Return the controlled retrieval target for a typed static subject."""

    subject = static_guidance_subject(question)
    if subject == StaticGuidanceSubject.PET_GRAB_AND_GO:
        # A retrieval target, not a generated recommendation: exact source
        # passage selection and quote-only publication remain mandatory.
        return "pets emergency kit grab-and-go bag food water leashes carriers"
    # Preserve a user's explicit container wording; request_facets owns that
    # more precise syntax. The typed subject only supplies a target where the
    # request says "kit guidance" rather than what it wants inside the kit.
    if contents_request_facet(question) is not None:
        return None
    if subject == StaticGuidanceSubject.EMERGENCY_KIT:
        return "emergency kit contents checklist"
    return None
