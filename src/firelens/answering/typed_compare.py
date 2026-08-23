"""Structured comparison of typed source and typed answer snapshots."""

from __future__ import annotations

import re

from firelens.answering.critical_fields import Comparator
from firelens.answering.typed_snapshot import (
    TypedSnapshot,
    extract_snapshot,
    objects_overlap,
    quantity_supported,
)

_OPPOSITE = {
    Comparator.AT_LEAST.value: {Comparator.AT_MOST.value, Comparator.LESS_THAN.value},
    Comparator.AT_MOST.value: {Comparator.AT_LEAST.value, Comparator.MORE_THAN.value},
    Comparator.MORE_THAN.value: {
        Comparator.LESS_THAN.value,
        Comparator.AT_MOST.value,
        Comparator.WITHIN.value,
    },
    Comparator.LESS_THAN.value: {Comparator.MORE_THAN.value, Comparator.AT_LEAST.value},
    Comparator.WITHIN.value: {Comparator.BEYOND.value, Comparator.OUTSIDE.value},
    Comparator.BEYOND.value: {Comparator.WITHIN.value, Comparator.AT_MOST.value},
    Comparator.BETWEEN.value: {Comparator.OUTSIDE.value, Comparator.BEYOND.value},
    Comparator.OUTSIDE.value: {Comparator.BETWEEN.value, Comparator.WITHIN.value},
}


def compare_snapshots(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    errors.extend(_quantity_errors(claim, source))
    errors.extend(_range_errors(claim, source))
    errors.extend(_comparator_errors(claim, source))
    errors.extend(_authority_errors(claim, source))
    errors.extend(_time_errors(claim, source))
    errors.extend(_freshness_errors(claim, source))
    errors.extend(_action_errors(claim, source))
    errors.extend(_urgency_errors(claim, source))
    errors.extend(_condition_errors(claim, source))
    errors.extend(_predicate_errors(claim, source))
    return list(dict.fromkeys(errors))


def typed_preservation_errors(claim: str, quotes: list[str]) -> list[str]:
    source = extract_snapshot("\n".join(quotes))
    answer = extract_snapshot(claim)
    return compare_snapshots(answer, source)


def _quantity_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    unsupported = [
        item for item in claim.quantities if not quantity_supported(item, source.quantities)
    ]
    if unsupported:
        errors.append("introduces an unsupported quantity or unit")
    source_numbers = {str(item.value.normalize()) for item in source.quantities}
    source_numbers.update(
        str(int(item.value))
        for item in source.quantities
        if item.value == item.value.to_integral()
    )
    if source.quantities and claim.bare_numbers:
        for number in claim.bare_numbers:
            if number in source_numbers and not claim.quantities:
                errors.append("removes a required unit from a sourced quantity")
                break
            if number in source_numbers and all(
                str(item.value.normalize()) != number and str(int(item.value)) != number
                for item in claim.quantities
            ):
                errors.append("removes a required unit from a sourced quantity")
                break
    return errors


def _range_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    if source.ranges and claim.ranges:
        source_pairs = {(item.low, item.high) for item in source.ranges}
        for item in claim.ranges:
            if (item.low, item.high) not in source_pairs:
                errors.append("changes a sourced numerical range")
            if (
                item.first != item.second
                and item.first == item.high
                and item.second == item.low
            ):
                if any(
                    sourced.first == item.second and sourced.second == item.first
                    for sourced in source.ranges
                ):
                    errors.append("reverses range boundaries")
    for mark in claim.exclusive_upper:
        if any(item.value == mark.value for item in source.inclusive_upper):
            errors.append("changes an inclusive boundary into an exclusive boundary")
    for mark in claim.inclusive_upper:
        if any(item.value == mark.value for item in source.exclusive_upper):
            errors.append("changes an exclusive boundary into an inclusive boundary")
    return errors


def _comparator_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    if not claim.comparators or not source.comparators:
        return []
    if any(
        item in _OPPOSITE.get(quote, set())
        for quote in source.comparators
        for item in claim.comparators
    ):
        return ["reverses a comparator"]
    return []


def _authority_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    source_names = {item.name for item in source.orgs if not item.generic}
    claim_names = {item.name for item in claim.orgs if not item.generic}
    introduced = sorted(claim_names - source_names)
    if introduced:
        errors.append("introduces or substitutes an unsupported authority")
    if any(item.generic for item in claim.orgs) and any(item.exclusive for item in source.orgs):
        errors.append("replaces an exclusive authority with a generic actor")
    introduced_j = sorted(claim.jurisdictions - source.jurisdictions)
    if introduced_j:
        errors.append("introduces or substitutes an unsupported jurisdiction")
    if source.municipalities and claim.province_wide and not claim.municipalities:
        errors.append("generalizes municipal guidance across a province")
    if source.regions and not claim.regions and not claim.municipalities:
        errors.append("removes a location or jurisdiction qualifier")
    return errors


def _time_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    source_retrieved = {item.token for item in source.times if item.role == "retrieved"}
    claim_updated = {item.token for item in claim.times if item.role == "source_updated"}
    if source.unknown_update and claim_updated:
        errors.append("describes retrieval time as an official source update time")
    if source_retrieved and claim_updated and source_retrieved & claim_updated:
        errors.append("describes retrieval time as an official source update time")
    introduced_dates = sorted(claim.dates - source.dates)
    if introduced_dates:
        errors.append("introduces an unsupported date")
    if source.dates and not claim.dates and not claim.has_condition_marker:
        errors.append("removes a date qualifier")
    return errors


def _freshness_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    if claim.freshness_live and (source.freshness_stale or source.unknown_update):
        return ["describes stale or dated guidance as current"]
    if claim.freshness_live and source.freshness_stale:
        return ["describes stale or dated guidance as current"]
    return []


def _action_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    for claimed in claim.actions:
        for sourced in source.actions:
            if claimed.lemma != sourced.lemma:
                continue
            if not objects_overlap(claimed.object_tokens, sourced.object_tokens):
                continue
            if claimed.polarity != sourced.polarity:
                errors.append("reverses an avoidance instruction")
    leave = {frame.lemma for frame in claim.actions}
    sourced_leave = {frame.lemma for frame in source.actions}
    if "leave" in sourced_leave and "stay" in leave and "stay" not in sourced_leave:
        errors.append("changes a required safety action")
    if "act" in sourced_leave and "wait" in leave:
        errors.append("changes a required safety action")
    if "wait" in sourced_leave and "act" in leave:
        errors.append("changes a required safety action")
    if source.must_not_return and claim.must_now_return:
        errors.append("changes the polarity of a safety action")
    return errors


def _urgency_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    if source.urgency_immediate and claim.urgency_delayed and not claim.urgency_immediate:
        return ["weakens immediate action into delay"]
    return []


def _condition_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    if source.has_condition_marker and not claim.has_condition_marker:
        optional = all(
            re.search(r"\b(?:want|wish|optional|possible)\b", item.body)
            for item in source.conditions
        ) and bool(source.conditions)
        if not optional:
            errors.append("removes a material condition from its quotes")
    for sourced in source.conditions:
        for claimed in claim.conditions:
            sourced_tokens = set(sourced.body.split())
            claimed_tokens = set(claimed.body.split())
            if sourced_tokens and claimed_tokens and sourced.negated != claimed.negated:
                overlap = sourced_tokens & claimed_tokens
                if len(overlap) >= min(3, len(sourced_tokens), len(claimed_tokens)):
                    errors.append("reverses a material condition")
    if source.exceptions and (not claim.exceptions or claim.exception_stripped):
        errors.append("removes a material exception")
    if source.restricted_group and claim.universal_group:
        errors.append("expands the applies-to group beyond the source")
    if source.regions and not claim.regions and not claim.has_condition_marker:
        errors.append("removes a location or jurisdiction qualifier")
    return errors


def _predicate_errors(claim: TypedSnapshot, source: TypedSnapshot) -> list[str]:
    errors: list[str] = []
    if source.all_clear == "negated" and claim.all_clear == "asserted":
        errors.append("changes the polarity of a safety action")
    source_defs = dict(source.definitions)
    claim_defs = dict(claim.definitions)
    if {"alert", "order"} <= source_defs.keys() and {"alert", "order"} <= claim_defs.keys():
        if _meanings_swapped(
            source_defs["alert"],
            source_defs["order"],
            claim_defs["alert"],
            claim_defs["order"],
        ):
            errors.append("swaps evacuation alert and order meanings")
    if source.downgrade and claim.upgrade:
        errors.append("reverses a status transition")
    if source.upgrade and claim.downgrade:
        errors.append("reverses a status transition")
    return errors


def _close_meaning(left: str, right: str) -> bool:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    return len(overlap) >= min(2, len(left_tokens), len(right_tokens))


def _meanings_swapped(
    source_alert: str, source_order: str, claim_alert: str, claim_order: str
) -> bool:
    return _close_meaning(claim_alert, source_order) and _close_meaning(
        claim_order, source_alert
    )
