# FireLens — Pacific Clarity (campaign tracker)

Branch: `cursor/firelens-pacific-clarity`
Base main SHA: `58eb80153358c82a5be1da095245e627b5c0ed05`
Base tree: `bff218c162b0c5329040e4533b56ef5ab393024a`

## Gate status

- PC-000 baseline: done (prod ready identity, bundle before, plan file)
- PC-010..070 UI: done
- PC-080 readiness: done + Vitest
- PC-090 multi fire centre: done + pytest
- PC-110 gates: local frontend + ClaimBench + hard probe rc2.2 + source-aware done; screenshots/perf harness deferred
- PC-130 preview/prod: pending commit + deploy

## Decisions locked

- Written prompt overrides screenshot mood.
- `CoarseResolvedLocation` has no label → omit place chip/headline place when no typed session location.
- Compact map for spatial; full map for idle explore / non-compact rail.
- Explanation card omitted (no fabricated glossary / no extra LLM call).

## Ticket log

### PC-000
- evidence: evals/pacific_clarity/baseline.json, performance_before.json

### PC-010–070
- files: App.tsx, ProductSidebar, LiveDataStatus, ContextChips, OfficialSourcesCard, tokens/shell/answer.css, LiveAnswerSummary, SourceProof, LiveMap variant, ConversationPanel, QuestionComposer, pacific-landscape.svg

### PC-080
- fetchReadyHealth fixed; readiness on session; LiveDataStatus truth

### PC-090
- official_fire_centres_from_question + clarification terminal plan

### PC-110
- Vitest 173 pass; ClaimBench pass; hard probe rc2.2 exit 0; source-aware pass
- remaining: Playwright screenshots, v1-6-performance, preview Reality Gate

## Remaining work
Commit, preview deploy, Reality Gate on preview, production only if authorized.
