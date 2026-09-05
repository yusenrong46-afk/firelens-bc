# 10 — Conversation and State

FireLens conversation state is bounded request context, not server-side long-term memory.

## State contract

| State | Owner | Bound |
| --- | --- | --- |
| User/assistant history | [`contracts.py`](../../src/firelens/contracts.py) `ConversationTurn`, `QueryRequest` | At most six normalized turns; each turn ≤6,000 characters |
| Coarse location | [`live_contracts.py`](../../src/firelens/live_contracts.py) `LocationInput` | Community label or rounded coordinate pair, never both; radius 1–200 km |
| Map context | [`contracts.py`](../../src/firelens/contracts.py) `MapContext` | One selected result, up to 100 unique visible result IDs, optional viewport |
| Resumable prompt | `RequiredInput` | Kind, prompt, and exact continuation question |
| Browser session | [`useFireLensSession.ts`](../../apps/web/src/features/ask/useFireLensSession.ts) | In-memory history/location/roster/selection; most recent six turns sent |
| Assistant continuation text | `AskResponse.history_text` | Backend-owned authority-labelled summary for later turns |

The client aborts a superseded active request and also checks request ownership
before publishing either success or failure. A transport that ignores abort
cannot restore an old answer. A generation counter invalidates pending browser
geolocation on a new submission, reset, or unmount. “Clear conversation” removes
the draft, history, location, selected record, roster and optional map layers;
Home returns focus to the composer. No durable user profile is implemented.

Mixed personal-safety clauses remain explicit even when the records task first
needs a location. The outer safety guard delegates those mixed requests to the
same plan/boundary composer; it does not drop the live task or authorize a
personal property-threat assessment as general background.

## Follow-ups

The backend recognizes bounded place corrections, explicit answer-mismatch corrections, selected-record references, ordinal references over the visible roster, source antecedents, and live refresh intent. Correction logic can reconstruct the previous task but must not add a new layer or authority absent from the current plan.

`history_text` is important: it carries a deterministic authority prefix rather than blindly feeding the full prior answer back as model-authored truth. Selected live identity is also carried as a typed ID, not inferred only from prose.

For significance follow-ups, an explicit current subject constrains the rationale;
only a bare reference resolves the previous user topic. A restricted user
antecedent retains the existing personal-decision prohibition. Assistant wording
cannot authorize a decision. The current question remains distinct from its
retrieval query. A selected personal-distance request carries its selected ID
through the missing-origin prompt and resumes the deterministic calculation.

## Failure modes and evidence

Risks include stale client selection, a roster order different from the answer, ambiguous pronouns, history truncation removing an antecedent, location correction attaching to the wrong task, or prior general background being upgraded to reviewed/current authority. Tests include `test_source_aware_conversation.py`, `test_v1_6_golden_traces.py`, `test_live_answering.py`, `test_agent_query_plan_boundary.py`, and client session/continuation tests. The clean local EvalLab core run passed the 106-case source-aware catalog, but it is development-unsealed and uses fake/local dependencies; see [Evaluation catalog](appendices/evaluation-catalog.md).
