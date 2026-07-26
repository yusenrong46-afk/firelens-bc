# FireLens BC R2 Full RAG Build Plan

> Historical implementation plan. It is superseded by
> `docs/TECHNICAL_HANDBOOK.md` and the V1 evidence ledger.

Date: `2026-07-25`  
Status: scoped R2 implementation sequence; architecture is governed by
`docs/firelens_complete_system_design.md`  
Scope: verified static-guidance RAG, before live wildfire-status tools

> Reconciliation note (2026-07-25): the model names below are experiment
> baselines. In particular, Gemini 3.5 Flash Lite is not promoted to production
> default until it passes the model bake-off and hard safety gates in the
> complete system design.

## 1. Outcome

R2 turns the existing evidence corpus and BM25 baseline into the first complete
FireLens RAG path:

```text
user question
  -> safety and freshness routing
  -> BM25 retrieval
  + semantic retrieval
  -> Reciprocal Rank Fusion
  -> Cohere Rerank 4 Pro
  -> bounded evidence packet
  -> Gemini 3.5 Flash-Lite answer draft
  -> deterministic schema, citation, and safety checks
  -> cited guidance or abstention
```

This is a full static RAG system because it retrieves approved evidence,
generates an answer from that evidence, verifies the answer contract, and
returns traceable citations. It is not yet the first customer MVP because it
does not provide current incident, evacuation, weather, or air-quality data.

## 2. Current verified foundation

The repository already contains:

- ten reviewed source-registry entries;
- eight approved static sources in the corpus;
- 175 citation-preserving chunks;
- PDF page and HTML section provenance;
- content hashes and hash-pinned human-reviewed repair;
- deterministic BM25 search;
- 20 evidence-anchored gold questions;
- recorded BM25 Hit@5 of `15/17` (`88.2%`);
- recorded BM25 MRR@5 of `0.755`;
- recorded mean source coverage@5 of `82.4%`;
- three current or predictive questions skipped by static retrieval design.

The two explicit lexical misses are:

- `GQ005`: broad practical FireSmart actions;
- `GQ019`: the adversarial claim that FireSmart guarantees survival.

Current reproducibility gap: this downloaded checkout contains no Python
dependency manifest or virtual environment. A fresh test attempt on 2026-07-25
failed during import because PyYAML, lxml, pypdf, and related packages were not
installed. The prior `27/27` result remains historical checkpoint evidence, not
a newly reproduced result.

## 3. Locked model route

All external model requests use OpenRouter credit through one credential:

| Responsibility | Model | Endpoint |
| --- | --- | --- |
| chunk and query embeddings | `openai/text-embedding-3-small` | `/api/v1/embeddings` |
| final candidate reranking | `cohere/rerank-4-pro` | `/api/v1/rerank` |
| default grounded generation | `google/gemini-3.5-flash-lite` | `/api/v1/chat/completions` |
| later quality challenger/fallback | `google/gemini-3.6-flash` | `/api/v1/chat/completions` |

Default Gemini generation uses low reasoning. Deprecated sampling controls such
as temperature and top-p are omitted. Model IDs, routing settings, latency,
token usage, estimated cost, retries, and response validation status are
recorded for evaluation.

OpenRouter is only the external model gateway. Corpus building, BM25, vector
storage, cosine similarity, RRF, evidence validation, and safety enforcement
remain local.

## 4. Non-negotiable authority boundary

```text
official source bytes
  -> reviewed extraction
  -> citation-preserving chunks
  -> retrieval candidates
  -> reranked evidence
  -> model-written draft
  -> FireLens validation
  -> user answer
```

- Retrieval scores are relevance signals, not truth or answerability.
- Rerank scores are ordering signals, not confidence.
- The LLM is a writer and router, never an evidence source.
- Only evidence IDs supplied in the request may appear in an answer.
- Current-status questions cannot be answered from the static corpus.
- Any hard validation failure produces an abstention, not a best guess.

## 5. Target package structure

```text
src/firelens/
  config.py
  providers/
    openrouter.py
  retrieval/
    bm25.py                 existing
    embeddings.py
    vector.py
    hybrid.py
    rerank.py
    pipeline.py
    evaluate.py             extend existing evaluator
  answering/
    schemas.py
    intent.py
    context.py
    generate.py
    validate.py
    service.py
  api.py
```

The provider boundary stays intentionally small. `OpenRouterClient` owns HTTP,
timeouts, retries, error normalization, and usage metadata. Domain modules own
FireLens decisions. No LangChain, managed vector database, agent framework, or
general plugin system is required.

## 6. Core contracts

### 6.1 Embedding record

```json
{
  "schema_version": "embedding_record.v1",
  "chunk_id": "preparedbc_wildfire_guide:page:11:chunk:1",
  "chunk_content_sha256": "hash of the exact embedded text",
  "corpus_version": "firelens_static_corpus.v1",
  "model": "openai/text-embedding-3-small",
  "dimensions": 1536,
  "vector": [],
  "created_at": "UTC timestamp"
}
```

The exact chunk text is sent to OpenRouter. Citation metadata remains local and
is joined by `chunk_id`; it is not embedded into an opaque database. A content
hash lets unchanged chunks reuse cached vectors.

### 6.2 Retrieval candidate

```json
{
  "chunk_id": "stable identifier",
  "source_id": "approved source",
  "locator": "page:11 or section:...",
  "bm25_rank": 2,
  "vector_rank": 1,
  "rrf_score": 0.0325,
  "rerank_score": 0.91,
  "text": "exact evidence text"
}
```

All ranking stages operate on the same stable chunk IDs. No stage is allowed to
drop publisher, URL, document hash, page, section, or temporal class.

### 6.3 Evidence packet

Each final passage receives a request-local evidence ID such as `E1`. The packet
contains the exact text plus canonical provenance. It also declares that the
material is stable guidance and cannot establish current conditions.

### 6.4 Generated answer

```json
{
  "answer_type": "guidance",
  "answer": "A concise evidence-bounded explanation.",
  "claims": [
    {
      "claim": "One independently checkable statement.",
      "evidence_ids": ["E1"],
      "evidence_quotes": ["Exact supporting substring"],
      "support_level": "direct"
    }
  ],
  "limitations": [],
  "requires_live_verification": false
}
```

The backend, not Gemini, reconstructs the public `sources` collection from the
accepted evidence IDs.

## 7. Implementation phases and gates

### Gate 0 — Reproducible environment and secret safety

Build:

- add a small `pyproject.toml` with a documented reference Python version;
- pin the ingestion dependencies needed by the existing code;
- add the one HTTP client used for OpenRouter;
- add `.env.example` containing only the variable name;
- load `OPENROUTER_API_KEY` at runtime without logging it;
- create a local `.venv` and document exact setup commands.

Pass when:

- the existing test suite is reproduced at `27/27` or any changed result is
  explained and fixed;
- a clean environment can build the corpus and BM25 report;
- secret scanning finds no API key outside ignored local environment files.

### Gate 1 — Offline embedding infrastructure

Build without spending API credit:

- embedding and index schemas;
- content hashing and cache lookup;
- stable chunk-to-vector mapping;
- batch preparation and response validation;
- JSONL vector persistence plus an index manifest;
- pure local cosine search;
- deterministic fake-embedding tests;
- corrupt, incomplete, wrong-dimension, and wrong-model failure tests.

Pass when:

- fake vectors round-trip without losing chunk identity;
- unchanged chunks are cache hits;
- changed content invalidates only the affected vectors;
- duplicate IDs, NaN values, wrong dimensions, and manifest mismatch fail
  closed.

### Gate 2 — Real OpenRouter embeddings

Build:

- batch all 175 chunk texts through `openai/text-embedding-3-small`;
- persist the returned vectors and API usage metadata;
- embed each query independently;
- add vector-only search and evaluation;
- keep the complete BM25 baseline unchanged.

Compare:

- Hit@1, Hit@3, and Hit@5;
- MRR@5;
- source coverage@5;
- per-question failures;
- citation-metadata integrity;
- index-build and query latency;
- reported token use and estimated cost.

Pass when citation integrity is `100%` and vector retrieval produces a valid,
repeatable report. Vector search does not need to beat BM25 by itself.

### Gate 3 — Hybrid retrieval with RRF

Build:

- retrieve the top 20 BM25 candidates;
- retrieve the top 20 vector candidates;
- fuse ranks by Reciprocal Rank Fusion with a recorded `k=60` baseline;
- deduplicate by `chunk_id`;
- preserve the component ranks and fused score;
- evaluate the top 1, 3, and 5 results.

RRF is preferred because BM25 and cosine scores are not calibrated to the same
scale. Rank fusion combines their ordering without pretending the raw scores
have comparable meaning.

Pass when:

- hybrid Hit@5 is no worse than the recorded BM25 `15/17`;
- every existing safety-critical BM25 hit remains in the hybrid top five;
- at least one lexical failure is recovered or the experiment records that no
  measured gain occurred;
- provenance remains complete for every result.

The stretch target is `17/17` Hit@5 and improved multi-source coverage, but it
must be measured rather than promised.

### Gate 4 — Cohere Rerank 4 Pro

Build:

- send the query and top 20 hybrid candidate texts to
  `cohere/rerank-4-pro`;
- map response indices back to immutable candidate records;
- return the best five passages;
- record model, latency, request count, cost, and any retry;
- cache by query hash, candidate-set hash, and model ID;
- add fake-client unit tests and live integration tests marked separately.

Pass when:

- reranked Hit@5 and source coverage do not regress from hybrid;
- `GQ005` and `GQ019` are explicitly inspected;
- all returned indices are valid and unique;
- unsafe sprinkler, gas, smoke-health, alert, and order questions retain the
  correct evidence;
- a failed reranker degrades to hybrid retrieval rather than losing the answer.

Rerank 4 Fast is a later latency challenger. Pro is the first quality baseline
because this corpus and evaluation set are small.

### Gate 5 — Freshness, intent, and answerability routing

Build:

- normalize conversational follow-ups into standalone questions;
- classify requests as `stable_guidance`, `live_status`, `mixed`, or
  `prohibited`;
- place deterministic safety rules after model classification;
- route `stable_guidance` to RAG;
- abstain on `live_status` and the live portion of `mixed` questions until
  authoritative live tools exist;
- block personalized medical, evacuation-route, spread-prediction, and
  property-safety judgments.

Pass when:

- `GQ016`, `GQ017`, and `GQ018` always abstain;
- location wording cannot turn cached guidance into a current-status answer;
- no prompt can make the router treat static documents as live evidence;
- alert and order remain distinct concepts.

### Gate 6 — Grounded Gemini generation

Build:

- use `google/gemini-3.5-flash-lite` with low reasoning;
- provide only the user question, bounded instructions, and top evidence
  packet;
- enforce the answer JSON schema through structured outputs;
- require evidence IDs and exact evidence substrings per factual claim;
- cap answer length and evidence count;
- omit model-memory claims and unsupplied URLs;
- implement timeout, rate-limit, malformed-response, and provider-error paths.

Pass when every answer parses and every factual claim names supplied evidence.
Gemini 3.6 Flash may be evaluated later on the same cases, but it is not an
automatic fallback merely because an answer is difficult. Hard validation
failure still causes abstention.

### Gate 7 — Deterministic answer verification

Build:

- schema validation;
- evidence-ID membership checks;
- exact-quote containment checks;
- one or more citations for every factual claim;
- temporal-class checks;
- forbidden-claim and prohibited-language checks;
- explicit limitation checks for live or mixed intent;
- reconstruction of source cards from canonical chunk metadata;
- an append-only request trace with no secrets.

Runtime decision:

```text
valid supported answer -> return guidance
no sufficient evidence -> abstain
malformed or unsupported draft -> abstain
provider unavailable -> bounded service error or abstention
live-status request -> live-verification abstention
```

Pass when the model cannot create a source, page, section, evidence quote, or
support level that was not present in its approved context.

### Gate 8 — End-to-end service

Build the simple interface only after the earlier gates pass:

```text
POST /rag/answer
```

Request:

```json
{
  "message": "What should go in my wildfire grab-and-go bag?",
  "history": []
}
```

Response:

```json
{
  "answer_type": "guidance",
  "answer": "...",
  "claims": [],
  "sources": [],
  "limitations": [],
  "requires_live_verification": false,
  "trace_id": "opaque identifier"
}
```

Conversation history is client-supplied, bounded, and normalized. R2 does not
add a database or unlimited server-side memory. Streaming is optional display
behavior; the completed structured response remains the auditable result.

Pass when CLI and HTTP paths invoke the same service and produce the same
validated result contract.

### Gate 9 — Full RAG evaluation

Run all 20 gold questions and report:

Retrieval:

- BM25, vector, hybrid, and reranked Hit@1/3/5;
- MRR@5 and source coverage@5;
- per-question rank movement and failure notes;
- provenance integrity and latency.

Answers:

- required-claim coverage;
- citation precision and completeness;
- unsupported-claim rate;
- forbidden-claim rate;
- abstention accuracy;
- adversarial-premise correction;
- alert-versus-order accuracy;
- latency, tokens, and cost per answer.

Release gates:

- citation precision: `100%` on the reviewed gold set;
- citation completeness: `100%` on the reviewed gold set;
- unsupported factual claims: `0`;
- forbidden claims: `0`;
- live/predictive abstentions: `3/3`;
- adversarial corrections: `2/2`;
- every response preserves its source locator and URL;
- no result is described as current wildfire status.

Required-claim coverage, latency, and cost targets are calibrated after the
first live run. They are not invented in advance and cannot override the zero-
unsupported-claim safety gates.

## 8. Evaluation expansion before public use

The existing 20-question set is the first development benchmark, not sufficient
public-safety qualification. Before a public beta, add locked tests for:

- paraphrases of every safety-critical question;
- typos, short queries, and conversational follow-ups;
- conflicting or incomplete evidence;
- prompt injection inside user messages and retrieved text;
- invented authority names and fake citations;
- current-status requests with and without a location;
- confusing alert, order, stage-of-control, and wildfire-rank terminology;
- requests for individualized smoke-health advice;
- provider timeout, stale index, corrupt cache, and corpus-version mismatch.

Development tuning and final holdout questions must be separated so the team
does not optimize directly against every release test.

## 9. Product experience direction

The first interface has one primary job:

> Ask a wildfire-preparedness question and understand both the supported
> guidance and where it came from.

The first screen should therefore emphasize:

- one prominent question field;
- a persistent statement that FireLens provides preparedness guidance, not
  current incident or evacuation status;
- calm answer typography rather than an emergency-command aesthetic;
- inline source markers connected to exact page or section evidence;
- an evidence drawer showing publisher, title, locator, passage, and link;
- a distinct abstention state directing the user to the correct official
  authority;
- no fake live map, fire perimeter, current alert, risk score, or safety badge.

Product Design will explore three desktop directions before any frontend is
built. The selected visual becomes the target for a later faithful prototype.

## 10. Delivery sequence

```text
Gate 0  reproducible environment
Gate 1  offline embedding infrastructure
Gate 2  real OpenRouter vector index
Gate 3  BM25 + vector RRF
Gate 4  Cohere Rerank 4 Pro
Gate 5  freshness and answerability routing
Gate 6  grounded Gemini generation
Gate 7  deterministic answer verification
Gate 8  CLI and /rag/answer service
Gate 9  locked evaluation and R2 decision
```

Each gate ends with code, tests, an evaluation artifact where applicable, and a
short learning review covering inputs, outputs, important functions, failure
modes, and measured results. A later phase adds live authoritative tools; only
after that gate passes can FireLens claim the complete customer MVP described in
the R0 product contract.
