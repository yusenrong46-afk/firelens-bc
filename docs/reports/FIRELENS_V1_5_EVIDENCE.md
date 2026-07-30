# FireLens BC V1.5 lab evidence ledger

> Historical pre-hardening snapshot. For the current candidate, gate counts, artifact hashes,
> and release decision, use `V1_5_PRINCIPAL_REMEDIATION.md` and
> `V1_5_EXECUTION_STATE.md`. Values below are retained as commit-bound history and must not be
> read as the current release state or current 170-chunk corpus identity.

Date: 2026-07-29 (America/Vancouver)

Baseline: `209b4e5f8f16f13d7ac9af56a89e135f697ce052`

Historical experimental phase: V1.5 lab

Historical hardening phase: based on `ba42b74`

Dedicated release reconstruction: not completed

## Release decision

**Do not promote this candidate yet.** V1.5 is implemented and its RAG, official-live mode, map,
security boundaries, and browser experience have substantial executed evidence. However, the
previous independently frozen retrieval holdout scored 81.25-87.5% Recall@5 across three
repetitions, below the required 96%. A new 47-case candidate has been frozen after configuration
selection with zero exact overlap against the preserved benchmark, but its relevance labels and
the owner semantic-review gate are still open. It has not been used for tuning or paid scoring.

The earlier 100% result on 47 route-eligible development cases used a non-owner-reviewed relevance
addendum. It remains useful development evidence but is not sealed promotion evidence. No
benchmark question or retrieved answer from the frozen holdout was used for tuning.

Nothing was merged, pushed, deployed, or cherry-picked into the release branch.

Later regression evidence records `105/105` hard-probe cases and `33/33`
generalization cases at `a093bf0`, with `18/18` desktop/mobile browser flows at
`ba42b74`. These results remain development evidence and do not substitute for
the sealed owner-review gates.

## Baseline versus candidate

| Measure | V1/V1.1 reference | Final V1.5 lab evidence | Decision |
|---|---:|---:|---|
| 165-case limitation probe | historical 145/165 (87.9%) | **162/165 (98.18%)** | pass, target >=95% |
| Novel-document grounding | historical 5/10 | **9/10** | pass, target >=9/10 |
| Corpus-gap grounded overclaims | historical 3/10 | **0/10** | pass, target zero |
| Personal-safety / medical | historical 7/10 / 7/10 | **10/10 / 10/10** | pass |
| Poison / citation bait / conflict | not comparable | **10/10 / 5/5 / 3/3** | pass |
| Leave-one-source-out | historical 15/15 | **15/15** | pass |
| Paid conversation response mode/status | earlier calibration 92% | **98%** | one conservative holdout miss |
| Route / deterministic safety route | 100% / 100% | **100% / 100%** | pass |
| Paid conversation static p95 | earlier calibration 3.62 s | **3.790 s** | pass, target <=4 s |
| Preserved independent Recall@5 | unavailable | **81.25%, 87.5%, 87.5%** | historical fail |
| New 47-case sealed Recall@5 | unavailable | **not run; 0/47 owner-approved** | pending |
| Frozen independent MRR@5 | unavailable | **0.6458, 0.7292, 0.6979** | not promotable |
| Cached official-live p95 | unmeasured | **0.339 s** | refreshed pass, target <=4 s |

The final limitation probe's overall p95 was 3.646 seconds. Its answer-producing subset was
4.353 seconds, a performance warning even though the locked conversation benchmark and overall
static-query gate passed.

## RAG implementation and trust boundary

- A deterministic BM25 preflight supplies bounded, explicitly untrusted title, section,
  identifier, and snippet candidates to the planner. Preflight text can shape retrieval intent but
  can never become answer evidence.
- Deterministic safety/live routing runs before planning and covers personalized safety,
  medical treatment, current status, policy manipulation, and exact-address use.
- Required aspects and authority requirements feed an aspect-to-evidence matrix. Models propose
  quote IDs; deterministic validation owns quote identity, exact text, authority, coverage,
  conflict disclosure, and accepted/partial/unsupported status.
- Exact citations and a lexical claim-to-quote floor are automated. They do not prove semantic
  entailment; the owner review packet remains authoritative for that release gate.
- Corpus admission quarantines prompt-injection sources before indexing or retrieval, rejects
  malformed/pathological sources and duplicate document hashes, and preserves near-duplicate
  warnings for version/conflict review.
- Conflicting prescriptive sources produce a typed `conflict` response with both original sources;
  summaries or graph outputs never become citation authority.

## Contextual retrieval and GraphRAG

`document_context_v2` generated hash-keyed 50-100-token sidecars for all 180 chunks and indexed
the context for retrieval only. Original chunks remained the sole citation authority. Its
controlled comparison did not gain the required +2 Recall@5 points or +3 MRR points, so
`metadata_context_v1` remains the candidate.

The GraphRAG exporter produced 180 raw-chunk records, an OpenRouter-compatible configuration, and
`raw_chunk_ids_only` citation authority. The GraphRAG CLI was absent. The experiment therefore
stopped as `excluded_dependency_missing`; no fragile proxy, graph index claim, direct-vendor call,
or graph-derived production path was introduced.

## Official live data and map

One `LiveDataService` powers chat and map for the official incident, perimeter, and wildfire
evacuation layers. It validates exact layer identities and required fields, paginates GeoJSON in
WGS84, uses pinned Shapely plus pyproj WGS84 geodesics, filters inactive/non-wildfire records, and
shows authority, source URL, source update time, retrieval time, status, freshness, and geometry.

The refreshed real-source qualification at commit
`eca9119511d79e089526a6d163b8481c9c4a2205` found:

| Live check | Result |
|---|---:|
| Displayable official records | 253 |
| Unavailable layers | 0 |
| Missing required metadata | 0 |
| Cold three-layer fetch | 5.797 s |
| Cached p95, 26 API requests | 0.339 s |
| Concurrency 1 p95 | 0.012 s |
| Concurrency 5 p95 | 0.086 s |
| Concurrency 20 p95 | 0.350 s |
| Chat/map identifier and status agreement | pass |

Fresh cache lasts five minutes. Refresh failure may expose visibly stale data only through 15
minutes; after that the layer fails closed. Polygon holes, multipolygons, boundaries, malformed
geometry, pagination, partial layer failure, invalid bbox/layer input, source identity, source
timestamp, stale expiry, and total outage are covered by deterministic tests. No-result wording
explicitly says it is not a safety determination.

The interface remains conversation-first with one evidence/map panel, lazy-loaded Leaflet, one
attributed OpenStreetMap basemap, official GeoJSON overlays, and a link to the official BCWS map.
Rendered checks covered desktop, 390x844 mobile, live, mixed, grounded static, exact evidence,
keyboard submission, timestamps, failure/retry states, and map-after-answer order. No console
errors or framework overlays were observed.

## Executed qualification

The current `make verify` run passed:

- 152 Python tests, 10 skipped, and 36 subtests;
- Ruff, formatting, mypy over 51 source files, and secret scan;
- generated OpenAPI and TypeScript types with no residual diff;
- 12 frontend unit tests and the production TypeScript/Vite build;
- 4 Sites packaging tests;
- 12 Playwright scenarios across desktop and mobile.

The provenance-complete 165-case run was bound to:

- commit `727110ec3c9626601fb4c04375eba4a1be572703`;
- corpus chunks SHA-256 `a6a26b22c45b1a17e286f38fb2af45b5d4baaf70f6c4c729243668b1355caa2f`;
- corpus manifest SHA-256 `ddeabeedc13778c1247d57be2c1e97d6e1cb311e672fa8e21d5f401e7f2821b3`;
- vector manifest SHA-256 `3024914bb9a263e5e2a3c8c5204e9bd8a63e073b5a7a41d02e52bbee585dbfc0`;
- naive/jailbreak/generalization input hashes embedded in the report;
- planner, grounded-generation, and background-generation prompt hashes embedded in the report;
- `metadata_context_v1`, 30/30/30 candidate pools, RRF 60, rerank 5;
- OpenRouter models `openai/text-embedding-3-small`, `cohere/rerank-4-pro`, and
  `google/gemini-3.5-flash-lite`.

The run used 286,681 tokens, cost `$0.31654526`, completed all 165 cases, and did not hit its
`$1.25` ceiling. Its three conservative misses were one ordinary preparedness abstention, one
follow-up abstention, and one novel-document background answer.

## Artifact hashes

Generated evaluation outputs remain ignored rather than committed:

| Artifact | SHA-256 |
|---|---|
| `v1_1_conversation_live_report.json` | `f2360bca6747d08a7863f9a47029aaef900a723a2734db2553bff6ec2397b62e` |
| `v1_1_conversation_live_review.md` | `500cec1aa0ee923b5fcff012b489830e0c303074d8366d5f58b45f7d5386d676` |
| `naive_user_probe/results.json` | `b6fad0e360c8f5c83700fe266ce51dd5e7d410132799cbe7b1883fd78e1b1980` |
| `qualification/v1_5_live.json` | `b2811588c4fb2e67ddda34d56fbf57ce6fd12f9c752463e414a8b6aa9b443294` |
| `v1_5_retrieval_owner_review.yaml` | `9cbfaa3c77a7f999fd23a3f23698d939b54a6231e007f08226334a07c1659a8f` |
| `v1_5_retrieval_owner_review.md` | `5115a3e8880c97fcf0bded1feaa2ff1e04e15a22bcc4673200f27f89c105b056` |
| `v1_5_owner_semantic_review.yaml` | `bf78f0a18f4eeb0f20d922e1d4ebf10ecef6724338c90189631f197d27705915` |
| `v1_5_retrieval_comparison.json` | `342b7f4a07103f79e9d6274579476ede1b0c5ebc065dd73d4a8520e9c2133c0e` |

The preserved failed retrieval report uses dataset SHA-256
`c0e8499ff0ce74b1706e5c4b54b8382dae271479329e7f743a802882503e932c` and holdout SHA-256
`ab1a5105c80b907aa0765496105f3178f50d0fb8dbaecf1d9932e790a43834ae`.

The new unscored sealed candidate uses dataset SHA-256
`33b8811f8a984e53be3d19c1874cd89df317943df9309dc048539d5f2876b6e4` and holdout SHA-256
`9dbdf45ce6f94e1c6d46893b6d50fe642f75a245e0a6309892eee03e6337443a`.

Those snapshot hashes include the 2026-07-30 metadata-only review-label migration. The later
remediation quarantined an unapproved repaired page and changed the production corpus/index
hashes, so all pending ignored review sidecars must be regenerated against the remediated tree.

## Cost ledger

This final sustained qualification recorded:

| Run | Cost |
|---|---:|
| Focused poison/conflict calibration | $0.02845812 |
| Frozen holdout, three repetitions | $0.14774012 |
| First complete 165-case run | $0.31334714 |
| Paid 50-case conversation run | $0.08253570 |
| Rendered mixed/static generation traces | $0.00971946 |
| Final provenance-complete 165-case run | $0.31654526 |
| **Total** | **$0.89834580** |

Every runtime/evaluation call used OpenRouter. The contextual-retrieval and development retrieval
experiments have their own earlier recorded costs; context-generation cost was historically not
aggregated, so this table is intentionally limited to the final qualification sequence.

## Unmet release gates

1. The new 47-case sealed set is frozen and structurally valid but remains 0/47 owner-approved;
   its paid Recall@5 gate has intentionally not run.
2. The preserved 16-case independent result remains below 96% and cannot authorize promotion.
3. Semantic correctness and unsupported-material-claim count remain unscored; the hash-bound
   50-case owner review remains 0/50 approved.
4. The OpenRouter limit is restored and the fixed-planner reranker comparison is complete; no
   candidate earned promotion. Paid sealed scoring remains blocked only by owner label review.
5. An anonymous Vercel preview, distributed rate limiting, and production rollback drill require
   external deployment approval and were not performed.

## Continued retrieval optimization

A final development-only query-policy experiment reused one set of planner decisions across four
treatments, avoiding planner variance between candidates. All 200 rows completed with zero
provider errors and recorded exact model IDs, attempts, 55,568 tokens, provider-stage timings,
wall latency, and `$0.49713884` provider-reported cost. The artifact SHA-256 is
`342b7f4a07103f79e9d6274579476ede1b0c5ebc065dd73d4a8520e9c2133c0e`.

On the 47 route-eligible development cases, current retrieval scored 100% Recall@5, 85.46% MRR@5,
and 91.84% mean source coverage. Original-question reranking scored 97.87% / 78.72% / 92.20%;
original-question retrieval scored 97.87% / 84.75% / 89.72%; and the combined treatment scored
97.87% / 78.19% / 91.13%. All three alternatives lost one recall case and failed the locked gain
rule, so current `metadata_context_v1`, 30/30/30, RRF 60, rerank 5 remains unchanged.

One earlier complete rerun consumed `$0.48585084` before row-level provenance instrumentation was
added; it was superseded rather than used as release evidence. Across those two complete reruns,
reports summed to `$0.98298968`; the OpenRouter key-status usage increased by `$0.88840588`. The
ledger keeps both values because provider-reported per-call cost and account status are distinct
observations. The final key status was limit `$20`, usage `$10.90011477`, remaining `$9.09988523`.

A separate zero-provider-call lexical sweep evaluated compound-identifier tokens and bounded
title, section, and locator weighting across 50 development cases. Field weighting changed BM25
MRR@5 from 70.33% to 71.00% with Recall@5 unchanged at 88%; identifier tokens were neutral on the
measured cases. Neither cleared the locked two-point Recall or three-point MRR rule. Production
retrieval remains `metadata_context_v1`, 30/30/30 candidate pools, RRF 60, rerank 5. The ignored
lexical artifact SHA-256 is
`237551e0569b70e78eb9f17608f3e70b970323a471f51cd91bf8e6c0b295f778`.

The post-experiment `make verify` run passed 152 Python tests, 10 skips, 36 subtests,
Ruff, formatting, mypy, secret scanning, generated OpenAPI/TypeScript contracts, 12 frontend unit
tests, the production build, 4 Sites tests, and 12 desktop/mobile Playwright flows. Generated-code
checks left no unintended tracked diff.

These are release blockers, so dedicated release reconstruction remains incomplete.

## Exact final commands

```bash
make verify
make retrieval-review-packet
make retrieval-review-template
make qualify-retrieval-review
make qualify-retrieval-v1-5
.venv/bin/python scripts/run_limitation_probe.py --max-cost-usd 1.25
make benchmark-v1-1-paid
make owner-review-template
make qualify-owner-review
make qualify-live-v1-5
make run
```

Paid commands sourced the ignored canonical `.env`; no secret was copied, printed, or committed.
Only passing lab commits exist. Release reconstruction starts only after owner review and a valid
sealed retrieval qualification pass.
