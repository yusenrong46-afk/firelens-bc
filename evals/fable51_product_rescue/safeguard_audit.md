# Safeguard audit

Classes: A real authority/safety invariant · B schema/type/input validation ·
C semantic heuristic · D duplicated defense · E benchmark-specific patch ·
F fallback compensating for another broken abstraction · G obsolete/dead.

Decisions: KEEP · SIMPLIFY · MERGE · MOVE TO TRUST BOUNDARY · REPLACE · DELETE.

| Safeguard / guard family | Where | What it actually protects (proved how) | Class | Decision |
| --- | --- | --- | --- | --- |
| Unavailable layer ≠ zero result | `live.py::_map_layer_results`, `compose.py::_packet_live_answer`, `live_response_support.empty_live_response` | Reading + fixture tests: an unavailable layer produces "could not establish current conditions… not an all-clear", never an empty roster | A | KEEP |
| Empty roster ≠ safe | `live_response_support`, `intent_safety.is_empty_map_safety_inference`, `firelens200_grader` hard-fail regex | Tests `test_empty_live_safety`; reproduced text "This does not mean the area is safe" | A | KEEP |
| No personalized safety decision | `intent.plan_query` PROHIBITED → `rails.input_seatbelt`; `output_rail_errors` `_FORBIDDEN`; `compose.safety_response` | Reproduced: "should I evacuate" → abstention; model text with "you are safe" vetoed | A | **MOVE TO TRUST BOUNDARY**: the decision stays blocked, but as a clause outcome so the official-records clause is still answered; seatbelt stays terminal for medical / injection / prohibited-only |
| Exact tool-call authorization (`AgentQueryPlan.authorizes`) + duplicate-dispatch fingerprint | `query_plan.py`, `loop.py`, `runtime_tools.py` | Provider tool requests outside the plan are rejected (tests `test_agent_query_plan`, `test_luna_brain_agent`) | A | KEEP |
| Deterministic live prose (model skipped for live-only) | `loop_support.skip_owned_model_write`, `fallback_write` | Live text is composed from fetched records; no provider call for live-only (confirmed: 0 provider calls in local traces) | A | KEEP |
| Invented kilometre / fire name / feed / flame-front / civic address vetoes | `rails.output_rail_errors` | Regex vetoes on model prose against packet facts | A (km, names, feeds, freshness) / C (civic address) | KEEP; the C part is harmless |
| Publication-state / secret / allowlist-bypass phrase vetoes | `rails.output_rail_errors` | Only fire on adversarial prompt-injection phrases from the hard probe | E | SIMPLIFY into one "instruction-following" veto family; keep behaviour |
| Typed claim mutation check | `typed_compare.typed_preservation_errors` | Model cannot alter quoted reviewed wording | A | KEEP |
| Exact-quote containment / chunk identity / typed inventory hashes | `publication/*`, `guidance_capabilities` load validation | Quotes must exist in admitted chunks; typed claims must be production-supported | A | KEEP |
| Tier A/B zero-generation | `grounded.packet_requires_structured` | High-risk answers are typed or quote-only | A | KEEP |
| Support decision by token overlap ≥ 0.4 | `context_support.decide_support` | Heuristic evidence floor | C | KEEP (measured: not the failing layer) |
| Capability exact string match | `guidance_capabilities.resolve_capability` | Routes a question to bound sources | C used as A | **REPLACE**: intent-based matching; exact binding kept |
| Place reject-lists (`_REJECTED_PLACES`, `_NON_PLACE_ANALYSIS_WORDS`, `PLACE_STOPWORDS` for places, `_GENERIC_LOCATED_NAMES`) | `location_intent.py`, `intent_spans.py`, `live_named_fire.py` | Compensate for greedy captures | F | **DELETE** with the structural extractor |
| Two location extractors (`coarse_location_from_question`, `intent_spans.location_candidate`) | — | Same job twice | D | **MERGE** into one |
| Location re-derivation in tools | `runtime_tools._fetch_layers` | Compensates for plans that lost the place | F | **DELETE** |
| Named-fire/place collision check | `query_plan.plan_agent_request` | Attempts to reconcile two extractors | F | **DELETE** (root cause fixed) |
| Finance metaphor, absence all-clear, ignore-alert, travel/fuel, smoke observation, vague local concern, unbound record reference terminals | `query_plan.py`, `query_plan_boundaries.py` | Each blocks one adversarial or ambiguous pattern; several are hard-probe cases | A (absence all-clear, ignore-alert, travel/fuel decision) / E (finance metaphor, unbound reference) / C (smoke, vague concern) | KEEP the A group as boundary outcomes; SIMPLIFY the rest into understanding flags where they still fire; delete any that no longer fire under the new extractor |
| `_live_place_correction`, `_answer_mismatch_correction` | `coordinator.py` | "Actually, Vernon" repairs | C | KEEP (small, user-serving) |
| `is_low_substance_question`, `missing_source_antecedent` | `input_clarity.py` | Empty/one-word input handling; "which source?" without antecedent | B / C | KEEP |
| Entry-asset compatibility route | `api/frontend.py` | Serves the current entry JS under an old hash name | F | **DELETE**; replaced by immutable caching + chunk-load recovery + integrity check |
| Security headers / `no-store` HTML | `api/middleware.py` | CSP, HSTS, no HTML caching | B | KEEP; add immutable caching for hashed assets |
| Anonymous request guard / body bounds | `api/middleware.py` | Rate and size limits | B | KEEP |
| Trace/telemetry content minimization | `errors.py`, `logging`, config validation rejecting `FIRELENS_TRACE_CONTENT` in preview/prod | Privacy invariant; tested | A | KEEP |
| Frontend semantic-owner guard test | `apps/web/tests/frontendSemanticOwner.test.ts` | Frontend must not classify questions | A (architecture) | KEEP |
| `presentation_shell` backend switching (chat/analysis/spatial) | `presentation_identity.py`, `workspacePresentation.ts` | Layout modes | C | SIMPLIFY (map/records as sections; charts for many-record answers) |
| Hard-probe expectation profiles rc2/rc2.1/rc2.2 | `hard_probe_expectations.py` | Migrated expectations | E (evaluation) | KEEP as-is; do not migrate more |
| `savedScopes` localStorage | `apps/web/src/features/ask/savedScopes.ts` | Nothing (no callers) | G | **DELETE** |
| `request_grammar.py` projection | — | Nothing unique | G | **DELETE** after callers move |
