# 09 — Safety and Authority

FireLens uses broad interpretation and narrow authority: it tries to understand a useful task, then permits only the smallest deterministic capability that the product contract supports.

## Authority layers

| Decision | Owner | Model role |
| --- | --- | --- |
| Prohibited/personalized request boundary | [`agent/rails.py`](../../src/firelens/agent/rails.py), [`agent/coordinator.py`](../../src/firelens/agent/coordinator.py) | None before terminal response |
| Tool, layer, geography, record, static subrequest | [`agent/query_plan.py`](../../src/firelens/agent/query_plan.py) | Cannot widen; later tool proposals must match exactly |
| Official live values and derivations | [`live.py`](../../src/firelens/live.py), [`live_contracts.py`](../../src/firelens/live_contracts.py) | May explain only after binding |
| Reviewed high-risk wording | [`publication/`](../../src/firelens/publication/) and human-reviewed inventory | Cannot author supported Tier A/B facts |
| Public response validity | [`contracts.py`](../../src/firelens/contracts.py), [`publication_response_binding.py`](../../src/firelens/publication_response_binding.py) | Draft is rejected if it violates the contract |

## Safety behavior

Personal evacuation, route, return, stay, and medical decisions terminate with a bounded refusal plus official handoff where applicable. Empty or unavailable live results never justify “safe,” “all clear,” or “nothing to worry about.” Unsupported live topics are separated from supported clauses so a useful official answer can remain partial without silently dropping the limitation.

Prompt injection is handled twice: the input seatbelt can terminate policy-manipulation requests, and exact plan authorization prevents a later model tool request from acquiring new authority. Output rails and response validation provide defense in depth.

## Invariants and tests

Inputs are questions/history/context; outputs are terminal safety responses or a restricted plan. Important failure modes are false all-clear inference, unsafe personalized advice, scope expansion, dropped mixed clause, source-lane strengthening, and stale-as-current language. Coverage includes `test_empty_live_safety.py`, `test_intent_capability_bypass.py`, `test_productbench_scope_safety.py`, `test_mixed_clause_outcomes.py`, `test_support_polarity_guard.py`, and hard-probe safety families.

No automated suite substitutes for independent safety review, real upstream faults, and human product judgment. Those current gates are **BLOCKED**.

