# FireLens V1.6.4 fix record

Starting identity: `codex/v1-6-4-coherent-truth` from `f8543e91b86645cc82221761bf63649e5a865191`.

Gate 6 local qualify: pytest 1983 passed / 10 skipped; ruff and mypy passed; vitest 166 passed plus the idle-summary assertion; ClaimBench v2 332/332; offline RC2.2 hard probe 91/105 with zero paired regressions vs Round 3. Browser checks at 320px, tablet, and desktop: product-first header, `V1.6.4`, idle live summary, no official-source banner on idle, map not auto-opened. Public identity is `1.6.4`. Status: `VERIFIED_READY_FOR_HUMAN_REVIEW`. Stretch F164-022/023 remain deferred.

State machine: UNTRIAGED -> REPRODUCED|NOT_REPRODUCED_CURRENT_BRANCH -> ROOT_CAUSE_IDENTIFIED -> REGRESSION_TEST_ADDED -> FOCUSED_TEST_PASS -> NEIGHBORING_TESTS_PASS -> BROWSER_OR_API_VERIFIED -> DONE

## Gate 0 schema inspection

BCWS `BCWS_ActiveFires_Points` exposes `FIRE_OF_NOTE_IND` and `WAS_FIRE_OF_NOTE_IND` as `Y`/`N` strings. The V1.6.3 adapter dropped both fields. `FIRE_STATUS` can independently be `Fire of Note`. Ranking uses the indicator, with status as a fallback.

## Tickets

| ID | State | First divergence | Notes |
|---|---|---|---|
| F164-001 | DONE | `fetchOfficialMap` + `deriveSessionMapView` | `requested_layers`; context layers opt-in only |
| F164-002 | DONE | mixed `live_results` + analysis shell | Mixed `presentation_shell=chat`; ≤8 sample IDs |
| F164-003 | DONE | `records[:8]` after ID sort | `fire_of_note` + information-value ranking |
| F164-004 | DONE | exact capability match | Registry `accepted_paraphrases` (≥10) |
| F164-005 | DONE | global official banner | Response-aware `provenance_class` |
| F164-006 | DONE | corpus deixis without antecedent | Clarification, empty `live_results` |
| F164-007 | DONE | `ANALYTICAL_QUERY` / `MAP_INTENT` | Backend `presentation_shell` only |
| F164-008 | DONE | quote-only concatenation | Structured distinction, no synthesized 9-1-1 advice |
| F164-009 | DONE | analysis rail clip | Wider rail + wrap |
| F164-010 | DONE | limitation stack | `select_public_limitations` |
| F164-011 | DONE | suggestions only on CAPABILITY | Registry allowlist |
| F164-012 | DONE | no low-substance gate | Unclear-input clarification |
| F164-013 | DONE | raw IDs | `Unnamed incident {id}` |
| F164-014 | DONE | corpus-verified / reason codes | Plain history and abstention labels |
| F164-015 | DONE | idle marketing copy | Zero-generation `/api/v1/live/summary` |
| F164-016 | DONE | bare related links | Typed handoff cards |
| F164-017 | DONE | hardcoded `V1.6` | Header reads `/api/v1/health/ready` |
| F164-018 | DONE | catalogue reset on close | Keep ready catalogue; retry aborted loads |
| F164-019 | DONE | request/feedback only | Allowlisted `/api/v1/product-events` |
| F164-020 | DONE | total latency only | `stage_metrics` total + tokens/cost when exposed |
| F164-021 | DONE | adaptive experiment | `retain_baseline` recorded |
| F164-022 | DEFERRED | stretch | CSV helper exists |
| F164-023 | DEFERRED | stretch | Saved-scope helper exists |
| F164-024 | DONE | employer-first header | Product-first header; evaluator copy in How-it-works |
