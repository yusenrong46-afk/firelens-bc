# FireLens V1.6 Round-3 engineering report

This is local zero-cost qualification of `upgrade/v1-6-semantic-round3`.
It is not a release GO. Independent held-out semantic examination is still
required. Visible development benchmarks are not independent proof.

Round 2 improved engineering but failed fresh semantic adversarial testing.
Round 3 introduces risk-tiered typed claims and deterministic rendering.
Remaining corpus coverage is human-review debt. Adaptive retrieval remains
disabled and unqualified. Frontend automation remains strong but human AT is
external.

Do not read this file as hallucination-free, semantically solved,
production-ready, or as a universal property of zero unsafe claims.

## 1. Starting and Final Identity

Starting (immutable rollback `examined/v1-6-round2`):

- Commit: `40cabcb9a3a42888474d4de1a622ca84a3fd49b3`
- Tree: `446a802f112da5ce34abe8c398475ee2413d8ed9`
- Branch at start: `upgrade/v1-6-qualification-round2`
- Package: `1.6.0rc1` / `1.6.0-rc.1`

Working branch: `upgrade/v1-6-semantic-round3` (local only; do not push).
Package version is unchanged. Candidate identity is the freeze commit that
adds `docs/reports/V1_6_ROUND3_AFTER_SNAPSHOT.json`. Recipients must run
`git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'`.

Frozen hashes (unchanged except allowlist, which gained the typed-claim file):

| Artifact | SHA-256 |
| --- | --- |
| FL-V16-S1 | `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef` |
| ClaimBench v1 | `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1` |
| ClaimBench v2 | `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557` |
| Hard probe dataset | `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035` |
| Corpus | `d5fcd794f9ec0486a256ae511366fde982254342b7d07b9c83a21ea8ead291eb` |
| Corpus manifest | `2d0d6b9b445f5ab0ef59e7f19bd0dce058a93f3a93b9599338702b95058ed687` |
| Vectors | `fd0b171488809c5a87f3aee5c912b07358231cac6478bb621f6d2fc79d41efb7` |
| Vector manifest | `437181a2a9aa03498b4bb4de2445d0e0b0bf3fe1c4d4fa76a50019d31f3f1046` |
| OpenAPI | `9c2b8ec877787fecefbb29e225d25340fb2af359ff2d8d4c92f8716d6ef5d1bb` |
| Typed-claim inventory | `902a953384fa430786289d02a52156e7fc80f6b0b4d2fdd7ec37e4c6abd0e714` |

## 2. Beginning and Ending Git Status

Beginning: clean worktree at `40cabcb9`. Rollback ref `examined/v1-6-round2`
created. Branch `upgrade/v1-6-semantic-round3` created. Not pushed.

Ending: expected clean after the freeze commit. Not pushed. Not deployed.

## 3. Reproduction of Fable Findings

EXECUTED on `40cabcb9` (`docs/reports/V1_6_ROUND3_FABLE_REPRODUCTION.json`).
Examiner case files were available under `/tmp/fable5_round2/` and imported
as original Fable development cases.

- Checker: 47/71 correct
- Unsafe false accepts: 22 of 49 mutations
- Faithful false rejects: `F-C1`, `F-F1` (2/22)
- Publication: 7 of 10 checker-survivors reached grounded publication,
  including `M-M4` “Drive through areas of dense smoke”
- Salvage did not resurrect rejected claims
- `always_abstain` false

The 22 checker unsafe IDs: `M-U4, M-C6, M-C8, M-A2, M-A3, M-A4, M-A5, M-A6,
M-F3, M-F5, M-F6, M-M4, M-M7, M-X2, M-X3, M-X4, M-X6, M-X7, M-X8, M-H2,
M-H3, M-H4`.

Publication leaks: `M-M4, M-H4, M-A2, M-A4, M-F3, M-C6, M-M7`.

## 4. Root Cause

Round 2’s checker is vocabulary-bound to ClaimBench families, not
class-general. High-overlap opposite meanings, authority substitutions,
retrieval-time-as-source-update-time, inclusive/exclusive boundary flips,
immediately-to-when-convenient, and condition/exception/scope changes passed
when they did not match frozen phrase lists.

## 5. Risk-Tier Policy

Version `firelens.claim_risk_policy.v1` in
`src/firelens/answering/risk_policy.py`.

- Tier A — action-critical: no unconstrained generated factual prose; render
  from reviewed typed claims; connective text may not change action fields.
- Tier B — quantitative/status-critical: render critical values from typed
  records; the LLM may not create or transform them except through explicitly
  validated conversions.
- Tier C — bounded explanatory content: bounded generation allowed;
  critical-field preservation and evidence support still required.

## 6. Typed Claim Architecture

Smallest practical representation:

- `TypedSnapshot` extracted from source and answer text
  (`typed_snapshot.py`): actions/polarity, orgs, time roles, ranges,
  inclusivity, conditions, exceptions, freshness, definitions.
- `compare_snapshots` / `typed_preservation_errors` (`typed_compare.py`)
  structured-compares those fields.
- `TypedClaimRecord` (`typed_records.py`) stores reviewed inventory rows
  with source-span ids, revision, and human review state.
- Unreviewed records cannot `production_supported()` and cannot
  `render_typed_claim`.

A semantic model checker remains off (`SEMANTIC_MODEL_CHECKER_ENABLED =
False`). If enabled later it may only reject, lower support, or force
partial/abstention. It may not promote a deterministic rejection, add or
rewrite evidence, or establish authority, freshness, or publication.

## 7. Reviewed Claim Coverage

Six production-supported records in `data/typed_claims/high_risk_v1.yaml`:

- `TC-EVAC-ALERT-001`, `TC-EVAC-ORDER-001`, `TC-EVAC-RESCIND-001`
- `TC-GAS-001`, `TC-SPRINKLER-001`
- `TC-FRESHNESS-001`

This inventory does not compile the corpus. Most high-risk spans remain
checker-gated rather than inventory-rendered.

## 8. Deterministic Rendering Changes

`claim_render.canonicalize_claim_text` may replace a validated compatible
Tier A/B paraphrase with the reviewed canonical sentence. Exact quote echo
is left unchanged. Mutated claims fail typed compare and are not promoted.
`live_record_fact` now carries `retrieved_at` and `freshness` separately from
`source_updated_at`.

## 9. Residual Validation Changes

`preservation_errors` now runs typed snapshot comparison in addition to the
existing critical-field checks. Output rails veto `typed_claim_mutation`.
Proof Cards project `unknown` when validation failed or
`critical_field_preservation == "failed"`. The public support state follows
the strictest failed gate.

## 10. Faithful False-Rejection Corrections

General equivalences, not Fable-id patches:

- `no fewer than` / `no less than` normalize to `at least` before comparator
  extraction.
- `live refresh` is stripped before currentness detection so stale-disclosure
  paraphrases are not read as live claims.

## 11. Checker-Level Results

EXECUTED (`docs/reports/V1_6_ROUND3_DEVELOPMENT_EVAL.json`):

| Suite | Correct | Unsafe FA | Faithful FR | Always-abstain |
| --- | --- | --- | --- | --- |
| Fable 71 | 71/71 | 0/49 | 0/22 | false |
| Round-3 extra 52 | 52/52 | 0/40 | 0/12 | false |
| ClaimBench v1 | 200/200 | 0 | 0 | false |
| ClaimBench v2 | 332/332 | 0 | 0 | false |

## 12. Full-Publication Results

Fable mutations published: 0/49. Salvage leaks: 0.
Round-3 extra mutations published: 0/40. Extra faithful published: 12/12.

Isolated-harness unpublished faithful Fable cases `F-U3` and `F-X1` fail
pre-existing `validate_draft` policies (live-claim-from-static; P8 leave
immediately), not typed-compare. They are not the Round-2 `F-C1`/`F-F1`
class. Checker FRR for those two is now 0.

## 13. ClaimBench v1/v2 Results

Catalogs unchanged. v1 200/200. v2 332/332. Passing these catalogs is not
independent proof.

## 14. Fable Development-Adversary Results

Visible 71-case adversary: checker 71/71; zero unsafe publication of the 49
mutations, including `M-M4`. This is a development suite, not a held-out exam.

## 15. Additional Development-Adversary Results

`data/evaluation/round3_semantic_dev.yaml` (52 cases, authored before
implementation completion, disjoint from the 71): checker 52/52; zero unsafe
publication; faithful FRR 0.

## 16. Hard-Probe Result

EXECUTED offline (`docs/reports/V1_6_ROUND3_HARD_PROBE.json`): **86/105**,
failed IDs identical to Round 2, **zero paired regressions**. Dataset sha256
unchanged. Evaluator unchanged.

## 17. Performance Result

EXECUTED representative workload, not a fleet average
(`docs/reports/V1_6_ROUND3_PERFORMANCE.json`):

- V1.5 generate-call average: 1.2
- Round 3: 0.8
- Reduction: 33.3% (≥20% required)
- Pure static: 1.0 generate call
- Mixed: 3.0 generate calls (grounded + in-engine repair + connective).
  Round 2 mixed was 2.0 because FakeProvider did not need repair.

## 18. Full Verification Result

EXECUTED (`docs/reports/V1_6_ROUND3_VERIFY.json`,
`docs/reports/V1_6_ROUND3_PACKAGE_VERIFY.json`):

- `make check`: 891 pytest / 47 vitest / frontend build
- full pytest: 891 passed, 3 skipped
- Sites worker: 4 passed
- Playwright e2e: 26/26 on retry (first `make verify` e2e hit a map-loading
  fill flake on the stale-records case; isolated and full-suite retries
  passed). No frontend redesign.
- `make v1-6-package-verify`: logical paths passed, including
  `data/typed_claims/high_risk_v1.yaml`. Staged Docker/Vercel inventories
  remain BLOCKED.

No serving-path `except Exception` in `src/firelens/agent` or
`src/firelens/answering`.

## 19. Tests Added Before Implementation

Commit `5e18c304cfb3920c21800909735d335cf1003f6d` added failing tests before
risk-tier/code:

- `tests/test_round3_semantic_adversary.py`
- `tests/test_round3_full_path_invariants.py`
- `tests/round3_semantic_support.py`
- `data/evaluation/round3_semantic_dev.yaml` (52 cases)

Those tests were red at that commit and are green on this candidate.

## 20. Test-Integrity Review

- Frozen 105-case hard probe, ClaimBench v1, and ClaimBench v2 were not
  modified.
- Fable 71 cases were imported, not edited to manufacture a pass.
- Extra 52 cases were written before implementation completion.
- No serving-path `except Exception` in `src/firelens/agent` or
  `src/firelens/answering`.
- Trust, freshness, authority, and time fields remain code-owned.
- Passing visible development tests is not proof of generalization.

## 21. Files and Commits

Required commit series (implementation through freeze):

1. `201e2ece` baseline and Fable reproduction
2. `5e18c304` failing tests
3. `0574442d` risk-tier and typed snapshots
4. `4a510f34` reviewed high-risk records
5. `5b6ae8f8` deterministic rendering
6. `96975879` residual validation
7. `9bec86fe` false-rejection corrections
8. `da46340f` full-path inventory tests
9. documentation and evidence (this report’s commit)
10. final candidate freeze

## 22. Remaining Unsupported High-Risk Areas

- Most corpus spans have no reviewed typed record
- Smoke driving/health actions are checker-protected, not inventory-rendered
- Live incident and evacuation records are not typed claims
- High-risk grab-and-go quantities are checker-protected, not inventory-rendered
- No production workflow publishes unreviewed model-extracted claims

## 23. External and Sealed Gates

See `docs/reports/V1_6_ROUND3_EXTERNAL_GATES.md`. Paid H4 remains BLOCKED
until Fable reports `READY_FOR_PAID_H4`. Sealed labels were not inspected.

## 24. Exact Commands for Fable

See `docs/reports/V1_6_ROUND3_FABLE_HANDOFF.md`.

## 25. Claims Supported

- Faithful paraphrases that preserve typed critical fields
- Validated unit conversions already accepted by the quantity checker
- `no fewer than` → `at least`
- Stale-disclosure paraphrases that do not claim live currentness
- Reviewed inventory renders for the six production-supported records

## 26. Claims Still Prohibited

- Avoid → perform, leave → stay, no all-clear → all-clear
- Immediately → when convenient
- Municipal → provincial; retrieval time → source update time
- Inclusive → exclusive; conditional → universal
- Authority substitutions; exception or condition deletion
- Unreviewed model-extracted Tier A/B claims as supported publication
- Personalized “should I evacuate” answers (input seatbelt / P8)

## 27. Final Status

`READY_FOR_INDEPENDENT_SEMANTIC_REEXAMINATION`

Not `READY_FOR_PAID_H4`. Not a release GO. Do not claim H2 passed until
independent Fable examination on unseen cases.
