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
- Release branch: `codex/v1-5-release` remains at the V1.1 baseline; no release
  worktree exists
- Main and production: unchanged

## Current decision

The lab implementation is complete enough for review and demonstration, but it is **not a
production-qualified V1.5 release**. The release branch must remain at the baseline because the
independently frozen retrieval holdout did not pass the 96% Recall@5 gate and its labels are not
owner-approved. Semantic entailment review is also pending.

Development evidence that used the Codex-authored relevance addendum is retained as useful
diagnostic evidence, but it no longer authorizes promotion.

## Executed evidence in this qualification

- `make verify`: 133 Python tests passed, 10 skipped, 36 subtests passed; Ruff,
  formatting, mypy over 49 source files, secret scan, generated OpenAPI/types,
  12 frontend tests, production build, 4 Sites tests, and 12 desktop/mobile
  Playwright flows all passed.
- Frozen independent retrieval holdout: 16 answerable cases, three repetitions,
  Recall@5 `81.25%`, `87.5%`, and `87.5%`; rankings differed. The run used no relevance
  addendum and no tuning, but all labels remain `codex_draft`.
- Provenance-complete limitation probe: `162/165` (`98.18%`), with per-case route,
  retrieval-stage chunk IDs, status, latency, models, attempts, tokens, and cost.
- Novel-document grounding: `9/10`; corpus-gap, personal-safety, medical, poison-source,
  citation-bait, conflict, and leave-one-source-out gates all passed perfectly.
- Paid 50-case conversation benchmark: response-mode/status accuracy `98%`, route and
  deterministic-safety accuracy `100%`, no provider failures, no automated traceability or
  lexical claim-support failures, and p95 `3.790 s`.
- Real official-live qualification: all three ArcGIS layers available, 252 displayable records,
  metadata complete, chat/map identifiers and statuses matched, and cached p95 `1.026 s` over
  26 requests including concurrency `1`, `5`, and `20`.
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
- `output/benchmark/v1_1_conversation_live_report.json`
- `output/benchmark/v1_1_conversation_live_review.md`
- `output/naive_user_probe/results.json`
- `output/qualification/v1_5_live.json`

Their hashes are recorded in `docs/reports/FIRELENS_V1_5_EVIDENCE.md`.

## Blocking gates

1. Independent retrieval Recall@5 is below 96% and the frozen set contains only 16
   retrieval-answerable cases, so it cannot prove the requested 46/47 gate.
2. Retrieval and conversation labels are still `codex_draft`; the relevance addendum is
   `codex_evidence_audited`, not `owner_approved`.
3. Automated checks establish exact traceability and a lexical support floor, not semantic
   entailment. Owner review of the 50-case packet is required before claiming zero unsupported
   material claims.
4. Distributed production throttling and an anonymous preview remain external deployment gates;
   the application correctly labels its local rate guard as instance-local.

## Maximized-optimization continuation

- Query-policy comparison: one baseline planner decision was reused across all candidates. The
  valid original-question retrieval treatment tied the current 97.87% Recall@5 and 84.04% MRR@5
  and raised mean source coverage from 89.72% to 91.84%; this did not clear promotion.
- Original-question reranking treatments were invalid because OpenRouter began returning HTTP 403
  after the account limit was exhausted. Their partial scores are not evidence.
- Query-policy attempt cost: `$0.36941354`; ignored artifact SHA-256
  `eb36fa47775c0d60bf27c0eca4b4e2c637bd5b8354e9ac0e7dbcdb936e547520`.
- Zero-cost lexical comparison: field weighting moved BM25 MRR@5 from 70.33% to 71.00% with
  unchanged 88% Recall@5; identifier-preserving tokenization was neutral on these cases. Neither
  cleared the three-point MRR or two-point Recall promotion rule.
- Lexical artifact SHA-256:
  `237551e0569b70e78eb9f17608f3e70b970323a471f51cd91bf8e6c0b295f778`.
- Production query handling, BM25 tokenization, retrieval settings, and runtime models remain
  unchanged.
- Post-experiment `make verify`: 138 Python tests passed, 10 skipped, 36 subtests passed; Ruff,
  formatting, mypy, secret scan, generated contracts, 12 frontend tests, production build, 4 Sites
  tests, and 12 Playwright desktop/mobile flows passed.

## Next authorized action

The first development-only query-policy run used one baseline set of planner decisions and cost
`$0.36941354`. The original-question retrieval variant completed and tied the baseline's 97.87%
Recall@5 and 84.04% MRR@5 while slightly improving source coverage; it did not clear promotion.
The two original-question reranking variants were invalidated by OpenRouter HTTP 403 responses.
The read-only OpenRouter key-status endpoint then confirmed that the key's `$10` limit is exhausted
(`limit_remaining: 0`, usage `$10.00670837`). Do not retry paid evaluation until the owner raises
or replenishes that limit.

Commit the reproducible negative experiment. Do not make another paid call until the owner raises
or replenishes the OpenRouter key limit. After that, run one valid fixed-planner comparison; only
a qualifying candidate may change production.

Do not populate `codex/v1-5-release`. Owner review and a sufficiently large owner-approved sealed
retrieval set remain mandatory even if the development experiment improves.
