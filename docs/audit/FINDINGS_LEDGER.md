# FireLens BC V1.5 audit findings ledger

Updated: 2026-07-30 (America/Vancouver)

This file is the durable source of truth for the zero-cost audit-remediation loop. Status changes
must follow `OPEN -> TEST_WRITTEN -> FIXED -> VERIFIED`, except a finding that reaches the defined
three-attempt hard stop may become `BLOCKED` with a root-cause report.

Deduplication: CF-003 is covered by GP-001; CF-005 is GP-004; CF-006 is GP-005; CF-007 is covered
by GP-008. They are not duplicated as independent rows.

| ID | Severity | Status | Repro test path | Fix commit | Notes |
|---|---|---|---|---|---|
| GP-001 | P0 | VERIFIED | `tests/test_static_rag.py::ContractTests::test_validator_rejects_safety_action_inversion`; `test_validator_rejects_unsupported_quantity_and_duration`; `test_validator_rejects_protected_semantic_mutations` | `bfac0b5`, `be3cb4e`, `d68006d` | Added fail-closed authority-alias and explicit-location preservation using quote plus immutable local source context. Focused regressions, the 92-test fast gate, and full zero-cost verification pass. |
| GP-002 | P1 | VERIFIED | `tests/test_repairs.py::RepairProvenanceContractTests::test_human_repair_provenance_reaches_public_evidence`; `prototype/firelens-rag-ui/tests/App.test.tsx` | `73d811b`, `2987bd5`, `0742cb0` | Public evidence preserves typed repair provenance and the source detail discloses a human-verified transcription. Focused, fast, full, generated-contract, UI, and browser gates pass. |
| GP-003 | P1 | VERIFIED | `tests/test_live_answering.py::LiveAnswerCoordinatorTests::test_stale_records_are_never_described_as_current`; `test_mixed_freshness_has_typed_state_and_no_current_wording`; `prototype/firelens-rag-ui/tests/e2e/app.spec.ts` | `2577462`, `5555396` | API responses carry validated aggregate freshness. Answer copy, limitations, badge, map heading, ARIA warning, rows, nearby filtering, and mixed freshness agree. Focused, fast, full, UI, build, and browser gates pass. |
| GP-004 | P1 | BLOCKED | `tests/test_request_guard.py::RequestGuardTests::test_untrusted_forwarding_headers_cannot_rotate_identity`; `test_vercel_identity_uses_only_the_platform_owned_header`; `tests/test_release_operations.py::test_firewall_plan_is_enforced_method_scoped_and_not_auto_published`; `test_firewall_plan_rejects_log_only_rules` | `b3e202a`, `39c5d7c` | Repository scope is verified: trusted identity, enforced deny plan, no auto-publish, fast and full gates pass. External cross-instance enforcement cannot be verified without an owner-authorized preview and firewall publication, both forbidden in this zero-network loop. Recovery: authorize a preview, publish the rendered rules, and run the two-instance quota probe. |
| GP-005 | P1 | VERIFIED | `tests/test_provider_api.py::ApiTests::test_chunked_oversized_body_stops_consuming_after_limit`; `test_misleading_declared_length_cannot_bypass_streaming_cap`; `test_concurrent_oversized_bodies_are_independently_bounded` | `b3e202a`, `7f633b1` | Streaming enforcement passes measured missing/misleading-length and eight-request concurrency coverage, stopping at the first rejecting frame without consuming a third frame. Fast and full zero-cost gates pass. |
| CF-001 | P1 | VERIFIED | `tests/test_live.py::LiveDataServiceTests::test_nearby_results_keep_records_with_unknown_geometry`; `tests/test_live_answering.py::LiveAnswerCoordinatorTests::test_unknown_geometry_is_disclosed_without_hiding_record` | `2577462` | Malformed/unknown geometry remains visible with an explicit limitation instead of becoming a false no-result. |
| CF-002 | P1 | VERIFIED | `tests/test_v1_5_rag.py::V15RoutingTests::test_long_preamble_cannot_hide_a_personal_safety_request` | `bfac0b5` | Safety classification uses the full raw question; focused text remains retrieval-only. |
| GP-006 | P1 | VERIFIED | `tests/test_conflict_handling.py::ConflictHandlingTests::test_authority_precedence_matrix_surfaces_material_differences`; `test_date_and_jurisdiction_differences_surface_without_precedence`; `test_different_non_prescriptive_passages_do_not_invent_conflict` | `1a47099`, `7381037` | The explicit matrix passes for same authority, provincial/public-health, provincial/FireSmart, provincial/local, version/date, jurisdiction, and complementary guidance. No automatic precedence hides a material difference. Fast and full gates pass. |
| GP-007 | P1 | VERIFIED | `tests/test_provider_api.py::ApiTests::test_public_deadline_cancels_every_provider_stage`; `test_caller_cancellation_reaches_active_provider_stage`; `test_public_deadline_cancels_slow_live_work`; `test_public_deadline_cancels_slow_live_map_work` | `1a47099`, `6ad68aa`, `d4f6ddf` | Planner, embedding, reranking, generation, repair, live ask, and live map all receive deadline cancellation; direct caller cancellation also reaches the active provider coroutine. Active-operation bookkeeping is tracked separately as CF-010. Fast and full gates pass. |
| GP-008 | P2 | VERIFIED | `tests/test_live.py::LiveDataServiceTests::test_record_ceiling_fails_closed_and_is_visible`; `test_bbox_is_sent_to_arcgis_and_retained_as_local_backstop`; `test_layer_definition_can_be_injected_without_code_path_duplication`; `test_repeated_full_page_fails_closed_instead_of_looping` | `2577462`, `9dc82d6` | Typed injectable layer definitions own URL/identity/schema. Pagination has page/record/dedup/repeat/progress bounds; ArcGIS receives bbox envelopes, bbox-keyed caches stay isolated, and local valid-geometry filtering remains a backstop without hiding malformed records. Fast and full gates pass. |
| GP-009 | P2 | VERIFIED | `tests/test_v1_5_rag.py::V15RoutingTests::test_evidence_cut_preserves_required_aspect_and_source_diversity` | `deb490b` | Before the bounded evidence cut, deterministic selection reserves directly matched aspect slots, then relevant unseen-source slots, then fills in reranker order. Both reservations require at least 40% normalized overlap, preventing one-token promotion. Focused, broader RAG, fast, and full gates pass. |
| GP-010 | P2 | VERIFIED | `tests/test_reliability.py::ContractPropertyTests::test_every_response_mode_has_server_bounded_assistant_history`; `prototype/firelens-rag-ui/tests/App.test.tsx::uses the server-bounded assistant history representation` | `a0a4b4f` | Every response with a public answer receives a deterministic, normalized assistant-history representation capped at 6,000 characters. The response contract rejects spoofed history, the UI uses the bounded representation for follow-up context, and the full visible answer remains unchanged. Fast and full gates pass. |
| CF-004 | P2 | VERIFIED | `tests/test_security_operations.py::SecurityOperationTests::test_production_never_registers_debug_routes` | `b3e202a` | Production environment prevents debug-route registration even when the debug flag is true. |
| CF-008 | P2 | VERIFIED | `tests/test_static_rag.py::ServiceTests::test_valid_claims_are_salvaged_without_weakening_validation` | `bd66d4b` | Deterministic salvage still exposes only independently validated claims. Every salvage response now reports the exact omitted-item count and explicitly warns that the remainder is not a complete list. Fast and full gates pass. |
| CF-009 | P3 | VERIFIED | `tests/test_static_rag.py::ServiceTests::test_single_shared_source_token_does_not_promote_tangent_query`; `test_explicit_source_reference_overrides_adjacent_planner_result` | `e21a180` | A single shared source-title token can no longer override a tangent planner decision or trigger embedding/reranking. Explicit source references require at least two distinctive matching tokens; the existing multi-token source-reference path remains covered. Fast and full gates pass. |
| CF-010 | P3 | VERIFIED | `tests/test_static_rag.py::ServiceTests::test_active_operations_clear_after_success_and_provider_failure`; `test_active_operations_clear_after_unexpected_exception`; `test_active_operations_clear_after_timeout`; `test_active_operations_clear_after_caller_cancellation` | `026bbaa` | The public ask boundary owns cleanup in a `finally`, covering search, generation, recording, normal returns, typed provider failure, unexpected exceptions, timeout, and direct cancellation. The lifecycle matrix, fast gate, and full gate pass. |
| CF-011 | P3 | VERIFIED | `tests/test_security_operations.py::SecurityAndOperationsTests::test_security_headers_and_production_debug_boundary`; production build; desktop/mobile map Playwright flows | `4eb1f64` | API responses now use `style-src 'self'` with no `unsafe-inline`. The handbook accurately scopes the policy to API responses. Production UI build, Sites packaging, and all 18 desktop/mobile browser tests—including live map, tile failure, and stale/partial states—pass. |

## Iteration log

- 2026-07-30: Ledger created from the deduplicated audit input. Existing commits were credited
  only where a pinned test and observed pre-fix failure were already available. All partially
  covered findings remain OPEN until their full stated scope is proven.
- 2026-07-30: GP-001 reopened during the completion audit; authority and location mutation
  regressions were added before implementation.
- 2026-07-30: GP-001 focused regressions and the complete fast gate pass after the authority and
  location preservation fix; status advanced to FIXED pending the global zero-cost gate.
- 2026-07-30: GP-001 global verification passed at `d68006d`; status advanced to VERIFIED.
- 2026-07-30: GP-002 fail-first backend regression reproduced missing public repair provenance;
  the paired UI regression cannot pass until the generated contract exposes the field.
- 2026-07-30: GP-002 focused backend and UI regressions pass with the generated public contract;
  status advanced to FIXED pending the global zero-cost gate.
- 2026-07-30: GP-002 global verification passed at `0742cb0`; status advanced to VERIFIED.
- 2026-07-30: GP-003 completion regressions were added for all-stale and mixed-freshness API
  responses plus badge and screen-reader warning order.
- 2026-07-30: GP-003 focused backend, UI, and desktop/mobile browser regressions pass;
  status advanced to FIXED pending the fast and global zero-cost gates.
- 2026-07-30: GP-003 global verification passed at `5555396`; status advanced to VERIFIED.
- 2026-07-30: Three-finding checkpoint after GP-001 through GP-003: the dedicated adversarial
  grounding and faithful-paraphrase set passed (`5` tests, `14` subtests); observed acceptance
  regressions: zero.
- 2026-07-30: GP-004 fail-first policy regression reproduced that the committed edge plan is
  observation-only; trusted-proxy identity regressions remain green.
- 2026-07-30: GP-004 focused policy tests and local command rendering pass with enforced deny
  actions and `publish_authorized=false`; status advanced to FIXED pending the global gate.
- 2026-07-30: GP-004 repository changes passed the fast and global gates at `39c5d7c`. External
  verification reached the three-attempt hard stop: (1) repository policy inspection proves only
  desired configuration, (2) the renderer confirms `publish_authorized=false` and changes no
  external state, and (3) the task's zero-network/no-publication boundary prevents a preview
  cross-instance probe. Status is BLOCKED only for that external proof; exact recovery is recorded
  in the finding row.
- 2026-07-30: GP-005 completion regressions added explicit byte/frame accounting for misleading
  lengths and eight concurrent oversized request bodies.
- 2026-07-30: All four focused GP-005 body-boundary tests passed without another runtime patch;
  the implementation fix is credited to `b3e202a` and the remaining change is durable proof.
- 2026-07-30: GP-005 global verification passed after one formatter-only retry at `7f633b1`;
  status advanced to VERIFIED.
- 2026-07-30: GP-006 explicit authority/date/jurisdiction/complementary matrix was added before
  implementation; the local-authority case exposes the missing authority type.
- 2026-07-30: GP-006 focused matrix passes after adding the missing typed local-authority class;
  behavior and evidence documentation now state that authority labels never imply precedence.
- 2026-07-30: GP-006 global verification passed at `7381037`; status advanced to VERIFIED.
- 2026-07-30: GP-007 deterministic hostile providers were added for every sequential model stage
  plus caller cancellation; live ask/map deadline regressions remain part of the same gate.
- 2026-07-30: All focused GP-007 deadline/cancellation regressions pass without another runtime
  patch; the shared deadline fix is credited to `1a47099` and `6ad68aa`.
- 2026-07-30: GP-007 global verification passed at `d4f6ddf`; status advanced to VERIFIED.
- 2026-07-30: Three-finding checkpoint after GP-005 through GP-007: the dedicated adversarial
  grounding and faithful-paraphrase set passed (`5` tests, `14` subtests); observed acceptance
  regressions remain zero.
- 2026-07-30: GP-008 fail-first tests were added for record caps, server-side bbox propagation,
  local spatial backstop, and injectable typed layer definitions.
- 2026-07-30: GP-008 focused live-service and presentation suites pass. A first implementation
  attempt hid malformed geometry at the local bbox backstop; the correction preserves those
  records as unknown, retaining CF-001's safety behavior.
- 2026-07-30: GP-008 global verification passed at `9dc82d6` after resolving import-format and
  offline-qualification compatibility findings; status advanced to VERIFIED.
- 2026-07-30: GP-009 fail-first regression demonstrates that a fixed top-five rank cut can remove
  a required aspect and distinct supporting source before sufficiency checks run.
- 2026-07-30: The corrected GP-009 regression (synchronous and actually executed) now passes;
  the first async-on-`TestCase` version was rejected as a false-pass harness defect.
- 2026-07-30: GP-009 global verification passed at `deb490b`; status advanced to VERIFIED.
- 2026-07-30: GP-010 fail-first backend/UI regressions were added for a server-bounded assistant
  history representation across all response modes.
- 2026-07-30: GP-010 global verification passed at `a0a4b4f`; status advanced to VERIFIED.
- 2026-07-30: Three-finding semantic checkpoint after GP-008 through GP-010 passed:
  five adversarial/faithful tests, fourteen subtests, zero failures.
- 2026-07-30: CF-008 fail-first regression now requires explicit incomplete-list disclosure
  after deterministic claim salvage.
- 2026-07-30: CF-008 global verification passed at `bd66d4b`; status advanced to VERIFIED.
- 2026-07-30: CF-009 fail-first regression covers a one-token source-title collision
  that previously promoted a tangent question into paid retrieval.
- 2026-07-30: CF-009 global verification passed at `e21a180`; status advanced to VERIFIED.
- 2026-07-30: CF-010 fail-first lifecycle matrix covers success, typed provider failure,
  unexpected failure, timeout, and direct caller cancellation.
- 2026-07-30: CF-010 global verification passed at `026bbaa`; status advanced to VERIFIED.
- 2026-07-30: Three-finding semantic checkpoint after CF-008 through CF-010 passed:
  five adversarial/faithful tests, fourteen subtests, zero failures.
- 2026-07-30: CF-011 fail-first header regression requires a self-only style policy
  with no `unsafe-inline`; existing build and map browser tests remain the compatibility gate.
- 2026-07-30: CF-011 global verification passed at `4eb1f64`; status advanced to VERIFIED.

## Final report

### Candidate identity and disposition

- Branch: `maintenance/v1-5-principal-remediation`.
- Audited base: `fc1c7d0bb55aa18c94b2e6540cd6590c5385ad7c`.
- Qualified source candidate: `faf79940aacdf0a6c943e0e726c477d46aefd2e3`.
- Canonical findings: 17 total; 16 VERIFIED and 1 validly BLOCKED.
- The findings table above is the final findings-to-commits-to-tests map. Every row names its
  pinned regression path, implementation commit, final status, and observed gate evidence.
- The original dirty checkout was not modified. Its untracked evaluation and research files were
  preserved. No branch was pushed, merged, deployed, or published.

The repository-actionable remediation is complete. This is not a production-release approval:
GP-004 still requires external proof, and the deferred paid and human gates below remain mandatory.

### Blocked item

GP-004 is BLOCKED only for external distributed enforcement proof. The repository now ignores
ordinary forwarding headers, accepts the platform-owned identity only in an identified Vercel
environment, keeps the instance-local limiter as defense in depth, and renders an enforced,
method-scoped edge deny plan with publication disabled. Local tests cannot prove that two deployed
instances share the published quota. Recovery requires owner authorization to create a preview,
publish the reviewed edge rules, and execute the documented two-instance quota probe. Those actions
were outside this zero-network, no-publication loop.

### Faithful-paraphrase false-abstention delta

Observed delta: **0** relative to the post-GP-001 semantic-gate baseline. The fixed acceptance set
(`test_validator_allows_faithful_quantity_paraphrase` and
`test_validator_allows_preserved_conditions_statuses_polarity_and_dates`) passed at every required
three-finding checkpoint and on the final candidate. The final combined adversarial/acceptance run
passed 5 tests and 14 subtests. This is a bounded regression result, not a claim about unreviewed
real-world questions; the human semantic review remains required.

### Final zero-cost qualification

All commands ran locally with fakes and fixtures. No OpenRouter, Gemini, Cohere, ArcGIS, geocoder,
or other external service was called.

| Command | Final result |
|---|---|
| Dedicated adversarial grounding plus faithful paraphrases | 5 passed, 14 subtests passed |
| `make verify` | secret scan and generated-contract checks clean; Ruff and formatting clean; mypy clean; 221 Python tests passed, 10 skipped, 102 subtests passed; 13 UI tests passed; production build passed; 4 Sites tests passed; 18 Playwright tests passed |
| `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_reliability.py -rs` | 13 passed, 9 subtests passed; Hypothesis-backed reliability tests executed |
| `git diff --exit-code` | clean after generated-file checks |
| `npm --prefix prototype/firelens-rag-ui test` | 13 passed |
| `npm --prefix prototype/firelens-rag-ui run build` | TypeScript typecheck and production build passed |

### Foundation alignment

- Deterministic code remains authoritative for safety, semantic invariants, citation validation,
  freshness, geometry, schemas, request limits, and release disposition.
- Models still propose only within bounded contracts; no model or lexical shortcut can promote
  rejected evidence.
- No framework, model, reranker, retrieval strategy, corpus, live source, or provider fallback was
  changed. No dependency was added.
- Public request contracts remain compatible. The response gained only an optional,
  server-derived bounded history field; visible answer text remains unchanged.
- Changes are isolated in one reviewable finding per implementation commit, with a separate durable
  evidence update. Generated OpenAPI and TypeScript files were regenerated, never hand-edited.

### Explicitly deferred release gates

The paid 105-case probe rerun, sealed retrieval review, and 50-case human semantic review were OUT
OF SCOPE for this loop and are still required before release. They must be executed against the
exact promoted candidate after GP-004's preview enforcement is verified. Historical results do not
qualify this tree, and no production-readiness claim should be made until those gates pass.
