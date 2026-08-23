# FireLens V1.6 Round-2 engineering report

This is local zero-cost qualification of `upgrade/v1-6-qualification-round2`.
It is not a release GO. Independent Fable 5 re-examination is still required.
`ENGINEERING_IMPROVED` is not claimed. FL-V16-S1 thresholds were not edited.

## 1. Executive Implementation Verdict

Round-2 closed the reproduced semantic-preservation blind spots, froze ClaimBench
v2 before checker work, adjudicated the remaining frozen hard-probe failures
without changing the evaluator, measured a representative (not fleet) generate-call
reduction, and kept `adaptive_v1` experimental because paid H4 evidence is absent.

Implementation status: **READY_FOR_INDEPENDENT_QUALIFICATION**.

Paid retrieval and H10 preview/rollback/firewall/human gates remain BLOCKED or
EXTERNAL. Do not treat this file as release authorization.

## 2. Starting Candidate and Round-2 Candidate Identity

- Examined Round-1 candidate: `6f038b4cacc2204be2da0147240143ecfbde3c96`
- Immutable local ref: `examined/v1-6-round1`
- Frozen V1.5 baseline: `3de745a22ad0801e19563f90ac64f18609ecae03`
- Working branch: `upgrade/v1-6-qualification-round2` (local only)
- Round-2 candidate SHA: the git commit that contains this report
- Package: `1.6.0rc1` / `1.6.0-rc.1`
- Environment: Darwin arm64, CPython 3.14.5, Node v25.9.0

Frozen hashes (unchanged from Stage 0 unless noted):

| Artifact | SHA-256 |
| --- | --- |
| FL-V16-S1 | `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef` |
| ClaimBench v1 | `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1` |
| ClaimBench v2 | `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557` |
| Hard probe dataset | `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035` |
| Corpus manifest | `2d0d6b9b445f5ab0ef59e7f19bd0dce058a93f3a93b9599338702b95058ed687` |
| Vector manifest | `437181a2a9aa03498b4bb4de2445d0e0b0bf3fe1c4d4fa76a50019d31f3f1046` |
| OpenAPI (after version bump) | `9c2b8ec877787fecefbb29e225d25340fb2af359ff2d8d4c92f8716d6ef5d1bb` |

## 3. Beginning and Ending Git Status

Beginning of Round 2 (Stage 0 snapshot): examined commit `6f038b4`, branch
created, snapshot recorded `dirty: true` while state and before-evidence were
being written. Paid auth absent. Docker/Vercel CLIs absent.

Ending: one identity commit on `upgrade/v1-6-qualification-round2`; working tree
expected clean after that commit. Not pushed.

## 4. Reproduction of Fable Findings

EXECUTED on `6f038b4` before checker changes
(`docs/reports/V1_6_ROUND2_FABLE_MUTATION_REPRODUCTION.json`): 7/16 nearby
cases correct. Mutations that still passed the Round-1 checker:

```text
leave_to_stay, immediate_to_delayed, required_to_optional,
unit_swap, comparator_flip, authority_swap,
exception_reversal, stale_as_current, overlap_opposite
```

Caught already: alert_to_order, negation_drop, decimal_shift, date_swap,
condition_omission. Faithful paraphrases accepted.

EXECUTED after typed preservation
(`docs/reports/V1_6_ROUND2_FABLE_MUTATION_AFTER.json`): 15/15 correct, zero
unsafe false-accepts, zero faithful false-rejects. Independent examiner cases
remain necessary.

## 5. Frozen ClaimBench v2 Identity

Catalog `data/evaluation/claimbench_v1_6_2.yaml` was committed in `4bb3dcd`
before checker implementation. SHA-256
`402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557`.

- 332 cases: 86 faithful / 246 mutations
- parent: 200 v1 cases plus 36 faithful and 96 mutation extras
- `independent_examiner_cases_still_required: true`
- Catalog was not rewritten after checker work began

Before-checker: 265/332; unsafe FA 25.6%; faithful FR 4.7%.
After-checker EXECUTED: 332/332; unsafe FA 0; faithful FR 0; preservation 1.0;
always-abstain false.

Salvage/rewrite/full-pipeline rates in the v2 evaluator are equal to the
checker unsafe-accept rate (INSPECTED). Selected salvage, rail, Proof Card, and
live-composition paths were EXECUTED in unit tests.

## 6. Semantic-Generalization Changes

New typed extractors in `src/firelens/answering/critical_fields.py` cover
quantities/units (canonical length/time/volume dimensions, 8% relative
tolerance only across units so 1.5 m ≈ 5 ft and 1.5 m → 1.5 feet fails),
comparators, authority/jurisdiction, freshness, modality, exceptions, and
actions.

Freshness wording is centralized in `src/firelens/freshness_language.py` and
used by claim validation, output rails, Proof Cards, and live prefixes.
Generated claims may not invent an authority absent from quotes. Unknown
authority stays unknown.

## 7. Full-Pipeline Adversarial Results

EXECUTED:

- Checker rejects all nine reproduced Fable mutations and accepts faithful
  conversions/paraphrases
- Partial salvage cannot keep a unit-swap claim
- A mutated-only draft cannot be published
- Output rail blocks “current/latest/live” on stale records
- Stale Proof Card / banner headlines do not say current
- ClaimBench v2 332/332 with always-abstain false

INSPECTED: mixed live+static headline remains “Official records plus reviewed
guidance”; live-only uses the freshness-aware official-records headline.

## 8. Hard-Probe Adjudication and Before/After Results

Evaluator and frozen expected outcomes were not changed.

| Point | Score | Class |
| --- | --- | --- |
| V1.5 baseline | 78/105 | INSPECTED (Fable Round-1) |
| Round-1 examined | 82/105 | EXECUTED on `6f038b4` |
| After PG2, before contract fixes | 82/105 same 23 IDs | EXECUTED |
| After PG3 contract fixes | 86/105 | EXECUTED |
| PG7 re-run | 86/105 | EXECUTED |

Newly passing vs Round-1: D10, J03, K04, K10 (personal highway, personal
under-status, invented perimeters, active BC wildfires live lane).

Remaining 19 IDs are taxonomy disagreements (`scope_redirect` /
`requires_input` vs allowed abstention|live), FakeProvider related-route
background, or unsupported capability (Okanagan gazetteer, named-fire
freshness). Adjudication:
`docs/reports/V1_6_ROUND2_HARD_PROBE_ADJUDICATION.json`.

## 9. Adaptive Retrieval Development Comparison

Default strategy remains `baseline`. `adaptive_v1` stays opt-in and disabled.

Dry-run EXECUTED: 50 development cases, pairing validated, sealed labels not
inspected, ranking-metric imports OK. Provider metrics BLOCKED. FakeProvider
ranking is not H4 evidence. Decision: keep experimental and disabled.

## 10. Paid Benchmark Authorization and Cost Estimate

`FIRELENS_PAID_RETRIEVAL_BENCHMARK_AUTHORIZED` absent.
`FIRELENS_MAX_RETRIEVAL_BENCHMARK_USD` absent. OPENROUTER key absent.

Maximum-cost estimate EXECUTED in dry-run arithmetic:

- 50 cases × 2 strategies × 6 queries
- 600 embedding + 600 rerank calls
- embed $0.02/MTok, rerank $0.02/call, 1.2× buffer
- **$14.4072**

Exact command:

```text
FIRELENS_PAID_RETRIEVAL_BENCHMARK_AUTHORIZED=1 \
FIRELENS_MAX_RETRIEVAL_BENCHMARK_USD=14.4072 \
.venv/bin/python scripts/v1_6_round2_retrieval.py --paid
```

Do not run unless both env vars exist and the ceiling is ≥ $14.4072.
Sealed 46/47 remains EXTERNAL; do not inspect labels.

## 11. Matched Provider-Call and Latency Comparison

EXECUTED: same machine, CPython 3.14.5, FakeProvider, ASGI `/api/v1/ask`,
10 warmup + 30 measured per route, V1.5 worktree at `3de745a2`.
Label: **representative_workload_average**, not fleet average.
Workload SHA-256 `972abb2df3bb6821ff87326a788961a3c2631c60a4ab072c0ec5269a4203ce08`.

| Metric | V1.5 | Round-2 |
| --- | --- | --- |
| Weighted generate calls | 1.2 | 0.7 (−41.7%) |
| Pure-static generate calls | 2.0 | 1.0 |
| Failures | 0 | 0 |

Pure-static outer chat turns remain 0 in golden traces (EXECUTED via pytest).
The V1.5 generate_calls=2 includes the discarded outer write.

Mixed live+static p95 rose because Round-2 runs reviewed-guidance generation
(2 generate calls vs V1.5 live-only 1). Remaining >10% p95 flags are
0.13–0.26 ms FakeProvider jitter with unchanged generate-call counts. These
are not production SLO evidence.

Content-free counters now include embedding, rerank, retrieval cycles, and
rewrites.

## 12. Packaging and Runtime-Artifact Evidence

`make v1-6-package-verify` logical Docker/Vercel path parity: passed
(EXECUTED). Staged filesystem inventories: BLOCKED (no Docker/Vercel CLI).
`.dockerignore` excludes `data/evaluation`, `docs`, `tests`, `output`
(INSPECTED). External scripts:
`docs/reports/V1_6_ROUND2_EXTERNAL_GATES.md` (READY_FOR_EXTERNAL_EXECUTION,
not EXECUTED). Documentation is not rollback proof.

## 13. Tests Added Before Implementation

Commit `f707c83` added failing critical-field tests before checker changes:
Fable nearby mutations, faithful conversions, salvage, unpublished mutated
draft, stale Proof Card/banner, output rail, mixed composition.

Commit `4bb3dcd` froze ClaimBench v2 and `tests/test_claimbench_v2.py` before
checker work.

## 14. Tests and Commands Executed

EXECUTED:

- `make verify` — secret-scan, OpenAPI, ruff, mypy, 872 pytest (3 skipped,
  448 subtests), vitest 47, frontend build, Sites 4, Playwright 26
- `make v1-6-round2-gate` — ClaimBench v1 200/200, v2 332/332, hard probe
  86/105, retrieval dry-run, matched performance, package-verify
- Fable mutation before/after harnesses
- `make v1-6-round2-report` after this file exists

## 15. Test Integrity Review

- Frozen 105-case dataset and evaluator semantics unchanged
- FL-V16-S1 thresholds unchanged
- ClaimBench v2 catalog hash unchanged after checker work
- No test deleted or skipped to create a pass
- Playwright stale-headline count 2→3 because the status banner now uses the
  same canonical “Official cached records” headline; “Current BC wildfire
  information” remains count 0
- Hard-probe gate floor is 86/105 (no paired regression), not 105/105
- Sealed labels were not inspected

## 16. Files and Modules Changed

Relative to `6f038b4`: ClaimBench v2 catalog/loader/tests; typed
`critical_fields.py` and `freshness_language.py`; checker, rails, Proof Cards,
live composition; intent pattern extraction and D10/J03/K04/K10 routing;
Round-2 harnesses and Makefile targets; representative workload; adjudication
and evidence reports; package `1.6.0rc1` / web `1.6.0-rc.1`; OpenAPI regen.

## 17. Local Commits and Rollback Points

| Commit | Why |
| --- | --- |
| `9337a16` | Stage 0 preserve examined candidate and reproduce Fable gaps |
| `4bb3dcd` | Freeze ClaimBench v2 before checker work |
| `f707c83` | Failing critical-field tests before implementation |
| `4ce61ab` | Typed critical-field preservation |
| `9558fd0` | Adjudicate 23 frozen failures without evaluator edits |
| `5855782` | Contract fixes for D10/J03/K04/K10 |
| `43460f3` | Retrieval dry-run, performance harness, external-gate prep |
| `23da2b0` | Format measurement scripts |
| identity commit | Version, report, and candidate freeze |

Rollback to Round-1: `git switch examined/v1-6-round1`.
Rollback to V1.5: `3de745a22ad0801e19563f90ac64f18609ecae03`.

## 18. Remaining External, Paid, Human, and Sealed Gates

| Gate | Status |
| --- | --- |
| Paid adaptive retrieval development | BLOCKED |
| Sealed 46/47 ×3 | EXTERNAL |
| Docker image build/inspect/health | BLOCKED |
| Vercel staged inventory | BLOCKED |
| Preview deploy | READY_FOR_EXTERNAL_EXECUTION |
| Rollback rehearsal | READY_FOR_EXTERNAL_EXECUTION |
| Firewall/rate-limit publish | EXTERNAL |
| VoiceOver / comprehension | READY_FOR_EXTERNAL_EXECUTION |
| Production smoke | EXTERNAL |

## 19. Résumé and Documentation Claims Now Supported

Locally supported with cited evidence: typed unit/comparator/authority/freshness
preservation against the reproduced Fable mutations; ClaimBench v2 332/332 on
the frozen catalog; hard probe 86/105 with no paired regression vs 78/105 and
82/105; pure-static outer calls 0; representative generate-call reduction
41.7%; adaptive retrieval remains disabled; logical Docker/Vercel path parity
passes.

## 20. Claims Still Prohibited

Do not claim ENGINEERING_IMPROVED, release GO, fleet-average latency or cost,
H4 retrieval quality, sealed 46/47, production p95, executed Docker filesystem
inspect, executed preview/rollback/firewall, or human AT pass. Independent
examiner mutations remain necessary. ClaimBench v2 is stronger than v1 and
still co-located with this repository.

## 21. Exact Commands for Fable 5 Re-examination

```text
git rev-parse HEAD
git status --short
git rev-parse examined/v1-6-round1
make verify
make claimbench-v2
make v1-6-hard-probe
make v1-6-retrieval-dry-run
make v1-6-performance
make v1-6-package-verify
make v1-6-round2-gate
make v1-6-round2-report
```

Do not run paid retrieval or sealed 46/47 without both authorization variables
and a ceiling at or above $14.4072. Do not inspect sealed labels. Do not push.

## 22. Final Status

READY_FOR_INDEPENDENT_QUALIFICATION
