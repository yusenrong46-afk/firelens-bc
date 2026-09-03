# Architecture inventory (PASS A, code first)

Commit `b24a73bb`. Built from source and from running the product locally and in
production before reading any architecture document.

## Real request path

```text
browser composer (QuestionComposer)
  -> useFireLensSession.submitQuestionWithContext
       history[-6], location (typed label | browser coords), context{visible_live_result_ids, selected_live_result_id}
  -> POST /api/v1/ask (answer_routes._answer_request)
  -> FireLensAgent.answer (agent/coordinator.py)
       input_seatbelt -> low-substance -> missing antecedent -> resolve_capability (exact string)
       -> _live_place_correction / _answer_mismatch_correction (regex on the turn)
       -> build_agent_query_plan (agent/query_plan.py)  [~20 grammars, 9 location parses]
            -> resolve_location (BC Geocoder) for LOCATION_RADIUS plans
       -> terminal | CAPABILITY -> StaticRAGService | STATIC -> StaticRAGService
       -> run_agent_loop (agent/loop.py)
            prefetch planned tool calls -> execute_tool (agent/runtime_tools.py)
               LIST_OFFICIAL_FIRES/EVACUATIONS -> _fetch_layers (re-derives location!) -> LiveDataService.nearby_page/map_results
               SEARCH_REVIEWED_GUIDANCE -> StaticRAGService.ask
               ANSWER_GENERAL_BACKGROUND -> provider
            live-only: skip model, fallback_write -> compose_official_answer (deterministic)
            otherwise: provider chat_turn -> output_rail_errors -> one rewrite -> fallback
       -> compose_response (agent/compose.py) -> AskResponse
            validators: attach_result_identity (sample_record_ids, provenance_class, presentation_shell)
                        attach_proof_presentation (status_banner, proof_cards)
  -> frontend: ConversationPanel/AnswerBody (answer, StatusBanner, limitations)
       sources: ConversationEvidenceDetails (<details>) -> EvidencePanel (side) -> "Technical binding details"
       map: LiveMap (lazy) inside EvidencePanel or LiveAnalysisWorkspace, driven by presentation_shell
       follow-up state: selectedLiveResultId synced from response; visible ids from current answer only
```

## Semantic ownership graph (who decides what)

| Decision | Modules that decide it independently today |
| --- | --- |
| Intent / route | `answering/intent.py` (`plan_query`), `intent_automaton.py`, `intent_patterns.py`, `intent_conversation.py`, `intent_safety.py`, `intent_refresh.py`, `capability_intent.py`, `request_grammar.py`, `request_facets.py`, `live_request_intent.py`, `live_record_intent.py`, `return_intent.py`, `agent/fallback_brain.py`, `agent/query_plan.py`, `agent/query_plan_boundaries.py`, `agent/rails.py` (`input_seatbelt`), `guidance_capabilities.py` (exact match) |
| Clause boundaries | `intent_automaton.py` (typed clauses), `intent.py` (`has_independent_supported_live_clause`, `unsupported_live_topics`), `fallback_brain.planned_static_subrequest` |
| Live / static / mixed | `query_plan.plan_agent_request`, `coordinator.answer` (4 early exits), `intent.plan_query`, `live_answering.LiveAnswerCoordinator.is_*` |
| Location | `location_intent.py` (+ `location_intent_patterns.py`), called from 12 modules / 28 sites; `live_named_fire.py` can veto it; `runtime_tools._fetch_layers` re-derives it; `live_support.official_fire_centre_from_question`; `query_plan_boundaries` prompts |
| Temporal scope | `intent_automaton.py` (`TemporalScope`), `intent_refresh.py`, `intent.py` history checks |
| Selected record | `query_plan._visible_ordinal_result_id`, `live_request_intent.uses_selected_live_binding/requires_selected_live_record`, `intent_conversation.is_selected_record_followup`, `live_selection.selected_live_result_id` (closest / prose-name / prior anchor), `compose.request_with_selected`, frontend `askContinuation.selectedResultIdForQuestion` |
| Safety | `agent/rails.input_seatbelt` (terminal), `intent_safety.py`, `query_plan_boundaries.*` (7 terminal boundaries), `rails.output_rail_errors`, `compose.safety_response`, `live_analysis` empty-map inference, `firelens200_grader` (eval) |
| Unsupported domains | `intent.unsupported_live_topics`, `query_plan` topics handling, `live_handoffs` |
| Source authority | `guidance_capabilities` bindings, `publication/*` (typed claims, quote-only), `claim_trust.py`, `proof_presentation.py`, `presentation_identity.derive_provenance_class` |
| RAG query | `intent.reviewed_guidance_plan`, `request_facets.contents_request_facet`, `static_guidance_subject`, `capability_execution.capability_query_plan`, provider planning (`provider.plan`) |
| Publication mode | `answering/service.py`, `grounded.py` (`packet_requires_structured`), `compiler.py`, `fallback.py`, `compose.py` |
| Presentation mode | backend `presentation_identity.presentation_shell`; frontend `workspacePresentation.ts`, `App.tsx` (map/context state), `ConversationPresentation.revealAssistantMessage` (scroll correction) |

Fourteen modules can interpret the question; six can decide the location; the
selected record is resolved in five places (plus the frontend).

## Frontend

- Single page, no router. `view.kind` (idle/loading/answer/…) is the only "route".
- Brand link is `href="#top"` — not a Home action. Reset only via toolbar "New conversation"/"Clear".
- Desktop ≥1120 px: fixed-height grid (`calc(100dvh - 132px)`, `overflow: hidden`) with nested scrollers; mobile: document flow. 15 media queries across 3 CSS files; 141 selectors defined more than once; JS scroll correction in two places.
- Evidence is progressive disclosure three levels deep; `supported_items` excludes quote-only claims.
- Lazy chunks: `LiveMap`, `AnalysisCharts` (392 KB — recharts). Entry JS 524 KB.
- Eager on idle: `/api/v1/health/ready`, `/api/v1/live/summary`.

## Live data

- Layers: BCWS ActiveFires, BCWS FirePerimeters, EmergencyInfoBC Evacuation Orders/Alerts (ArcGIS FeatureServer).
- Geocoder: BC Address Geocoder, exact locality match, score ≥ 60; plus a small region gazetteer.
- Record identity: `kind:OBJECTID` (unstable across source rebuilds; observed). Stable keys available: `FIRE_NUMBER`, `EMRG_OAA_SYSID`.
- Distances: geodesic from resolved point to record geometry; deterministic; never model-written.

## RAG

- 179 chunks, BM25 + `text-embedding-3-small` + RRF + `cohere/rerank-4-pro` (top 5); evidence packet ≤ 5 spans; support decision by token overlap ≥ 0.4.
- High-risk (Tier A/B) questions: zero generation; typed claims (26 reviewed) or exact quote-only publication.
- Capability registry: exact string match on canonical questions/paraphrases → bound chunk + exact quotes (zero provider calls).

## Deployment

- Vercel FastAPI service; build hook `[tool.vercel.scripts] build = python scripts/prepare_vercel_build.py` (npm ci + vite build + runtime candidate + copy to `public/`).
- Only output: one Python lambda (79 MB). Static assets served by the lambda; no CDN caching; `no-store` HTML; `max-age=0` assets; entry-file compatibility route.
- Deployed via `scripts/deploy_vercel.py` (clean tree, exact SHA, pinned CLI 58.1.0).

## Evaluation

- pytest 2017 passed / 13 skipped (34 s); vitest 168; Playwright e2e against mocked API; e2e-real against fixture backend.
- ClaimBench v2 332/332 (offline); hard probe 91/105 with `rc2.2` profile (82/105 historical profile) — offline FakeProvider.
- FireLens-200: 200 cases, run against a deployed preview with the paid provider (≈320 calls).
- No test asks the product a natural question in a browser against the real backend and checks the *user-visible* result (source visible, Kelowna understood, Home works). That is the gap the Product Reality Gate fills.
