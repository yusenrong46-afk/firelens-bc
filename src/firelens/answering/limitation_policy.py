"""Select the smallest material public limitation set."""

from __future__ import annotations

import re

from firelens.contracts import BACKGROUND_LIMITATION

_BOILERPLATE = (
    re.compile(r"uses official records and is not a safety assessment", re.I),
    re.compile(r"uses stable guidance", re.I),
    re.compile(r"static corpus cannot establish", re.I),
    re.compile(r"exact source wording", re.I),
    re.compile(r"general background", re.I),
    re.compile(r"no reviewed structured claim", re.I),
)
_SAFETY = (
    re.compile(r"cannot (?:provide|make) personal", re.I),
    re.compile(r"not a safety determination", re.I),
    re.compile(r"did not substitute", re.I),
    re.compile(r"not an all-clear", re.I),
    re.compile(r"unavailable", re.I),
    re.compile(r"stale", re.I),
    re.compile(r"source failure", re.I),
)


def select_public_limitations(items: list[str], *, max_material: int = 1) -> list[str]:
    """Keep one material limit plus any safety-critical boundary."""

    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        text = " ".join(item.split())
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    required = [item for item in unique if item == BACKGROUND_LIMITATION]
    safety = [
        item
        for item in unique
        if item not in required and any(pattern.search(item) for pattern in _SAFETY)
    ]
    material = [
        item
        for item in unique
        if item not in required
        and item not in safety
        and not any(pattern.search(item) for pattern in _BOILERPLATE)
    ]
    selected = required + safety
    for item in material:
        if (
            len([entry for entry in selected if entry not in required and entry not in safety])
            >= max_material
        ):
            break
        if item not in selected:
            selected.append(item)
    return selected or unique[:1]
