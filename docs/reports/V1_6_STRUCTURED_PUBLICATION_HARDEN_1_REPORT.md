# FireLens V1.6 Coverage-First Structured-Publication Hardening Report

Status: `READY_FOR_HUMAN_CLAIM_REVIEW_CONTINUATION`

Evidence class: executed local engineering and offline verification. This report is not
independent examination, human claim approval, paid H4/H8 evidence, preview evidence,
deployment evidence, or release proof.

## Evaluated identity

- Branch: `upgrade/v1-6-structured-publication-harden-1`
- Batch 1 base commit: `47e9ee13180756e6a1c78ce0e3f22f8fd966be72`
- Evaluated implementation commit: `9e4e01dd07257c2af926ede4c1b33e1798b7e6d8`
- Evaluated implementation tree: `a53200ab386a6a91bc145bcbe69aae5d27bd1fdf`
- Historical Round 3 snapshot identity: `6d62671`

The implementation tree is clean for all task-owned paths. The working directory also
contains a pre-existing modification to `CONTRIBUTING.md` and the untracked
`docs/protocols/V1_6_GITHUB_UPDATE_STANDARD.md`; both are user-owned, unrelated, and
excluded from every hardening commit. The global working directory is therefore not
represented as clean.

## Focused commits

1. `47e9ee1` — Record Batch 1 typed-claim review decisions.
2. `15d8223` — Bind reviewed claims to admitted corpus authority.
3. `18f221b` — Prepare all typed-claim candidates for human review.
4. `721c6c7` — Cache validated publication authority.
5. `eb227e9` — Satisfy structured publication verification gates.
6. `9e4e01d` — Record human review packet hashes.

No commit was pushed, merged, deployed, or used to alter a frozen threshold.

## Batch 1 freeze

- The human-approved `TC-EVAC-ALERT-001` surface is pinned exactly and produces zero
  typed-preservation errors.
- `TC-SPRINKLER-001` remains `pending_review` and cannot be compiled as structured
  support.
- Historical inventory reports are labeled as snapshots of `6d62671`; their historical
  measurements were not rewritten.

## Authority binding and selection

External typed claims now bind to all of the following before structured compilation:

- admitted corpus chunk IDs;
- the admitted source document SHA-256;
- an atomic exact-source quote and normalized quote SHA-256;
- the approved public surface SHA-256; and
- an allowed human review state.

`PublicationAuthority.source_revision_sha256` now carries the admitted document hash.
The existing public wire shape and `S-{claim_id}` evidence identity are unchanged.
FireLens-authored freshness text uses the explicit `internal_static` binding; other Tier
A/B records require `corpus_chunk`.

Compilation fails closed for a missing chunk, changed document hash, quote no longer
present in the chunk, changed quote or surface hash, pending review, and changed approved
text without rebinding. The validated inventory/corpus authority index is cached once per
corpus root and reloads only after explicit cache clearing.

Selection uses bound chunk identity plus atomic quote overlap, then conservative
normalized exact-quote matching. An unrelated fact from the evacuation-order chunk does
not select the order claim. No BM25 selection path was added.

## Original 36-candidate ledger

Every record in immutable `candidates_pending_v1.yaml` has exactly one disposition:

| Disposition | Raw candidates |
|---|---:|
| `review_ready` | 16 |
| `duplicate_existing` | 3 |
| `not_claim_bearing` | 8 |
| `needs_source_repair` | 9 |
| **Total** | **36** |

The 16 review-ready parents produced 20 deterministic atomic proposals because multi-fact
parents were split. All 20 proposals retain lineage, source identity, exact quote,
surrounding context, conservative proposed surface, typed fields, preparation notes, and
hashes. All remain `pending_review` with null reviewer and review timestamp. They are
grouped into batches 2 and 3, 10 proposals each; Batch 1 remains the separately frozen
human decision.

Coverage delta:

- raw candidate governance coverage: 0/36 to 36/36;
- prepared atomic human-review proposals: 0 to 20;
- approved structured-production records: unchanged at 5 because this loop did not
  approve any candidate;
- unresolved source-repair candidates: 9 and explicitly excluded from review-ready
  status.

Provenance hashes:

- raw candidate queue: `008274a5cda237473697b5ddd9c8c04d3a42a8738c560d594ea682ed74344f9c`
- prepared candidate artifact: `d1e085fd7c495e18ee8f9cf6602832e128ec9a3d4a1de4ed6caa62ab9a410dfd`
- typed inventory: `589a48fbb82a95e4d589b10c59be9bd3750f01e0b039e3824ea50932911674a9`

## Human handoff

The ignored local packets contain exact quote, context, proposed surface, typed fields,
document/quote/surface hashes, quality flags, preparation notes, and instructions to
approve, edit, reject, or defer. Blank decision templates contain no reviewer, decision,
timestamp, or approved surface.

Only content-free packet manifests and hashes are tracked:

- `V1_6_TYPED_CLAIM_REVIEW_PACKET_BATCH_02.json` — 10 records;
- `V1_6_TYPED_CLAIM_REVIEW_PACKET_BATCH_03.json` — 10 records.

The generated packet and decision-template files remain ignored under `tmp/`.

## Bypass audit

| Path | Executed result |
|---|---|
| Pending typed claim compilation | Rejected |
| Changed corpus document or quote | Structured availability removed |
| Changed approved surface without rebinding | Structured availability removed |
| Unrelated quote sharing a larger chunk | Typed claim not selected |
| Free-form Tier A/B generation | Cannot obtain structured-supported status |
| Rewrite of compiled Tier A/B wording | Compiled text preserved |
| Salvage of untyped high-risk text | Cannot promote to structured support |
| Mixed structured plus uncovered content | Structured block preserved; uncovered content quote-only, partial, or handoff |
| Proof Card identity | Claim text and source revision match compiled authority |
| Compiler exclusivity | No alternate structured-claim constructor found |
| Semantic model role | Optional rejection-only; no publication authority |

The executed structural evaluator reported zero for unsupported typed identity,
unreviewed support, source mismatch, Proof Card mismatch, and model-created Tier A/B
support.

## Verification

Focused acceptance suites:

- required inventory/architecture/development command: 18 passed;
- added authority/preparation/export suites: 9 passed;
- combined focused suite: 27 passed.

`scripts/v1_6_structured_publication_eval.py` passed with zero structural leaks.

The final escalated `make verify` run against commit `9e4e01d` passed:

- Ruff check and format check;
- mypy over 192 source files;
- 915 backend tests passed, 3 skipped, 448 subtests passed;
- 47 frontend unit tests passed;
- frontend typecheck and production build;
- 4 Sites worker tests passed; and
- 26 Playwright end-to-end tests passed.

The first sandboxed Playwright attempt could not bind `127.0.0.1:4174` (`EPERM`). The
same full command passed when rerun with local-server permission; this was an execution
environment restriction, not a code waiver.

## Hard probe and offline timing

The exact-commit offline hard probe executed 105 cases at zero cost:

- Batch 1 baseline: 86 passed, 19 known offline-double misses;
- hardened candidate: 86 passed, 19 known offline-double misses;
- paired regressions: 0;
- paired improvements: 0.

The runner returns nonzero because the 19 known misses remain, but the bounded plan's
acceptance threshold of at least 86/105 with zero unexplained paired regression is met.
No paid H4 call was made.

The same five-claim structured selection/compilation workload was executed for 500
iterations after warm-up:

| Metric | Batch 1 baseline | Hardened candidate | Change |
|---|---:|---:|---:|
| p50 | 0.385541 ms | 0.136375 ms | -64.63% |
| p95 | 0.415375 ms | 0.147292 ms | -64.54% |
| provider calls | 0 | 0 | unchanged |

The p95 requirement of no more than 10% regression is met.

## Frozen artifacts and compatibility

The hard-probe dataset, ClaimBench datasets, provider configuration, retrieval defaults,
and public API schema were not changed. Current frozen hashes are:

- ClaimBench v1: `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1`
- ClaimBench v2: `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557`
- hard probe: `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035`
- admitted corpus: `d5fcd794f9ec0486a256ae511366fde982254342b7d07b9c83a21ea8ead291eb`

No public response or frontend fields were added or removed. The semantic change to
`source_revision_sha256` is internal authority binding while preserving its wire field.

## Remaining human work and stop condition

Human reviewers must review the 20 pending atomic proposals and provide explicit
approve/edit/reject/defer decisions with identity and timestamp. The 9 source-repair
records require source remediation before they can become review-ready. Independent
examination, paid H4/H8, preview, rollback, accessibility/UX review, firewall validation,
push, merge, and deployment remain separate gates.

This loop stops before human approval and therefore ends at:

`READY_FOR_HUMAN_CLAIM_REVIEW_CONTINUATION`
