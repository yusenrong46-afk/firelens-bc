# FireLens BC V1.1 RC Evidence Ledger

Status: `engineering-complete, semantic acceptance pending`

Release-qualified: **no**

Evidence date: 2026-07-26 (America/Vancouver)

Environment: macOS 26.4.1, Python 3.14.5, Node 25.9.0, npm 11.12.1

Inspected base commit: `df9f69d`; RC changes were present in the working tree

This ledger distinguishes what was executed from what was merely inspected and
what still requires human judgment. Generated reports are local/ignored; their
hashes bind the measurements below to the retained files.

## 1. Release-gate ledger

| Gate | Evidence | Status |
|---|---|---|
| Secret and repository boundary | tracked-file secret scan passed; `.env`, corpus, vectors, traces, reports, builds ignored | pass |
| Reproducible verification | secret scan, OpenAPI, Ruff, format, mypy 43 files, Python/frontend/build/browser suites passed | pass |
| Corpus/index integrity | 8 approved sources, 180 chunks, 180 × 1,536 index, manifest/hash checks | pass |
| Deterministic safety boundary | V1 red-team 20/20; V1.1 safety route 100% | pass |
| V1.1 offline architecture | 50/50 complete; every control metric 100% | pass, fake-provider scope only |
| V1.1 live architecture | 50/50 complete; all control metrics 100%; zero provider failures/leaks | pass for retained run |
| Contextual retrieval decision | candidate C 100% Recall@5; holdout unopened; main index rebuilt explicitly | pass |
| Locked retrieval selection | current 20/20, RRF 60, top-5 retained at 96% Recall@5 | pass for dev selection rule |
| Citation/quote structure | zero automated traceability failures; no background citation leaks | pass |
| Variability canary | 30/30 structurally accepted; no status/reason variance | pass |
| Legacy V1 retrieval gate | 92.42% reranker Recall@5 versus required 95% | **fail** |
| Frontend automation | 11 unit/accessibility, 4 Sites packaging, 12 Playwright flows | pass |
| Manual in-app visual inspection | local server launched, but stale browser handles persisted after recovery | **not executed** |
| Semantic owner review | claim-to-evidence entailment and required concepts | **pending** |

Release label remains `engineering-complete, semantic acceptance pending`.
Passing the clean V1.1 automated run does not waive the independent legacy
retrieval gate, manual visual gap, or semantic owner review.

## 2. Executed verification

| Command/check | Result | Proves | Does not prove |
|---|---:|---|---|
| `make verify` | 99 Python passed, 3 paid smoke skipped, 22 Python subtests; all remaining checks passed | current offline code/contracts/builds are internally consistent | live provider or semantic quality |
| Ruff check and format | clean | selected static/style rules | runtime correctness |
| mypy | 43 source files clean | configured type contract | complete soundness of Python types |
| frontend unit/accessibility | 11/11 | explicit UI modes, history, retry, evidence interactions, automated axe checks | visual judgment in a real manual session |
| frontend production build | pass | TypeScript/Vite buildability | deployed behavior |
| Sites packaging | 4/4 | packaging contract | Sites deployment |
| Playwright | 12/12 | six primary flows at desktop and mobile viewports | manual visual quality or public hosting |
| `make benchmark` | V1 red-team 20/20; V1.1 offline 50/50 | deterministic safety and fake-provider pipeline wiring | live ranker/generator quality |
| `make benchmark-v1-1-paid` | 50/50 clean final run | complete real-provider V1.1 path and recorded automated metrics | semantic entailment |
| `make benchmark-contextual` | 8 cases × 3 candidates, complete | isolated development A/B/C retrieval comparison | broad generalization |
| `make benchmark-retrieval` | 50 answerable dev cases × 4 configs | locked V1 configuration comparison | holdout performance or label correctness |
| legacy `make benchmark-live` | 100/100 complete | V1 compatibility, safety, citations, retrieval | V1.1 mode-label agreement |
| `make canary` | 30/30 complete | repeated status/reason and structural stability | truth or completeness |
| local `make run` | server launched | process can serve local frontend/API | manual in-app visual acceptance |

The in-app browser could not complete a fresh inspection because its handles
remained bound to a stale session after the documented recovery attempt. This
ledger relies on Playwright for browser interaction evidence and explicitly does
not claim a manual visual pass.

## 3. V1.1 benchmark results

### 3.1 Final authoritative live run

Artifact: `output/benchmark/v1_1_conversation_live_report.json`

SHA-256: `362cd644443d5ce05fcfc8e8ebf28eb2fe154667e717aae9fad5d3f8cd9bbc8a`

| Metric | Result |
|---|---:|
| Cases complete | 50/50 |
| Route accuracy | 100% |
| Status accuracy | 100% |
| Response-mode accuracy | 100% |
| Capability accuracy | 100% |
| Deterministic safety route accuracy | 100% |
| Planner relation accuracy | 100% |
| Follow-up resolution accuracy | 100% |
| Tangent precision / recall | 100% / 100% |
| Adjacent-background precision / recall | 100% / 100% |
| Evidence-status accuracy | 100% |
| Required-limitation accuracy | 100% |
| Paid-call-boundary accuracy | 100% |
| Provider failure rate | 0% |
| Background citation leaks | 0 |
| Automated traceability failures | 0 |
| BM25 / vector / fused Recall@20 | 100% / 100% / 100% |
| Reranker Recall@5 | 100% |
| Reranker MRR@5 | 78.33% |
| Reranker nDCG@5 | 80.07% |
| Latency p50 / p95 | 0.606 s / 2.572 s |
| Provider tokens | 52,157 |
| Reported cost | $0.07547866 |

All development, sealed-holdout, and red-team split-level route/status/mode
metrics were 100%. `semantic_correctness_scored=false` and
`unsupported_verified_claim_count_scored=false`; these null fields are
intentional, not zero-error findings.

### 3.2 Adjacent repeat variability

An earlier 50-case repeat encountered a transient OpenRouter 429 on
one case after all three same-model attempts. That run completed its report but
recorded a 2% provider failure rate, 98% status/mode, 90% reranker Recall@5,
3.017-second p95, and $0.07162128 response-reported cost. Its report was
overwritten by the final rerun, so no retained artifact hash is claimed.

This observation demonstrates that bounded retry and fail-closed behavior work;
it also demonstrates that a single clean run is not proof of provider
availability. It is recorded as variability evidence, not merged into the final
scored artifact or hidden as a discarded diagnostic.

### 3.3 Offline run

Artifact SHA-256:
`1cb13ab1180ac4b9a2373819cff67780e0df66d3366e044403bb2966ac819b79`.
All 50 cases and all route/status/mode/capability/safety/planner/follow-up/
tangent/adjacent/evidence/limitation/paid-boundary checks were 100%. Retrieval
Recall was 100% for BM25, fused, and the fake reranker; fake dense Recall was
40%. This proves deterministic wiring and fixtures, not real semantic ranking.

### 3.4 Dataset integrity

| Dataset | Cases/splits | Dataset SHA-256 | Sealed-holdout SHA-256 |
|---|---|---|---|
| V1.1 conversation | 50: 30 dev, 10 holdout, 10 red-team | `922ab1a5e61866bff7f113b59f82d10c0b7a165f83584979d3cce83763ad70d9` | `a76deab5553a9549ce81a888d3ad7d722cf2625e21e938d7d13cbbdcbf98e53e` |
| V1 compatibility | 100: 60 dev, 20 holdout, 20 red-team | `75414daede41d029ecb233b380053546c279eb4ed33a201c19a5ceb5d2e6afef` | `d16eb54a8a9d88d27db776db83171d555a90cd8bdc971ce436349cbc238420fe` |

V1.1 manifest SHA-256:
`7a2ba273c60f415447eaad83d51778c8b2ce8e46e3ea1efe24f5688d3386319f`.
V1 manifest SHA-256:
`39a33230fcf5e7d6bbb380dfc76eb3c35aa23cedcd1482fbd1c18ef1485c3786`.

## 4. Retrieval evidence

### 4.1 Contextual A/B/C experiment

Artifact SHA-256:
`10a927718191e986b753d3e99828e1d25aaa35174d2a58dd0069845ff67cbb97`.
Eight grounded development cases only; sealed holdout unopened; no answer
generation; provider error count zero.

| Candidate | BM25 Recall@20 | Dense Recall@20 | Fused Recall@20 | Rerank Recall@5 | MRR@5 |
|---|---:|---:|---:|---:|---:|
| A — raw question/original text | 87.5% | 87.5% | 87.5% | 87.5% | 58.75% |
| B — saved plan/original text | 100% | 100% | 100% | 87.5% | 79.17% |
| C — saved plan/metadata context | 100% | 100% | 100% | **100%** | **81.25%** |

Reported cost was $0.062848. Candidate C cleared the locked two-point rule and
was selected as `metadata_context_v1`; the governed 180 × 1,536 index was then
rebuilt. Retrieval metadata is never eligible citation text.

### 4.2 Locked V1 retrieval sweep

Artifact SHA-256:
`fe0d65d4c852bff051d02ede857a6b45ebc22a8c244cd53d1c031be54929ebac`.
Fifty answerable development cases; holdout unopened; total cost $0.54486652.

| Candidate | Configuration | Recall@5 | MRR@5 | nDCG@5 |
|---|---|---:|---:|---:|
| current | BM25 20, dense 20, RRF 60, rerank 5 | **96%** | **86.17%** | **85.12%** |
| broader recall | 30, 30, RRF 60, 5 | 96% | 82.73% | 83.06% |
| rank-sensitive | 20, 20, RRF 30, 5 | 96% | 80.33% | 82.32% |
| wider evidence | 20, 20, RRF 60, 8, scored at five | 92% | 81.17% | 82.23% |

No challenger cleared the locked two-point safety rule; current 20/20/60/5 was
retained. The wider candidate is still scored at Recall@5 and cannot claim an
artificial gain from returning eight items.

## 5. Canary and V1 compatibility

### 5.1 Thirty-call canary

Artifact SHA-256:
`5fddb360cb8c95196fe7cfd99faddb89c5921c1e80c7302a1a7bedd6cda35f7d`.
All 30 calls were structurally accepted; status variance and reason-code
variance were both false. p95 latency was 2.565 seconds and reported cost was
$0.12597612. It establishes repeatability for one canary question, not general
semantic correctness.

### 5.2 Current legacy V1 compatibility run

Artifact SHA-256:
`343af1d24c2a16d36a63bf75f56a8ea5924dc3237d04d5088f62f2fbc411569b`.

- 100/100 cases complete;
- safety route/status 100%;
- citation ID and exact quote validity 100%;
- route 85%, status 76%, accepted validation 80%;
- reranker Recall@5 92.42%, MRR@5 77.40%, nDCG@5 79.99%;
- one provider error, p95 2.924 seconds, $0.28428938 cost.

Most route/status mismatches arise because the older labels expect corpus-only
static/abstention behavior, while V1.1 intentionally introduces capability,
background, tangent, and follow-up modes. That contract conflict explains the
compatibility diagnostics but does not excuse the 92.42% retrieval result. The
explicit 95% V1 retrieval gate remains failed.

## 6. Cost accounting

| Retained successful evidence command | Cost |
|---|---:|
| Final V1.1 live benchmark | $0.07547866 |
| Contextual A/B/C experiment | $0.06284800 |
| Four-candidate V1 retrieval sweep | $0.54486652 |
| Legacy V1 full compatibility run | $0.28428938 |
| Thirty-call canary | $0.12597612 |
| **Retained successful-artifact total** | **$1.09345868** |

The earlier rate-limited repeat reported another $0.07162128 and is
described separately because its artifact was overwritten. Other iterative
diagnostics are not included. These values come from response usage metadata;
the full OpenRouter account/session spend is not available and is not asserted.

## 7. Artifact hashes

| Artifact | SHA-256 |
|---|---|
| Corpus JSONL | `a6a26b22c45b1a17e286f38fb2af45b5d4baaf70f6c4c729243668b1355caa2f` |
| Corpus manifest | `ddeabeedc13778c1247d57be2c1e97d6e1cb311e672fa8e21d5f401e7f2821b3` |
| Vector matrix | `68d6fe79c19c2f50068a2b50d373781f56517c05dfff22ec76228770e1d74b03` |
| Vector manifest | `3024914bb9a263e5e2a3c8c5204e9bd8a63e073b5a7a41d02e52bbee585dbfc0` |
| V1.1 offline report | `1cb13ab1180ac4b9a2373819cff67780e0df66d3366e044403bb2966ac819b79` |
| V1.1 live report | `362cd644443d5ce05fcfc8e8ebf28eb2fe154667e717aae9fad5d3f8cd9bbc8a` |
| V1.1 live review packet | `cca0de70ea14ed54c598369a078a1a4cda7eceb540e36ed75918d0380b321107` |
| Contextual A/B/C report | `10a927718191e986b753d3e99828e1d25aaa35174d2a58dd0069845ff67cbb97` |
| V1 retrieval comparison | `fe0d65d4c852bff051d02ede857a6b45ebc22a8c244cd53d1c031be54929ebac` |
| V1 full compatibility report | `343af1d24c2a16d36a63bf75f56a8ea5924dc3237d04d5088f62f2fbc411569b` |
| Canary report | `5fddb360cb8c95196fe7cfd99faddb89c5921c1e80c7302a1a7bedd6cda35f7d` |

## 8. Exact semantic-acceptance action

The owner must perform and record these checks before the release label changes:

1. Open `output/benchmark/v1_semantic_review.md` and review all 20 V1 red-team
   cases plus its fixed 10-case ordinary sample.
2. Open `output/benchmark/v1_1_conversation_live_review.md` and review all 10
   V1.1 red-team cases plus every case containing an accepted grounded or
   background claim.
3. For each claim, check that the displayed quote entails the claim, all
   required concepts appear, forbidden claims are absent, and limitations are
   appropriate. Capability/scope cases must be checked against their declared
   deterministic concepts.
4. Mark each case approve/reject/needs discussion and add reviewer identity,
   date, and notes. Do not edit benchmark expectations during review.
5. Move rejected development cases into labelled fixes. A holdout failure may
   inform a class-level design change, but its individual answer must not be
   tuned directly.
6. Re-run `make verify`, `make benchmark`, one cost-capped live V1.1 benchmark,
   and the relevant compatibility retrieval check after any code/config change.

Only when semantic review passes, the 95% legacy retrieval gate is resolved or
formally superseded by an approved ADR, and a fresh manual visual review is
recorded may the owner consider the product release-qualified.

## 9. Historical V1 evidence (preserved)

The original V1 completion ledger recorded a single-turn, corpus-only candidate
with a then-current 69-test Python suite, 100% safety and citation structure,
81.82% reranker Recall@5 on its complete live run, 3.14-second p95, $0.2444 full
benchmark cost, and a 30-call canary at $0.1284. It also recorded a manual local
browser reproduction. That evidence remains historically valid for that code
state but is superseded for V1.1 current-state claims.

V1.1 changes the product contract, benchmark, index text, test count, frontend,
and runtime paths. Historical V1 values must not be combined with V1.1 values as
if they came from one run.
