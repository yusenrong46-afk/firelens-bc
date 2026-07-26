# R1.3 Deterministic BM25 Baseline

> Historical executed subsystem note. Current retrieval configuration and
> measured comparisons are recorded in `docs/TECHNICAL_HANDBOOK.md`.

Date: `2026-07-25`

## Purpose

Prove that FireLens can rank useful evidence before adding embeddings or an
LLM. BM25 is a deterministic lexical baseline: semantic retrieval must later
beat it on the same gold questions.

## Contract

- input is validated `ChunkRecord` JSONL;
- output is a ranked list of `RetrievalResult` objects;
- every result retains chunk, page, source, publisher and URL provenance;
- only positive lexical matches are returned;
- ties are broken deterministically by `chunk_id`;
- a retrieval score is relevance ranking, not proof of answerability.

## Scoring

The implementation uses Okapi BM25 with:

```text
k1 = 1.5
b = 0.75
```

Terms shared by query and chunk raise the score. Rare terms receive more
weight. Repetition has diminishing returns, and length normalization prevents
long chunks from winning only because they contain more words.

## Current evaluation

The corpus currently contains only the PreparedBC Wildfire Preparedness Guide.
Seven gold questions have evidence entirely within that source.

```text
Hit@3: 7 / 7
Hit@5: 7 / 7
```

The pet-preparation question retrieves page 6 at rank 2 rather than rank 1.
This is acceptable for the baseline and becomes a concrete semantic-retrieval
comparison case.

The evacuation-order test initially expected page 11 at rank 1. BM25 ranked
page 10 first because page 10 contains the official evacuation-stage summary.
The gold contract identifies both pages 10 and 11 as relevant, so the test was
corrected rather than distorting the retriever.

## Known limitation

BM25 matches words, not meanings. It can return chunks for an unsupported or
live-status question because words such as `wildfire` occur in the corpus.
FireLens must implement answerability and live-intent routing separately.
BM25 scores must never be treated as confidence that an answer is safe.
