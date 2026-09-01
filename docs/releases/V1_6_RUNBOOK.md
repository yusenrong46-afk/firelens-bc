# FireLens BC V1.6.2 candidate runbook

This runbook prepares the V1.6.2 engineering candidate. It does not replace
independent semantic, accessibility, safety, retrieval, UX, or human review.
It does not authorize push, deploy, or paid runs.

Round 2 improved engineering but failed fresh semantic adversarial testing.
Round 3 introduces risk-tiered typed claims and deterministic rendering.
Visible development benchmarks are not independent proof. Adaptive retrieval
remains disabled and unqualified. Frontend automation remains strong but
human AT is external. Coverage-first structured-publication hardening has
dispositioned the original 36 candidates. Thomas approved all 20 prepared
proposals and the edited SPRINKLER surface, and deferred all nine extraction
defects outside V1.6. The integrated RC inventory contains 26 bound claims.

The current continuation report is
`docs/reports/V1_6_STRUCTURED_PUBLICATION_HARDEN_1_REPORT.md`. Historical
Round 1, Round 2, Round 3, and structured-publication reports remain snapshots
of their recorded identities.

The tracked Python package, web package, runtime default, Docker configuration,
and OpenAPI are `1.6.2`. This is a local V1.6.2 engineering candidate,
not a qualified release. Candidate evidence may bind `1.6.2` only after a clean
commit exists; a workflow label may not relabel the runnable artifact.

The V1.6.2 patch promotion is separate from the historical `1.6.0-rc.1` and
RC2 records. The frozen standard, probes, reports, and Thomas's prior human
decisions remain byte-preserved. A V1.6.2 qualification records a new exact
commit/tree and its own artifacts; it never retrofits historical evidence.

## Candidate preflight

1. Create a clean V1.6.2 commit before freezing. Record its exact Git commit
   and Git tree, then produce the matching CI candidate-evidence artifact. Do
   not name a historical RC1/RC2 commit as the V1.6.2 candidate; those reports
   remain snapshots of their recorded identities.
2. Confirm `docs/ARCHITECTURE_V1_6.md` is the Ask authority, not
   `docs/TECHNICAL_HANDBOOK.md`.
3. Confirm `FIRELENS_RETRIEVAL_STRATEGY` is `baseline` unless an authorized
   adaptive comparison is in progress.
4. Run `make secret-scan` before any recovery or snapshot artifact.
5. Run `make v1-6-package-verify` and `make v1-6-gate` for zero-cost identity.
6. Run the permanent hard probe with `--expectation-profile rc2.2`. Confirm that
   report v2 binds the unchanged historical dataset, the active RC2.2 profile
   and manifest, the frozen RC2.1 profile and manifest, the effective-expectations
   hash, and the exact candidate commit/tree. The frozen RC2 pair remains a
   separately bound material.
7. Do not treat missing H4 sealed 46/47 or H10 evidence as a pass.

## Source-aware conversation evaluation

Run `make source-aware-conversation` before candidate review. The runner is
offline and unsealed: it executes the real agent over a fresh local vector
index, a deterministic fake provider, and deterministic official-record
fixtures. The JSON report records observed routes, response modes, source
lanes, publication kinds, tool traces, provider-stage calls, and failure
reasons. It also binds the dataset/manifest, guided and capability registries,
corpus/vector artifacts, typed inventory, and current Git identity.

The command intentionally exits non-zero when the current runtime misses any
declared predicate or the zero Tier A/B generation gate. That is a repair signal,
not evidence to relax a threshold; no network or model call is made.

## Structured-publication continuation

Before independent examination:

1. Keep the 20 approved proposals bound to
   `V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml` and
   `V1_6_TYPED_CLAIM_REVIEW_BATCH_3_DECISIONS.yaml`; do not treat the journals
   as independent-exam evidence by themselves.
2. Keep the edited `TC-SPRINKLER-001` surface bound to its final append-only
   decision.
3. Keep all nine `defer_out_of_scope` decisions non-compilable.
4. Preserve Thomas's acceptance of the exact RC1 H8 report through
   `V1_6_RC1_H8_TRADEOFF_DECISION.yaml`; remeasure and obtain a new decision if
   the evaluated implementation or report changes.
5. Run independent examination against the exact implementation commit/tree.

The coding agent may prepare packets and validate bindings. It may not supply
reviewer identity or approve a claim.

## Local, preview, and production evidence

| Surface | What it proves | What it does not prove |
| --- | --- | --- |
| `make check` / `make verify` | Engineering regressions on this worktree | Deployed identity, ZDR roster, or human review |
| `make v1-6-baseline` | Frozen before snapshot / seal at Stage 0 | After-implementation improvement |
| `make v1-6-gate` | Standard identity and current inventory | H10 release GO |
| `make v1-6-package-verify` | Allowlist / Docker / Vercel logical parity helpers | A deployed origin |
| RC2.2 offline hard probe | Historical cases plus stronger declared migration invariants at zero cost, including A09/A10 two-sided structured coverage | Paid provider quality, sealed labels, or deployed behavior |
| Preview / production qualify scripts | One HTTPS origin when authorized | UX, VoiceOver, firewall, or sealed retrieval |

Archive limitation: a local report, an archived report, or a CI result from a
different commit/tree cannot qualify this candidate. Qualification requires the
exact candidate commit and tree, the matching CI artifact, and the required
human-authorized external gates.

Candidate-evidence v2 must bind the unchanged historical hard-probe
dataset/manifest, the frozen RC2 expectation profile/manifest, the frozen
RC2.1 expectation profile/manifest, and the active RC2.2 expectation
profile/manifest. It rejects a historical or RC2 current
report, an arbitrary overlay, a stale Git identity, a changed material, an
unlisted expectation migration, provider credentials, or cost. For A01 it
recomputes the exact two-kind publication set and its response invariants.
For A09 and A10 it recomputes two-sided `structured_reviewed` coverage of
`TC-EVAC-ALERT-001` and `TC-EVAC-ORDER-001`.

Paid comparison, preview Ask probes, firewall publish, rollback proof,
VoiceOver, participant UX, and sealed V3 47-case retrieval stay `EXTERNAL`
until explicitly authorized with a cost ceiling.

## Privacy and models

Production still requires fail-closed embedding/generation ZDR, deny
collection, and no fallbacks. A model swap is a change to
`FIRELENS_GENERATION_MODEL`. Tools, rails, and RAG stay. Do not enable
`ANSWER_GENERAL_BACKGROUND` as a live tool.

## Checked Vercel identity

This runbook still does not authorize push, deploy, or paid runs. When an
owner later authorizes a Vercel upload, bind identity from a **clean** local
tree before `.vercelignore` excludes `.git`:

```text
test -z "$(git status --porcelain)"
$(PYTHON) scripts/deploy_vercel.py --dry-run
```

`scripts/deploy_vercel.py` refuses a dirty tree, reads `git rev-parse HEAD`,
and constructs pinned `npx vercel@58.1.0 deploy --yes` with both `--build-env`
and `--env` for `FIRELENS_BUILD_COMMIT=<full SHA>` and
`FIRELENS_RELEASE_VERSION=1.6.2`, plus
`FIRELENS_BENCHMARK_ID=firelens_v1_6_2`, so readiness cannot keep a stale
project `1.6.0-rc.1` after that deploy. Preview is the default. `--prod` is
explicit.
`make vercel-preview` and `make vercel-production` invoke the same wrapper.

After an authorized deploy, `/api/v1/health/ready` must report that exact SHA
and `release_version=1.6.2`. The generated candidate identity is
`firelens-v1-6-2:<full SHA>`; historical callers that do not set
`FIRELENS_BENCHMARK_ID` retain the legacy `rc2` default.

If production still reports `1.6.0-rc.1` or another version, the Vercel project environment
variable `FIRELENS_RELEASE_VERSION` is overriding the wrapper and must be
set to `1.6.2` or removed. Do not rename the benchmark identifier to match.

## After qualification

Any source, corpus, index, prompt, model, threshold, configuration, or code
change after qualification invalidates the candidate. Push, PR, and merge
follow `docs/protocols/V1_6_GITHUB_UPDATE_STANDARD.md`; no remote action is
authorized implicitly by this runbook.
