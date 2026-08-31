"""Compatibility exports for evidence packet construction and support checks.

``context`` remains the stable import surface used by the answering service,
publication compiler, and tests. Packet construction and lexical support
decisions are split into cohesive internal modules so each authority boundary
is small enough to inspect independently.
"""

from firelens.answering.context_packet import (
    _CONFLICT_CUES,
    EvidenceGroup,
    EvidenceIndex,
    _candidate_chunk_ids,
    _detect_conflicts,
    _exact_quote_segments,
    _select_evidence_hits,
    build_evidence_packet,
)
from firelens.answering.context_support import (
    _ADMINISTRATIVE_STEMS,
    _ASPECT_STOPWORDS,
    _EXCLUSION_DIRECTION_TOKENS,
    _EXCLUSION_EVIDENCE,
    _EXCLUSION_REQUEST,
    SUPPORT_TOKEN_OVERLAP_FLOOR,
    _aspect_support_decision,
    _aspect_supported,
    _authority_support_decision,
    _direct_exclusion_evidence,
    _exclusion_topic,
    _has_exclusion_evidence,
    _immediate_support_decision,
    _requires_exclusion_evidence,
    _support_tokens,
    decide_support,
    support_token_overlap,
)

__all__ = [
    "EvidenceGroup",
    "EvidenceIndex",
    "SUPPORT_TOKEN_OVERLAP_FLOOR",
    "_ADMINISTRATIVE_STEMS",
    "_ASPECT_STOPWORDS",
    "_CONFLICT_CUES",
    "_EXCLUSION_DIRECTION_TOKENS",
    "_EXCLUSION_EVIDENCE",
    "_EXCLUSION_REQUEST",
    "_aspect_supported",
    "_aspect_support_decision",
    "_authority_support_decision",
    "_candidate_chunk_ids",
    "_detect_conflicts",
    "_direct_exclusion_evidence",
    "_exact_quote_segments",
    "_exclusion_topic",
    "_has_exclusion_evidence",
    "_immediate_support_decision",
    "_requires_exclusion_evidence",
    "_select_evidence_hits",
    "_support_tokens",
    "build_evidence_packet",
    "decide_support",
    "support_token_overlap",
]
