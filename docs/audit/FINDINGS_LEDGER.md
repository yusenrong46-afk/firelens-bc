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
| GP-004 | P1 | OPEN | `tests/test_request_guard.py`; `tests/test_security_operations.py` | `b3e202a` | Arbitrary X-Forwarded-For is rejected. Repository edge rules remain log-only and need an enforceable distributed policy plus offline configuration tests. |
| GP-005 | P1 | OPEN | `tests/test_provider_api.py` | `b3e202a` | Declared and streamed oversize requests fail early. Add explicit byte-consumption and concurrent-request regressions before verification. |
| CF-001 | P1 | VERIFIED | `tests/test_live.py::LiveDataServiceTests::test_nearby_results_keep_records_with_unknown_geometry`; `tests/test_live_answering.py::LiveAnswerCoordinatorTests::test_unknown_geometry_is_disclosed_without_hiding_record` | `2577462` | Malformed/unknown geometry remains visible with an explicit limitation instead of becoming a false no-result. |
| CF-002 | P1 | VERIFIED | `tests/test_v1_5_rag.py::V15RoutingTests::test_long_preamble_cannot_hide_a_personal_safety_request` | `bfac0b5` | Safety classification uses the full raw question; focused text remains retrieval-only. |
| GP-006 | P1 | OPEN | `tests/test_conflict_handling.py` | `1a47099` | Cross-authority skip was removed. Freeze and execute an explicit precedence/conflict matrix before verification. |
| GP-007 | P1 | OPEN | `tests/test_provider_api.py` | `1a47099`, `6ad68aa` | Ask/map total deadlines cancel slow live work. Add stage-wide planner/embed/rerank/generation/repair and caller-cancellation coverage, then audit active-operation cleanup. |
| GP-008 | P2 | OPEN | `tests/test_live.py` | `2577462` | Stable order, dedup, repeat detection, progress, and page ceiling exist. Add record ceiling, server-side bbox/local filtering, and config-driven layer definitions. |
| GP-009 | P2 | OPEN | pending | pending | Question-support floor exists, but there is no constrained aspect/source-diverse selection before the top-five evidence cut. |
| GP-010 | P2 | OPEN | `tests/test_reliability.py::ContractPropertyTests::test_valid_long_answer_can_round_trip_as_assistant_history` | `1a47099` | One grounded-length regression exists. Prove round-trip bounds for every response mode or add a server-issued bounded history representation. |
| CF-004 | P2 | VERIFIED | `tests/test_security_operations.py::SecurityOperationTests::test_production_never_registers_debug_routes` | `b3e202a` | Production environment prevents debug-route registration even when the debug flag is true. |
| CF-008 | P2 | OPEN | pending | pending | Audit enumerated claim salvage; any dropped supported member must be disclosed explicitly in partial limitations. |
| CF-009 | P3 | OPEN | pending | pending | Audit tangent-token promotion in evidence/support routing and add a fail-first regression. |
| CF-010 | P3 | OPEN | pending | pending | `_active_operations` cleanup is not yet proven for success, provider failure, timeout, or caller cancellation. |
| CF-011 | P3 | OPEN | pending | pending | CSP still contains `style-src 'unsafe-inline'`; remove it without breaking the built UI or map. |

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

## Final report

Pending. Append the findings-to-commits-to-tests table, blocked items, faithful-paraphrase
false-abstention delta, final zero-cost commands, and the explicitly deferred paid/human gates only
after every row is VERIFIED or validly BLOCKED.
