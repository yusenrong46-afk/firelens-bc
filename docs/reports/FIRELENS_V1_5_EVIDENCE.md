# FireLens BC V1.5 lab evidence ledger

Date: 2026-07-28 (America/Vancouver)

Baseline: `209b4e5f8f16f13d7ac9af56a89e135f697ce052`

Lab branch: `codex/v1-5-lab`

Release branch: `codex/v1-5-release` remains at the baseline

## Decision

**Lab qualification is strong, but promotion is blocked.** The candidate clears the answer-quality,
safety, citation-structure, latency, official-source, and browser gates that were executed. It does
not clear the locked expanded retrieval gate: final route-eligible reranked Recall@5 was **45/47 =
95.74%**, below the required 96%. Paid-cost capture was also absent from the completed 165-case run
and from the document-context generation/index step. No commits were cherry-picked to the release
branch, and nothing was merged, deployed, or pushed.

This is a prove-before-promote result, not a failed implementation. The lab contains a complete
candidate and honest negative experiments; production remains on V1.1.

## Baseline versus candidate

| Measure | V1/V1.1 baseline | V1.5 lab | Gate |
|---|---:|---:|---|
| 165-case limitation probe | 145/165 (87.9%) | **163/165 (98.8%)** | pass, target at least 95% |
| Novel-document grounding | 5/10 | **10/10** | pass, target at least 9/10 |
| Corpus-gap grounded overclaims | 3/10 cases | **0/10** | pass, target zero |
| Personal-safety bucket | 7/10 | **10/10** | pass |
| Medical-personal bucket | 7/10 | **10/10** | pass |
| Poison-source protection | 10/10 | **10/10** | pass |
| Citation-bait protection | 5/5 | **5/5** | pass |
| Leave-one-source-out | 15/15 | **15/15** | pass |
| Locked 50-case response-mode accuracy | earlier V1.5 calibration 92% | **96%** | pass |
| Locked 50-case route / safety-route accuracy | 100% / 100% | **100% / 100%** | pass |
| Locked 50-case provider failure rate | 0% | **0%** | pass |
| Static p95 | earlier V1.5 calibration 3.62 s | **2.96 s** | pass, target at most 4 s |
| Expanded route-eligible reranked Recall@5 | not previously separated from intentional no-retrieval routes | **95.74%** | **fail**, target at least 96% |
| Expanded route-eligible reranked MRR | not comparable | **0.8032** | recorded; no promoted candidate |

The two final probe misses were conservative abstentions (`NU-PLAIN-03` and `NU-JARGON-03`), not
unsupported grounded claims. Automated semantic entailment was not scored; the generated review
packet still requires owner review.

## What is implemented and verified

- Corpus-aware BM25 preflight supplies bounded, explicitly untrusted snippets and exact identifiers
  to retrieval planning. Exact identifiers in the current corpus cannot be dismissed as tangent.
- Deterministic safety/live routing runs before planning and covers natural personal-safety,
  medical, current-status, exact-address, and policy-manipulation paraphrases.
- Required aspects, authority requirements, per-passage lexical support, administrative-policy
  checks, and exact quote validation decide whether an answer is supported, partial, or unsupported.
- Generated limitations can no longer decide application evidence status; the application owns the
  visible evidence limitations.
- `document_context_v2` supports hash-keyed offline sidecars and retrieval-only contextual text;
  original raw chunks remain the only citation authority.
- One typed `LiveDataService` powers chat and map with ArcGIS pagination, WGS84 GeoJSON, five-minute
  fresh cache, 15-minute stale ceiling, fail-closed schemas, Shapely geometry, and shared record IDs.
- Live records require a source timestamp. Records marked out/inactive/rescinded and non-wildfire
  evacuation events are filtered before display.
- Coarse opt-in location is rounded to two decimals, is not persisted by the UI, and exact-address
  input is rejected.
- The restrained UI keeps conversation primary and lazy-loads the Leaflet map into its own bundle.
  It removes internal trace/evidence jargon and avoids a dashboard or UI-component proliferation.

## Live and interface evidence

The official-source smoke queried all three configured ArcGIS layers over the BC bounding box after
the schema correction:

| Layer | Displayable records |
|---|---:|
| Incident | 132 |
| Perimeter | 56 |
| Wildfire evacuation alert/order | 62 |

The smoke returned **250 total records, zero unavailable layers, and zero missing source
timestamps**. Counts are a time-of-test observation, not a product promise.

`make verify` passed from the lab checkout:

- secret scan and generated OpenAPI/type checks;
- Ruff check and formatting, plus mypy over 46 source files;
- 112 Python tests, 10 skipped, and 36 subtests;
- 12 frontend unit tests and production TypeScript/Vite build;
- 4 Sites packaging tests;
- 12 Playwright flows across desktop and mobile, including grounded evidence, background mode,
  conversation reset, tangent handling, live map keyboard flow, and transient failure retry.

The production build kept the map lazy-loaded (`LiveMap` JavaScript 156.84 kB, gzip 46.03 kB)
instead of adding it to the primary conversation bundle.

## Experiments not promoted

### Expanded retrieval configurations

The report now separates legacy all-case metrics from the 47 questions that actually invoke static
retrieval. Three legacy questions correctly make no retrieval call in V1.5 because deterministic
safety/live routing owns them. None of the four final retrieval configurations cleared the absolute
96% route-eligible Recall@5 plus two-point gain, source-coverage, and MRR rules. The current
configuration remains unchanged.

### Contextual retrieval

The existing deterministic metadata-context comparison reached 8/8 Recall@5, but its safety gate
failed because one saved planner relation did not match its development label. It was not newly
promoted.

For `document_context_v2`, 180/180 contextual records and an isolated 1,536-dimensional embedding
index were generated. On the expanded 50-case comparison, every final configuration remained at
45/47 (95.74%) route-eligible Recall@5. V2 did not clear the required gain and remains lab-only.

### GraphRAG

The isolated exporter produced 180 raw-chunk records with `raw_chunk_ids_only` citation authority
and an OpenRouter-compatible settings file. The GraphRAG CLI was not installed, so the experiment
ended as `excluded_dependency_missing`. No compatibility proxy, direct vendor billing, graph index,
or graph-derived product claim was added.

## Unmet release gates

1. Expanded final Recall@5 is 95.74%, below 96%.
2. The completed 165-case probe predates the added per-case token/cost instrumentation, so its paid
   cost cannot be reconstructed reliably after later traces rotated. The runner now records model,
   attempts, tokens, cost, and latency for future executions, but the sealed run was not repeated
   merely to manufacture that field.
3. Document-context generation/index cost was not aggregated by its command, although the two
   retrieval comparisons recorded $0.5769 and $0.5774, the contextual comparison recorded $0.0639,
   and the locked conversation benchmark recorded $0.0799.
4. Automated semantic correctness and unsupported-material-claim review remain unscored. Owner
   review of the 50-case review packet is required.
5. Cached live-query p95 and concurrency at 1/5/20 users were not measured in this release run.

Because these gates are explicit, the release branch was deliberately not populated.

## Exact executed commands

```bash
make verify
make benchmark-v1-1-paid
make benchmark-retrieval
make benchmark-contextual
.venv/bin/python scripts/run_limitation_probe.py
.venv/bin/python scripts/run_graphrag_experiment.py
.venv/bin/firelens generate-document-contexts \
  --output output/experiments/document_context_v2.jsonl
```

The official live smoke and document-context-v2 index/comparison were executed with bounded Python
drivers against the typed services. All paid commands sourced the ignored original `.env`; no key was
copied, printed, or committed.

## Lab commit ledger

```text
0e3355f test: freeze V1.5 baseline and experiment harness
3e89e22 feat: make planning corpus-aware and evidence-bound
6f2c5d0 feat: add document contextual retrieval v2
3db3dc2 feat: add typed official live data adapters
e07b9cf feat: publish V1.5 live response contracts
9a8e0a7 feat: add restrained live map experience
77ed686 feat: expose contextual retrieval v2 experiment
9021416 experiment: evaluate GraphRAG promotion boundary
1d4602f fix: require explicit location for near-me live queries
c4e770c fix: calibrate evidence sufficiency and safety routing
bcb3646 fix: validate official live record freshness
c984231 test: report route-eligible retrieval gates
ab3d429 style: apply repository formatting
```

## Promotion recommendation

Keep `codex/v1-5-lab` for review and resume/demo work, but do not call it a production-qualified
V1.5 release yet. The next bounded step is to improve or replace the final retrieval selection so it
reliably clears 46/47, rerun the paid-cost-instrumented probe, complete semantic review, and measure
cached live p95. Only then should passing commits be cherry-picked into `codex/v1-5-release`.
