# FireLens same-day stabilization

**Terminal state: `SAMEDAY_STABILIZATION_READY_FOR_DEPLOY_REVIEW`**

This is not the Astra refactor. Production was not pushed.

## Identity

| Field | Value |
| --- | --- |
| Starting SHA | `ffae3c96ce271aed24e94876d9aab76c437acc55` |
| Final product SHA | `2eb940d069b24b2afbe522a464c387a1a42b0d9a` |
| Product | FireLens 1.6.4 |
| Branch | `codex/v1-6-4-coherent-truth` |
| Provider | `openai/gpt-5.6-luna` |
| Retrieval | `metadata_context_v1` / baseline |
| Preview URL | `https://firelens-no9fstydl-yusenrong46-9212s-projects.vercel.app` |
| Preview deployment | `dpl_2u24P51ZWETX8QiRazGVFKgUeU2b` |
| Ready | `/api/v1/health/ready` JSON `build_commit=2eb940d069b24b2afbe522a464c387a1a42b0d9a`, `release_version=1.6.4` |

The product candidate that preview binds is `2eb940d`. Later documentation-only commits may exist; they do not change that bind.

## Files changed

Product and evaluator owners:

- `src/firelens/answering/intent_lexicon.py`
- `src/firelens/answering/intent_guidance.py`
- `src/firelens/answering/intent.py`
- `src/firelens/answering/intent_patterns.py`
- `src/firelens/answering/intent_conversation.py`
- `src/firelens/answering/live_request_intent.py`
- `src/firelens/answering/live_evacuation.py`
- `src/firelens/answering/live_analysis.py`
- `src/firelens/answering/live_analysis_distance.py`
- `src/firelens/answering/live_handoffs.py`
- `src/firelens/guidance_capabilities.py`
- `src/firelens/agent/fallback_brain.py`
- `src/firelens/agent/query_plan.py`
- `src/firelens/agent/live_selection.py`
- `src/firelens/agent/compose.py`
- `src/firelens/agent/loop.py`
- `src/firelens/agent/loop_support.py`
- `src/firelens/agent/rails.py`
- `src/firelens/agent/runtime_tools.py`
- `src/firelens/agent/prompts.py`
- `src/firelens/evaluation/firelens200_grader.py`
- `benchmarks/firelens200/run_campaign.py`
- `scripts/run_firelens200_focused.py`
- `tests/test_sameday_stabilization.py`
- `tests/test_firelens200_grader.py`
- `tests/test_architecture.py`
- `docs/ARCHITECTURE_V1_6.md`
- `.gitignore`, `.vercelignore`

## Root cause per ticket

### TODAY-001 — Mixed-intent collapse

First divergence: clause split + static planning, not compose.

`why` and `write` were missing request starters, so sky-blue rematched as a
fronted place and the haiku clause never split. `planned_static_subrequest`
then dropped any non-reviewed half once live layers existed.

Fix: keep an explicit static half when a distinct non-live clause exists;
route it through `ANSWER_GENERAL_BACKGROUND` unless reviewed guidance owns
it. That tool now calls background generation directly so adjacent RAG cannot
swallow a conceptual clause (FL200-072).

### TODAY-002 — Live routing

- FL200-013: `briefing` was not a record noun.
- FL200-015: `_count` always reported incident/perimeter counts.
- FL200-016: type-breakdown was not an evacuation-record question.
- FL200-017: freshness lacked `checked` and did not open live layers.

Evacuation overlays skip reviewed-guidance / definition questions.

### TODAY-003 — Typed handoffs

Reception centre, utility outage, park closure, insurance, and live weather
were missing from unsupported-live topics and official links. Utility wording
also kept independent evacuation layers. Handoff-only questions now terminate
with a typed official link.

### TODAY-004 — Personalized safety

`Should my elderly parent leave…` missed `_PROHIBITED_PATTERNS`. Packing
exclusion stays non-prohibited.

### TODAY-005 — 9-1-1 quote-only

`immediate_danger_contact` required a wildfire token and a trapped/medical
condition. “Flames near houses” now binds the quote-ready capability. Preview
answers used reviewed emergency wording, not general-knowledge dispatch
advice.

### TODAY-006 — Multi-turn selected record

“Tell me more about that one” was not selected-record deixis. The planner
LISTs the prior place, and `selected_live_result_id` inherits the closest
prior record or the uniquely named assistant record. FL200-107 bound
`incident:1261` on 3/3 runs.

### TODAY-007 — Grader

See `evals/sameday_stabilization/evaluator_fixes.md`. FL200-164 is a
`BENCHMARK_DEFECT` in the checker, not the product. An explicit unavailable
mixed clause is no longer a false provenance fail.

## Benchmark fixes

- Live numeric / wrong entity type
- Required-clause coverage
- Quote-only vs `general_knowledge`
- Selected-record identity + sibling consistency
- Haiku output form
- Metamorphic helpers
- FL200-164 `varies_by_case` live snapshot allowed

## Focused provider results

69 Ask rows on `0cdd121` / `dpl_323YJXmKERij6Z11hhhMmbqRsVCr`, then FL200-072
replaced by 3/3 on `2eb940d` / `dpl_2u24P51ZWETX8QiRazGVFKgUeU2b`.

| Gate | Result |
| --- | --- |
| FL200-068/069/072/083/085 | **3/3 PASS mixed** |
| FL200-013/015/016/017/018 | PASS live |
| FL200-107 | **3/3 PASS**, selected `incident:1261` |
| FL200-134 | 3/3 PASS `requires_input` (not an evac dump) |
| FL200-135 | 3/3 PASS reviewed quote-only wording |
| FL200-145–149 | PASS `scope_redirect` typed handoffs |
| FL200-164 | PASS live snapshot |
| FL200-171/172 | REVIEW abstention (authority unchanged) |
| Remaining FAIL | 067 (safety owns mixed live), 073 (DriveBC link not typed), 074 (history triple), 108 (selected id unbound) |

Overall after 072 replacement: **51 PASS / 12 FAIL / 6 REVIEW**.

## Before / after (failed benchmark cases)

| Case | Before (`ffae3c96`) | After (`2eb940d` preview) |
| --- | --- | --- |
| FL200-068 | Live snapshot only | Mixed: Rayleigh scattering + current records |
| FL200-069 | Live snapshot only | Mixed: Out of Control definition + status count |
| FL200-072 | Largest record only | Mixed: largest size + “largest ≠ most dangerous” |
| FL200-083 | Live snapshot only | Mixed: fire-weather explanation + Fire of Note |
| FL200-085 | Live snapshot only | Mixed: current records + haiku |
| FL200-013 | General briefing template | Live province snapshot |
| FL200-015 | `0 incident records and 0 perimeter records` (false PASS) | Evacuation count/groups |
| FL200-016 | “No evacuation records were included” | Alert 9 / Order 8 |
| FL200-017 | Preparedness webpage extract | Source-update and retrieval clocks |
| FL200-107 | Quilpituk / EmergencyInfoBC dump / Out of Control def (false PASS) | Quilpituk Creek selected `incident:1261` 3/3 |
| FL200-134 | Evacuation-record dump | Personalized-safety boundary |
| FL200-135 | Invented “Yes—call 9-1-1 immediately” (false PASS) | Reviewed quote-only emergency wording |
| FL200-145–149 | Guidance or evac dump | Typed official handoff |
| FL200-164 | Correct live snapshot, false FAIL | PASS live snapshot |

Full visible answers: `evals/sameday_stabilization/actual_answers.md`.

## Local test results

| Gate | Result |
| --- | --- |
| Ruff / mypy | passed |
| pytest | 2015 passed, 13 skipped, 672 subtests (at first candidate); follow-up owner tests passed after 072 patch |
| ClaimBench v2 | **332/332**, unsafe false-accept 0.0 |
| Hard probe RC2.2 | **91/105**, floor 86 met, same 14 failed IDs |
| Frontend typecheck / vitest / production build | passed (168 vitest) |
| Floors | not weakened |

Hard-probe failed IDs (unchanged):
`F06 F07 F09 F10 H01 H02 H03 I04 I08 K03 K09 L01 L02 L05`.

## Remaining known issues

See `evals/sameday_stabilization/remaining_for_astra.md`.

- FL200-067 still answers only the safety boundary (no nearby live roster).
- FL200-073 composes fires + road-check prose but not a typed DriveBC link.
- FL200-074 history/count/pack triple still collapses to a high-risk redirect.
- FL200-108 answers the second incident but leaves `selected_live_result_id` unbound.

## Intentionally deferred to Astra

Architecture simplification, RAG rewrite, new models/routers/agents, history,
forecasting, document ingestion, major UI, and planner-module split
(`query_plan.py` is a written 650-line exception at 684).

## Preview identity

`/api/v1/health/ready` on
`https://firelens-no9fstydl-yusenrong46-9212s-projects.vercel.app` returned
JSON with `build_commit=2eb940d069b24b2afbe522a464c387a1a42b0d9a` and
`deployment_id=dpl_2u24P51ZWETX8QiRazGVFKgUeU2b`. Bare `/ready` is 404; the
product ready path is `/api/v1/health/ready`.

## Terminal state

`SAMEDAY_STABILIZATION_READY_FOR_DEPLOY_REVIEW`
