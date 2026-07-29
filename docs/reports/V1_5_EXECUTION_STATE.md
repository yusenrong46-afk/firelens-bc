# FireLens BC V1.5 execution state

Updated: 2026-07-28 (America/Vancouver)

## Repository truth

- Canonical checkout: `/Users/thomas/Downloads/firelens-bc 2`
- Canonical branch/commit: `improvement/rag-webapp-v2` at
  `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- Canonical state: tracked-clean with 26 preserved untracked files; read-only for this task
- Lab checkout/branch: `/Users/thomas/Downloads/firelens-bc-v1-5-lab` on
  `codex/v1-5-lab`
- Final provenance-complete probe commit: `727110ec3c9626601fb4c04375eba4a1be572703`
- Candidate code commit before this ledger update: `eca9119511d79e089526a6d163b8481c9c4a2205`
- Owner semantic gate commit: `46ae83a`; sealed 47-case retrieval gate commit: `eca9119`
- Release branch: `codex/v1-5-release` remains at the V1.1 baseline; no release
  worktree exists
- Main and production: unchanged

## Current decision

The lab implementation is complete enough for review and demonstration, but it is **not a
production-qualified V1.5 release**. The release branch must remain at the baseline because the
previous independently frozen retrieval holdout did not pass the 96% Recall@5 gate. A new
post-configuration-freeze 47-case candidate is now hash-frozen, but its relevance labels and the
50-case semantic entailment review are both pending owner approval. The new sealed set has not
been run against paid providers.

Development evidence that used the Codex-authored relevance addendum is retained as useful
diagnostic evidence, but it no longer authorizes promotion.

## Executed evidence in this qualification

- `make verify`: 152 Python tests passed, 10 skipped, 36 subtests passed; Ruff,
  formatting, mypy over 51 source files, secret scan, generated OpenAPI/types,
  12 frontend tests, production build, 4 Sites tests, and 12 desktop/mobile
  Playwright flows all passed.
- Frozen independent retrieval holdout: 16 answerable cases, three repetitions,
  Recall@5 `81.25%`, `87.5%`, and `87.5%`; rankings differed. The run used no relevance
  addendum and no tuning, but all labels remain `codex_draft`.
- New sealed retrieval candidate: 47 unique answerable holdout cases, zero exact question overlap
  with the preserved V1 benchmark, all 47 raw chunk IDs validated against the governed corpus,
  dataset SHA-256 `178f7b2cbedb4b308c2e1e2eaf1a6e79855e854d2d0a277147bbd90081211564`.
  The owner sidecar is hash-bound and currently 0/47 approved. The paid runner was exercised and
  reported `paid_calls_started: false`; it cannot initialize the runtime until approval passes.
  A human-readable packet contains all 47 questions and 51 exact original corpus passages.
- Owner semantic review: hash-bound 50-case live-provider sidecar generated, currently 0/50
  approved. Whitespace reviewer names, offline reports, wrong report counts, changed report hashes,
  missing cases, and missing claims fail closed.
- Provenance-complete limitation probe: `162/165` (`98.18%`), with per-case route,
  retrieval-stage chunk IDs, status, latency, models, attempts, tokens, and cost.
- Novel-document grounding: `9/10`; corpus-gap, personal-safety, medical, poison-source,
  citation-bait, conflict, and leave-one-source-out gates all passed perfectly.
- Paid 50-case conversation benchmark: response-mode/status accuracy `98%`, route and
  deterministic-safety accuracy `100%`, no provider failures, no automated traceability or
  lexical claim-support failures, and p95 `3.790 s`.
- Refreshed real official-live qualification at `eca9119`: all three ArcGIS layers available,
  253 displayable records, metadata complete, chat/map identifiers and statuses matched, and
  cached p95 `0.339 s` over 26 requests including concurrency `1`, `5`, and `20`.
- Rendered browser verification covered anonymous homepage, live answer, mixed answer, grounded
  static answer, exact source passage, desktop map, and 390x844 mobile map-after-answer layout.
  No console errors or framework overlays were observed.

## Candidate and experiment state

- Production candidate retrieval strategy: `metadata_context_v1`, BM25/vector/fused
  `30/30/30`, RRF `60`, rerank `5`.
- `document_context_v2`: implemented but excluded; it did not clear the measured promotion gain.
- GraphRAG: excluded at the dependency boundary. The exporter and raw-chunk provenance contract
  exist, but no qualified real GraphRAG run exists and no compatibility proxy was added.
- Official live incident, perimeter, and wildfire evacuation layers: implemented and real-source
  qualified.

## Cost and artifact truth

This final qualification sequence recorded `$0.89834580` of OpenRouter usage, including the
focused security calibration, frozen holdout, two 165-case runs, 50-case conversation benchmark,
and two rendered static-generation checks. The final provenance-complete 165-case run alone used
286,681 tokens and cost `$0.31654526`. No direct-vendor call was used.

Canonical ignored artifacts:

- `output/benchmark/v1_5_frozen_holdout_retrieval.json`
- `output/benchmark/v1_5_retrieval_owner_review.md`
- `output/benchmark/v1_5_retrieval_owner_review.yaml`
- `output/benchmark/v1_1_conversation_live_report.json`
- `output/benchmark/v1_1_conversation_live_review.md`
- `output/benchmark/v1_5_owner_semantic_review.yaml`
- `output/naive_user_probe/results.json`
- `output/qualification/v1_5_live.json`

Their hashes are recorded in `docs/reports/FIRELENS_V1_5_EVIDENCE.md`.

## Blocking gates

1. The new 47-case sealed retrieval candidate is frozen but intentionally unopened. Its relevance
   sidecar is 0/47 pending owner approval; only then may the one-time three-repetition paid gate run.
2. The preserved 16-case independent run remains a failed historical result. Development results
   and the Codex-authored relevance addendum do not authorize promotion.
3. Automated checks establish exact traceability and a lexical support floor, not semantic
   entailment. The hash-bound owner semantic review is 0/50 pending.
4. Distributed production throttling and an anonymous preview remain external deployment gates;
   the application correctly labels its local rate guard as instance-local.

## Maximized-optimization continuation

- The final fixed-planner query-policy comparison completed all 200 treatment rows with zero
  provider errors. It recorded model IDs, attempts, 55,568 tokens, provider timings, wall latency,
  and `$0.49713884` provider-reported cost. Artifact SHA-256:
  `342b7f4a07103f79e9d6274579476ede1b0c5ebc065dd73d4a8520e9c2133c0e`.
- On 47 route-eligible development cases, current retrieval retained 100% Recall@5, 85.46% MRR@5,
  and 91.84% mean source coverage. Original-question retrieval and both original-question rerank
  treatments fell to 97.87% Recall@5; none passed the locked promotion rule. Production remains
  unchanged.
- Zero-cost lexical comparison: field weighting moved BM25 MRR@5 from 70.33% to 71.00% with
  unchanged 88% Recall@5; identifier-preserving tokenization was neutral on these cases. Neither
  cleared the three-point MRR or two-point Recall promotion rule.
- Lexical artifact SHA-256:
  `237551e0569b70e78eb9f17608f3e70b970323a471f51cd91bf8e6c0b295f778`.
- Production query handling, BM25 tokenization, retrieval settings, and runtime models remain
  unchanged.
- Post-experiment `make verify`: 152 Python tests passed, 10 skipped, 36 subtests passed; Ruff,
  formatting, mypy, secret scan, generated contracts, 12 frontend tests, production build, 4 Sites
  tests, and 12 Playwright desktop/mobile flows passed.

## Next authorized action

The OpenRouter limit is now `$20`; the final read-only status check reported usage `$10.90011477`
and `$9.09988523` remaining. The valid fixed-planner comparison is complete and retained current
retrieval. Complete the two owner sidecars next. After the 47 retrieval labels are approved, run
the sealed retrieval gate exactly once; only qualifying evidence may change production.

Do not populate `codex/v1-5-release`. Both owner reviews and a passing one-time sealed retrieval
run remain mandatory even if a development experiment improves.
