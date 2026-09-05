# 05 — Understanding and Planning

## Contract

| Field | Description |
| --- | --- |
| Owner | [`answering/intent_automaton.py`](../../src/firelens/answering/intent_automaton.py) for typed request structure; [`understanding/place.py`](../../src/firelens/understanding/place.py) for the sole place extractor; [`answering/location_intent.py`](../../src/firelens/answering/location_intent.py) for compatibility projection; [`agent/query_plan.py`](../../src/firelens/agent/query_plan.py) for executable authority |
| Input | Normalized `QueryRequest`, bounded history, location, selected/visible map record IDs |
| Output | Frozen `AgentQueryPlan`: route, mode, live layers, geography, bound location, exact static subrequest, exact tool calls, boundaries, or terminal response |
| Invariant | Interpretation and authority are separate. A recognized intent cannot execute anything until the deterministic plan permits an exact call. |
| Failure modes | Conflicting phrase grammars; incorrect clause split; wrong temporal scope; ambiguous place; stale selected ID; model/fallback re-planning |
| Observability | Public event records route and tool names, but not the parsed facets or first-divergence decision. Local traces store bounded categorical planning fields. |
| Tests | `test_typed_intent_automaton.py`, `test_request_grammar.py`, `test_request_facets.py`, `test_agent_query_plan.py`, `test_agent_query_plan_boundary.py`, `test_multiple_fire_centres.py` |
| Evaluation | Hard-probe routing, source-aware conversation, golden traces, location/trajectory mutations |

## Plan modes

- `static`: one exact reviewed/general subrequest.
- `live`: one or more explicit official layers with province-wide or bounded-location geography.
- `mixed`: official layers plus one exact static subrequest.
- `selected`: one exact record ID from bounded context.
- `terminal`: application-owned response for capability, clarification, redirect, prohibition, or another completed boundary.

`PlannedToolCall.matches()` compares the tool name and normalized argument map exactly. [`runtime_tools.execute_tool()`](../../src/firelens/agent/runtime_tools.py) also rejects duplicates and exhausts a per-request call budget. This makes prompt injection unable to add an evacuation layer, switch geography, or substitute a different record.

## Place and record binding

Coarse location may arrive explicitly in `QueryRequest.location`, be recognized
from text, or be resolved through the official BC geocoder during live
execution. The candidate uses explicit response-control grammar so directives
such as output-format preambles are not place authority, binds same-turn
personal location declarations, and recognizes fronted multiword/numeric B.C.
communities through one shared vocabulary contract. Exact addresses are
rejected and coordinates are rounded to two decimals. Selected-record
follow-ups bind through `MapContext.selected_live_result_id`; visible IDs
provide bounded UI context but do not authorize an arbitrary record lookup.

## First-divergence risks

The typed automaton is described as the request-shape owner, but clause, route, location, live-layer, named-fire, and fallback helpers still inspect text in several modules. [`agent/fallback_brain.py`](../../src/firelens/agent/fallback_brain.py) also derives static tool intent even though the plan is meant to be immutable. These are compatibility paths, not independent authorities. New behavior should enter the typed projection or the plan, and tests should reject divergence across paraphrases rather than add downstream phrase patches.
