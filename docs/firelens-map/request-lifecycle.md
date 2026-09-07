# Public Ask request lifecycle

Source digest: `38a45545a031f2d2d84d70419c6f0407f60ea20dc00c29de98041108b29b0cf3`. This is a navigation trace, not executed evidence.

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
