"""Reviewed-guidance classification helpers for the typed intent automaton."""

from __future__ import annotations

from firelens.answering import intent_lexicon as lex

_STABLE_EVACUATION_ACTIONS = frozenset(
    {
        "action",
        "actions",
        "bag",
        "bags",
        "pack",
        "packing",
        "pet",
        "pets",
        "prepare",
        "ready",
        "respond",
        "response",
        "route",
        "vehicle",
    }
)


def is_evac_definition(tokens: tuple[str, ...]) -> bool:
    """Return whether a clause asks for a stable evacuation-term definition."""

    token_set = frozenset(tokens)
    if not (token_set & lex.EVACUATION_WORDS or token_set & {"evacuated", "evacuating"}):
        return False
    if token_set & lex.DEFINITION_WORDS:
        return True
    return bool(
        token_set & {"a", "an"}
        and (lex.has_phrase(tokens, ("what", "is")) or lex.has_phrase(tokens, ("what", "are")))
    )


def _is_control_stage_definition(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    asks_definition = bool(
        token_set & lex.DEFINITION_WORDS
        or token_set & {"explain", "define", "describe", "describes"}
        or lex.has_phrase(tokens, ("what", "is"))
    )
    if not asks_definition:
        return False
    return bool(
        lex.has_phrase(tokens, ("being", "held"))
        or lex.has_phrase(tokens, ("out", "of", "control"))
        or lex.has_phrase(tokens, ("under", "control"))
        or lex.has_phrase(tokens, ("fire", "of", "note"))
        or lex.has_phrase(tokens, ("stage", "of", "control"))
    )


def is_stable_evacuation_action(tokens: tuple[str, ...]) -> bool:
    """Keep non-current evacuation preparation and response in reviewed guidance."""

    token_set = frozenset(tokens)
    if not (token_set & lex.EVACUATION_WORDS or token_set & {"evacuated", "evacuating"}):
        return False
    if token_set & lex.CURRENT_WORDS or lex.has_any_phrase(tokens, lex.CURRENT_PHRASES):
        return False
    if token_set & {"listed", "record", "records", "reported"}:
        return False
    return bool(token_set & _STABLE_EVACUATION_ACTIONS)


def is_guidance(tokens: tuple[str, ...]) -> bool:
    """Return whether a clause owns reviewed stable-guidance semantics."""

    token_set = frozenset(tokens)
    if lex.has_any_phrase(tokens, lex.GUIDANCE_PHRASES):
        return True
    if token_set & lex.STRONG_GUIDANCE_TOPICS:
        return True
    # Broad, stable wildfire-smoke questions are source-backed public-health
    # guidance, even when a user asks conversationally rather than using one
    # of the catalogue's imperative verbs.  Keep them in the reviewed lane so
    # that a general-background answer never displaces available exact source
    # wording.  Current AQHI, forecast, and smoke-condition requests remain
    # live-source decisions in the higher-level router.
    current_smoke_measurement = bool(
        token_set
        & {
            "air",
            "aqhi",
            "condition",
            "conditions",
            "current",
            "forecast",
            "latest",
            "now",
            "quality",
            "today",
            "weather",
            "wind",
        }
        or lex.has_any_phrase(tokens, lex.CURRENT_PHRASES)
    )
    if (
        "smoke" in token_set
        and not current_smoke_measurement
        and (
            token_set
            & {
                "about",
                "affect",
                "children",
                "effect",
                "effects",
                "english",
                "health",
                "know",
                "pregnant",
                "protect",
                "protecting",
                "risk",
                "risks",
                "vulnerable",
            }
            or token_set & {"what", "how", "tell", "explain", "describe"}
        )
    ):
        return True
    if (
        "smoke" in token_set
        and token_set & {"n95", "respirator", "respirators", "mask", "masks"}
        and not current_smoke_measurement
    ):
        return True
    if is_evac_definition(tokens):
        return True
    if is_stable_evacuation_action(tokens):
        return True
    if token_set & {"pack", "packing"} and token_set & {"what", "should"}:
        return True
    if {"what", "should", "do"}.issubset(token_set) and token_set & lex.EVACUATION_WORDS:
        return True
    if (
        {"what", "do"}.issubset(token_set)
        and token_set & {"i", "we"}
        and token_set & lex.EVACUATION_WORDS
        and token_set & {"if", "after", "received", "receiving", "under"}
    ):
        return True
    generic_guidance = token_set & (lex.GUIDANCE_WORDS - lex.STRONG_GUIDANCE_TOPICS)
    governed_topic = bool(token_set & lex.GOVERNED_GUIDANCE_TOPICS)
    if generic_guidance and governed_topic:
        if token_set & lex.DEFINITION_WORDS:
            return True
        explicit_guidance_noun = bool(
            token_set & {"advice", "guidance", "tips", "checklist", "preparedness", "readiness"}
        )
        if explicit_guidance_noun:
            return True
        if token_set & lex.CURRENT_WORDS or lex.has_any_phrase(tokens, lex.CURRENT_PHRASES):
            return False
        return True
    if token_set & lex.GUIDANCE_ACTIONS and token_set & lex.GOVERNED_GUIDANCE_TOPICS:
        return True
    if (
        "smoke" in token_set
        and token_set & {"home", "house", "property"}
        and token_set & {"can", "do", "how", "what"}
    ):
        return True
    if token_set & {"meaning", "mean"} and lex.has_fire(tokens):
        return True
    return _is_control_stage_definition(tokens)
