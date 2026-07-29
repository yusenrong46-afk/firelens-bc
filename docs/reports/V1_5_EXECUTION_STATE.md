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

## Next authorized action

Do not populate `codex/v1-5-release`. The owner must review
`output/benchmark/v1_1_conversation_live_review.md` and provide or approve an independent sealed
retrieval set large enough to evaluate the 46/47 gate. After those inputs exist, rerun the frozen
qualification and only then reconstruct the release branch from individually passing commits.
