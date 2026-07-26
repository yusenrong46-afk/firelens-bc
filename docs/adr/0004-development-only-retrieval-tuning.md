# ADR 0004: Development-only retrieval tuning

Status: accepted
Date: 2026-07-26

Retrieval configuration selection uses only development labels. All candidates
are compared at Recall@5 even if a candidate exposes more context passages. A
candidate must improve Recall@5 by at least two percentage points without
reducing required-source coverage. The holdout projection is hash-frozen and is
never opened by the tuning command.
