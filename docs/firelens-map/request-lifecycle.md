# Public Ask request lifecycle

Source digest: `9aa28d967f53827d4f5a55d02a286e1d9517d44be0c6f0206ca5e29c5a9cac3c`. This is a navigation trace, not executed evidence.

1. `api/answer_routes.py` applies readiness and deadline boundaries.
2. `agent/coordinator.py` builds the immutable `AgentQueryPlan`.
3. `agent/prefetch.py` executes plan-authorized work through `live.py`'s `LiveDataService` and `answering/service.py`'s `StaticRAGService`.
4. `agent/loop.py` skips provider prose for application-owned responses; otherwise it permits bounded
   writing, one repair, then deterministic fallback.
5. `publication/compiler.py` and `compiled_validation.py` own publishable structured facts.
6. `agent/compose.py` creates `AskResponse`; `proof_presentation.py` binds proof projections.
7. The web client renders the response and must fail closed rather than strengthen authority.

| Trigger | Result |
| --- | --- |
| Runtime absent or deadline exceeded | Typed HTTP 503 |
| Provider unavailable | Deterministic response or official-source handoff |
| Retrieval incomplete | Typed unavailable; retained candidates are not complete support |
| Generated draft rejected | One repair, safe salvage, exact-source compiler, or abstention |
| Live records empty/unavailable | Explicit limitation; never an all-clear |
| Proof authority missing/mismatched | Unknown/rejected presentation |
