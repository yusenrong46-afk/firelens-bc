# Remaining for Astra

Same-day stabilization did not redesign FireLens. These items are recorded, not
fixed today.

## Product

- Historical comparison (`refresh … whether anything changed`, last week, next
  week) remains unsupported. The planner now keeps refresh as one live
  operation instead of inventing a static half.
- Conversation replay in FireLens-200 still sends prior Ask turns as text
  history. The product can now recover a selected record from that text, but
  the public API still has no first-class `selected_live_result_id` handoff
  between HTTP turns.
- Mixed composition still depends on the static service returning accepted
  BACKGROUND or GROUNDED claims. If general-background generation is rejected,
  the live half plus a “non-live clause was not established” limitation is
  published as LIVE, not as a MIXED uncertainty section (AskResponse contract
  requires claims or an official handoff for MIXED).
- Typed handoffs for reception centres, outages, park closures, insurance, and
  live weather are link/boundary quality only. No new live integrations.
- `query_plan.py` is now a written 650-line exception (684). Astra should
  split planner helpers without changing the immutable plan contract.
- Hard-probe RC2.2 remains 91/105 with the same 14 failed IDs as the 1.6.4
  exposure candidate. Do not weaken the floor to hide them.

## Evaluation

- FireLens-200 still uses a lightweight rubric after deterministic hard
  checks. REVIEW verdicts can remain for borderline completeness.
- Fault-injection catalog fixtures (`no_preview_fault_injection_mode`) are
  still NOT_RUN on preview.
- The full 320-call FireLens-200 campaign was not rerun today. Only the
  focused owner set is evidence for this SHA.
- Previous exposure Gate B–H preview rows were unbound (`F164-E-001`) and
  were not repaired here.

## Explicitly out of scope today

Architecture simplification, RAG rewrite, new models/routers/agents,
history, forecasting, document ingestion, and major UI changes.
