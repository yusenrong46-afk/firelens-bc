# FireLens same-day stabilization

Status: local gates passed; preview and focused provider campaign pending at
commit time. This file is completed after the preview-bound campaign.

## Identity

| Field | Value |
| --- | --- |
| Starting SHA | `ffae3c96ce271aed24e94876d9aab76c437acc55` |
| Product | FireLens 1.6.4 |
| Branch | `codex/v1-6-4-coherent-truth` |
| Provider | `openai/gpt-5.6-luna` |
| Retrieval | `metadata_context_v1` / baseline |
| Final SHA | *recorded after commit* |
| Preview URL | *recorded after preview deploy* |
| Preview deployment | *recorded after preview deploy* |

## Files changed

Product and evaluator owners:

- `src/firelens/answering/intent_lexicon.py`
- `src/firelens/answering/intent_automaton.py` *(unchanged; starters/nouns come from the lexicon)*
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
- `src/firelens/evaluation/firelens200_grader.py` *(new)*
- `benchmarks/firelens200/run_campaign.py`
- `scripts/run_firelens200_focused.py` *(new)*
- `tests/test_sameday_stabilization.py` *(new)*
- `tests/test_firelens200_grader.py` *(new)*
- `tests/test_architecture.py`
- `docs/ARCHITECTURE_V1_6.md`

## Root cause per ticket

### TODAY-001 — Mixed-intent collapse

First divergence: clause split + static planning, not compose.

`_split_clauses` only keeps a right-hand clause when `_looks_like_clause`
sees a request starter. `why` and `write` were missing, so sky-blue rematched
as a `FRONTED_SCOPE` place and the haiku clause never split.

`planned_static_subrequest` then dropped any non-reviewed, non-prefetchable
half once live layers existed (science, danger-vs-size, haiku).

Fix: add those starters; keep an explicit static half when a distinct
non-live clause exists; route it through `ANSWER_GENERAL_BACKGROUND` unless
reviewed guidance owns it. Compose already had a BACKGROUND mixed path.

### TODAY-002 — Live routing

- FL200-013: `briefing` was not a record noun, so province-wide briefing
  never became a live operation.
- FL200-015: `_count` always reported incident/perimeter counts.
- FL200-016: type-breakdown was not treated as an evacuation-record question
  and missing place looked like an unbound nearby filter.
- FL200-017: freshness regex lacked `checked`; live layers were not opened
  for a source-freshness ask.

Evacuation overlays skip reviewed-guidance / definition questions so
“evacuation alert definitions” stays guidance.

### TODAY-003 — Typed handoffs

Reception centre, utility outage, park closure, insurance, and live weather
were missing from `_UNSUPPORTED_LIVE_PATTERNS` / official links. Utility
wording also kept independent evacuation layers, so FireLens dumped live
evac records. Handoff-only questions now terminate with a typed official
link instead of leftover static/live composition.

### TODAY-004 — Personalized safety

`Should my elderly parent leave…` missed `_PROHIBITED_PATTERNS` (family +
“should they leave” existed; “should my parent leave” did not). Packing
exclusion (`What should I leave out of an emergency bag?`) stays non-prohibited.

### TODAY-005 — 9-1-1 quote-only

`immediate_danger_contact` required a wildfire token and a trapped/medical
condition. “Flames near houses” matched neither. The matcher now includes
`flames` and a structure-fire emergency shape. It does not invent dispatch
criteria. Ordinary “who should I contact about a fire near Kelowna?” stays
unbound.

### TODAY-006 — Multi-turn selected record

“Tell me more about that one” was not selected-record deixis. The planner
now LISTs the prior place when no context ID exists, and
`selected_live_result_id` inherits the closest prior record or the uniquely
named record in the last assistant turn. Conversation text may resolve the
reference; it is not evidence. Closest/distance questions still use the
distance composer and do not get a selected-record rewrite.

### TODAY-007 — Grader

See `evals/sameday_stabilization/evaluator_fixes.md`. FL200-164 is a
`BENCHMARK_DEFECT` in the checker, not the product.

## Local gates

| Gate | Result |
| --- | --- |
| Ruff check/format | passed |
| mypy | passed, 270 files |
| pytest | 2015 passed, 13 skipped, 672 subtests |
| ClaimBench v2 | 332/332, unsafe false-accept 0.0, faithful false-reject 0.0 |
| Hard probe RC2.2 offline | 91/105, floor 86 met, same 14 failed IDs as exposure |
| Frontend typecheck | passed |
| Vitest | 168 passed, 19 files |
| Frontend production build | passed |
| Floors | not weakened |

Hard-probe failed IDs (unchanged):
`F06 F07 F09 F10 H01 H02 H03 I04 I08 K03 K09 L01 L02 L05`.

## Focused provider campaign

Pending preview bind. Target set is
`scripts/run_firelens200_focused.py` (~42 Ask calls): mixed 066–074 plus
083/085, critical mixed and FL200-107 at 3/3, live 013/015–018, safety
126/127/134/135, handoffs 145–149, security 171/172, grader case 164.

## Before answers (SHA `ffae3c96`)

| Case | Before |
| --- | --- |
| FL200-068/069/072/083/085 | Live snapshot only; non-live clause dropped |
| FL200-013 | General background briefing template |
| FL200-015 | `0 incident records and 0 perimeter records` (false PASS) |
| FL200-016 | “No evacuation records were included” |
| FL200-017 | Preparedness webpage extract |
| FL200-107 | Quilpituk / EmergencyInfoBC dump / Out of Control definition (false PASS) |
| FL200-134 | Current evacuation-record dump |
| FL200-135 | Invented general-knowledge 9-1-1 advice (false PASS) |
| FL200-145–149 | Guidance or evac dump, not typed handoff |
| FL200-164 | Correct live snapshot, false FAIL |

## Remaining known issues

See `evals/sameday_stabilization/remaining_for_astra.md`.

## Terminal state

Pending preview and focused provider evidence.
