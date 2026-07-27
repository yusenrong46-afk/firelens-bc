# FireLens BC V1.1 RC

FireLens BC is a local, evidence-first conversational assistant for reviewed
British Columbia wildfire-preparedness guidance. V1.1 can introduce its
collection, answer document-grounded questions with exact local citations,
provide clearly labelled low-risk background, resolve bounded follow-ups, and
redirect genuinely unrelated requests. It still refuses current-incident,
prediction, personalized evacuation, and personalized medical decisions.

**Release status:** `engineering-complete, semantic acceptance pending`.
The system is not release-qualified until owner semantic review is complete and
the remaining legacy V1 retrieval gate is resolved.

```mermaid
flowchart LR
    Q["Question plus at most 6 prior turns"] --> B["Deterministic safety boundary"]
    B -->|"live or prohibited"| A["Typed abstention"]
    B -->|"capability"| C["Local scope answer"]
    B -->|"ordinary"| P["Bounded planner"]
    P -->|"tangent"| T["Scope redirect"]
    P -->|"adjacent"| G["Labelled general background"]
    P -->|"grounded candidate"| H["BM25 plus dense plus RRF"]
    H --> R["Cohere Rerank 4 Pro"]
    R --> E["Local evidence packet"]
    E --> D["Gemini structured draft"]
    D --> V["Deterministic validator"]
    V -->|"accepted"| O["Claims plus exact local support"]
    V -->|"rejected"| A
```

Local Python code owns policy, routing, retrieval, source metadata, evidence
construction, validation, and public responses. OpenRouter supplies bounded
planning, embeddings, reranking, and generation. There is no hidden model
substitution, retrieval fallback, answer repair, or model-memory fallback.

## Quick start

Python 3.11–3.14 and Node/npm are supported. Dependencies are locked in
`requirements.lock` and `package-lock.json`.

```bash
make setup
cp .env.example .env
# Put a rotated OPENROUTER_API_KEY in the ignored .env file.
make verify
make run
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). `make run` builds the
React frontend, then serves the frontend and `/api/v1` from one FastAPI origin.

If the corpus or index is absent:

```bash
.venv/bin/firelens bootstrap-corpus
.venv/bin/firelens build-index
.venv/bin/firelens doctor
```

Source changes fail hash verification and require explicit review. Never edit a
manifest merely to force readiness.

## Response modes

| Mode | When it is used | Evidence behavior |
|---|---|---|
| `capability` | Greetings and “what can I ask?” | Deterministic local answer; no paid call |
| `grounded` | Directly supported stable guidance | Every claim has an exact quote and local source record |
| `background` | Related low-risk explanation outside direct corpus support | Clearly labelled; no corpus citation is allowed |
| `scope_redirect` | Completely tangent request | Redirects to FireLens topics |
| `abstention` | Live, predictive, personalized, unsafe, or unvalidated request | No factual evidence claim is returned |

The background mode is intentionally separated from grounded RAG: it improves
conversation breadth without making unverified material look document-backed.

## Commands

```bash
make verify                 # secrets, OpenAPI, lint, types, tests, builds, browsers
make benchmark              # zero-cost V1 red-team plus V1.1 offline suite
make benchmark-v1-1-paid    # cost-capped 50-case live conversation benchmark
make benchmark-contextual   # development-only A/B/C retrieval-text experiment
make benchmark-retrieval    # four locked V1 retrieval configurations
make canary                 # 30 repeated live calls
make model-bakeoff          # identical-evidence Gemini comparison
make live-smoke             # opt-in OpenRouter endpoint smoke tests
```

CLI equivalents:

```bash
.venv/bin/firelens search "What belongs in a grab-and-go bag?"
.venv/bin/firelens ask "What does an evacuation alert mean?"
.venv/bin/firelens corpus-audit
```

## API

`POST /api/v1/ask` accepts a question and up to six bounded prior turns:

```json
{
  "question": "Why does that matter?",
  "history": [
    {"role": "user", "content": "What belongs in a grab-and-go bag?"},
    {"role": "assistant", "content": "The reviewed guide lists household supplies."}
  ]
}
```

Other routes:

- `GET /api/v1/health/live`: process liveness.
- `GET /api/v1/health/ready`: corpus, index, and provider readiness.
- `POST /api/v1/search` and `GET /api/v1/debug/chunks/{chunk_id}`: development
  only when `FIRELENS_DEBUG=true`.

Strict contracts reject unknown fields. Public source metadata is always
reconstructed from local corpus records; the model cannot supply publishers,
URLs, locators, hashes, or page numbers.

## Current measured checkpoint

| Area | Result |
|---|---:|
| Governed corpus | 8 sources, 180 chunks |
| Main vector index | 180 × 1,536, `metadata_context_v1` |
| Final verification | 99 Python passed, 3 paid skipped, 22 Python subtests; frontend 11 unit, 4 Sites, 12 browser flows |
| V1.1 offline suite | 50/50 complete; all control metrics 100% |
| Context A/B/C winner | 100% Recall@5, 81.25% MRR@5 on 8 grounded dev cases |
| Locked V1 retrieval sweep | 96% Recall@5, 86.17% MRR@5; current 20/20/60/5 retained |
| 30-call canary | no status/reason variance; p95 2.565 s |
| Final V1.1 live run | 50/50 complete; all control metrics and Recall@5 100%; p95 2.572 s |
| Legacy V1 compatibility run | 92.42% Recall@5; below the 95% release gate |

One immediately preceding V1.1 repeat hit a transient 429 on one of 50 cases
after all three bounded attempts. The final retained rerun is clean. The pair is
evidence of provider variability, while the final artifact remains the
authoritative scored result.

Automated checks establish routing, structural traceability, exact quote
identity, and policy invariants. They do **not** establish semantic entailment or
claim completeness. The exact owner-review action and artifact hashes are in
[`docs/releases/V1_EVIDENCE.md`](docs/releases/V1_EVIDENCE.md).

Further reading:

- [`docs/TECHNICAL_HANDBOOK.md`](docs/TECHNICAL_HANDBOOK.md): authoritative
  architecture, contracts, operations, and code-reading guide.
- [`docs/reports/FIRELENS_V1_1_TECHNICAL_REPORT.md`](docs/reports/FIRELENS_V1_1_TECHNICAL_REPORT.md):
  detailed layer-by-layer report and result visualizations.
- [`docs/adr/`](docs/adr/): immutable architecture decisions.
- [`docs/learning/`](docs/learning/): textbook-style subsystem explanations.
