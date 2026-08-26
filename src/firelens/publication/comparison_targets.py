"""Atomic publication targets for evacuation alert/order definition comparisons."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from firelens.answering.intent_lexicon import DEFINITION_WORDS, TOKEN
from firelens.contracts import RetrievalHit

ALERT_ORDER_ATOMIC_TARGETS = (
    "evacuation alert meaning",
    "evacuation order meaning",
)
ALERT_ORDER_ATOMIC_TARGET_SET = frozenset(ALERT_ORDER_ATOMIC_TARGETS)
MISSING_ASPECT_LIMITATION_PREFIX = "Not supported by selected evidence: "


def alert_order_comparison_targets(question: str) -> tuple[str, ...]:
    """Return atomic alert and order definition targets, or empty if not a comparison."""

    tokens = {match.group(0) for match in TOKEN.finditer(question.casefold())}
    if not (({"alert", "alerts"} & tokens) and ({"order", "orders"} & tokens)):
        return ()
    if not (tokens & DEFINITION_WORDS):
        return ()
    return ALERT_ORDER_ATOMIC_TARGETS


def publication_targets(question: str, supported_aspects: Sequence[str]) -> tuple[str, ...]:
    """Prefer atomic alert/order definition targets over the whole comparison question."""

    atomic = alert_order_comparison_targets(question)
    extras = [
        aspect.strip()
        for aspect in supported_aspects
        if aspect.strip() and aspect.strip() != question.strip()
    ]
    if atomic:
        return tuple(dict.fromkeys((*atomic, *extras)))
    return tuple(
        dict.fromkeys(
            target.strip() for target in (question, *supported_aspects) if target.strip()
        )
    )


def typed_subject_covers_atomic_target(subject: str | None, target: str) -> bool:
    return subject == target and target in ALERT_ORDER_ATOMIC_TARGET_SET


@lru_cache(maxsize=1)
def atomic_aspect_source_span_ids() -> dict[str, frozenset[str]]:
    """Map atomic comparison targets to admitted typed-claim source chunk IDs."""

    from firelens.publication.records import versioned_records

    mapping: dict[str, set[str]] = {target: set() for target in ALERT_ORDER_ATOMIC_TARGETS}
    for record in versioned_records():
        for target in ALERT_ORDER_ATOMIC_TARGETS:
            if typed_subject_covers_atomic_target(record.record.subject, target):
                mapping[target].update(record.source_span_ids)
    return {target: frozenset(chunk_ids) for target, chunk_ids in mapping.items() if chunk_ids}


def reserve_fused_atomic_hits(
    reranked_hits: Sequence[RetrievalHit],
    coverage_hits: Sequence[RetrievalHit],
    *,
    selection_aspects: Sequence[str],
    limit: int,
) -> list[RetrievalHit] | None:
    """Keep retrieved fused atomic spans that rerank dropped, without raising k."""

    atomic = ALERT_ORDER_ATOMIC_TARGET_SET.intersection(selection_aspects)
    if not atomic or not coverage_hits:
        return None
    wanted_by_target = atomic_aspect_source_span_ids()
    protected = set().union(*(wanted_by_target.get(target, ()) for target in atomic))
    selected = list(reranked_hits[:limit])
    selected_ids = {hit.chunk_id for hit in selected}
    for target in ALERT_ORDER_ATOMIC_TARGETS:
        if target not in atomic:
            continue
        wanted = wanted_by_target.get(target, frozenset())
        if selected_ids & wanted:
            continue
        replacement = next((hit for hit in coverage_hits if hit.chunk_id in wanted), None)
        if replacement is None:
            continue
        displaced = False
        for index in range(len(selected) - 1, -1, -1):
            if selected[index].chunk_id in protected:
                continue
            selected_ids.discard(selected[index].chunk_id)
            selected[index] = replacement
            selected_ids.add(replacement.chunk_id)
            displaced = True
            break
        if not displaced and len(selected) < limit:
            selected.append(replacement)
            selected_ids.add(replacement.chunk_id)
    return selected
