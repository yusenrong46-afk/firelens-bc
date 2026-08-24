"""Deterministic request facets shared by retrieval and publication."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentsRequestFacet:
    """A request for the items contained in a named container."""

    container: str
    retrieval_query: str


_CONTAINER_AFTER_PREPOSITION = re.compile(
    r"\bwhat\b.{0,100}\b(?:be|need|have|put|pack(?:s|ed|ing)?|include(?:s|d|ing)?|"
    r"store(?:s|d|ing)?|keep|cop(?:y|ies|ied|ying)|belong(?:s|ed|ing)?|"
    r"go(?:es|ing)?)\b.{0,40}\b(?:in|into|inside)\b\s+(?P<container>.+)$",
    re.IGNORECASE,
)
_CONTAINER_BEFORE_RELATION = re.compile(
    r"\bwhat\b\s+(?:(?:can|could|does|do|should|must|might|would)\s+)?"
    r"(?P<container>.+?)\s+(?:contain|include)(?:s|d|ing)?\b",
    re.IGNORECASE,
)
_CONTAINER_AFTER_LIST_REQUEST = re.compile(
    r"\b(?:list|name)\b(?:\s+the)?\s+(?:contents?|items?|supplies|equipment)\b"
    r".{0,30}\b(?:in|inside|for|of)\b\s+(?P<container>.+)$",
    re.IGNORECASE,
)
_CONTENTS_REQUEST_WITHOUT_CONTAINER = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwhat\b.{0,100}\b(?:contain|include)(?:s|d|ing)?\b",
        r"\b(?:list|name)\b.{0,100}\b(?:contents?|items?|supplies|equipment)\b",
    )
)
_TRAILING_QUALIFIER = re.compile(
    r"\s+(?:for\s+(?:me|my|us|our|you|your)\b|during\b|before\b|when\b|"
    r"while\b|so\s+that\b).*$",
    re.IGNORECASE,
)
_LEADING_DETERMINER = re.compile(r"^(?:a|an|the|my|our|your)\s+", re.IGNORECASE)


def _normalize_container(value: str) -> str | None:
    container = re.sub(r"[?.!,;:]+$", "", value.strip())
    container = _TRAILING_QUALIFIER.sub("", container).strip()
    container = _LEADING_DETERMINER.sub("", container).strip()
    container = " ".join(container.split())
    if not container or container.casefold() in {"it", "this", "that", "them"}:
        return None
    if len(container.split()) > 12:
        return None
    return container


def contents_request_facet(question: str) -> ContentsRequestFacet | None:
    """Return a container-focused retrieval facet for a contents question.

    The extraction is deliberately syntactic and container-agnostic. It does
    not infer a product, inject a corpus identifier, or broaden retrieval.
    """

    normalized = " ".join(question.split())
    for pattern in (
        _CONTAINER_AFTER_PREPOSITION,
        _CONTAINER_BEFORE_RELATION,
        _CONTAINER_AFTER_LIST_REQUEST,
    ):
        match = pattern.search(normalized)
        if match is None:
            continue
        container = _normalize_container(match.group("container"))
        if container is not None:
            return ContentsRequestFacet(
                container=container,
                retrieval_query=f"{container} contents checklist",
            )
    return None


def requests_contents(question: str) -> bool:
    """Return whether a question requests actual contents, not construction."""

    normalized = " ".join(question.split())
    return contents_request_facet(normalized) is not None or any(
        pattern.search(normalized) for pattern in _CONTENTS_REQUEST_WITHOUT_CONTAINER
    )
