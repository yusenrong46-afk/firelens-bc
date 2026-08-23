"""Deterministic risk may only stay or rise."""

from __future__ import annotations

_RANK = {"A": 3, "B": 2, "C": 1}


def effective_risk(deterministic: str, proposed: str) -> str:
    if deterministic not in _RANK or proposed not in _RANK:
        raise ValueError("unknown risk tier")
    return deterministic if _RANK[deterministic] >= _RANK[proposed] else proposed


def lower_risk(from_tier: str, to_tier: str) -> str:
    if from_tier not in _RANK or to_tier not in _RANK:
        raise ValueError("unknown risk tier")
    if _RANK[to_tier] < _RANK[from_tier]:
        raise ValueError("risk may only rise")
    return to_tier
