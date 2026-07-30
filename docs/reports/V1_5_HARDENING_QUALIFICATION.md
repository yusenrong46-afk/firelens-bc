# FireLens BC V1.5 hardening qualification

Date: 2026-07-29 (America/Vancouver)

## Decision

**HARDENING COMPLETE; RELEASE BLOCKED.** The internal seams, permanent evaluation runner, CI,
security controls, privacy-safe logs, dependency fixes, and semantic safeguards are implemented
and verified. Promotion is not authorized because the last complete hard probe is `104/105`, the
sealed retrieval review is not qualified, and the semantic review is not qualified.

## Scope delivered

- Documented and enforced one same-evidence-packet grounded repair followed by deterministic
  validation, supported partial salvage, or abstention.
- Extracted `GroundedAnswerEngine` and `LiveAnswerCoordinator` without changing the public API.
- Added the permanent 105-case hash-bound hard probe with offline and cost-capped qualified modes.
- Added pull-request CI, scheduled dependency/license checks, pinned actions, secret scanning,
  generated-file drift checks, static analysis, tests, builds, packaging, and browser coverage.
- Added CSP/security headers, production debug-route denial, experiment import boundaries, and
  privacy-safe structured operational logs.
- Removed all known npm and Python vulnerability findings observed during qualification.
- Corrected corpus-source references, ambiguous requests, mixed-scope blending, enumerated repair
  completeness, authority-rewrite sufficiency, unsupported administrative claims, current-fire
  paraphrases, and unsupported fine/penalty claims without changing the corpus, model, reranker,
  retrieval strategy, or live sources.

## Gate ledger

| Gate | Evidence | Result |
|---|---|---|
| Full repository verification | 179 Python tests, 66 subtests, 12 UI, 4 Sites, 18 Playwright; Ruff, format, mypy, build, secret and generation checks | PASS |
| Hard probe | Complete run `104/105` at `ac0e437`; sole `C09` failure fixed and focused `1/1` at `91fc37e` | NOT PASSED |
| Generalization | `33/33` at `91fc37e` | PASS |
| Novel document | `10/10` | PASS |
| Conflict and leave-one-out | `3/3` conflict and `15/15` leave-one-out | PASS |
| Static performance | p95 `3.7526 s` in the latest complete run | PASS |
| Official live sources | 3/3 layers, complete metadata, chat/map parity | PASS |
| Cached live performance | p95 `0.3794 s`; concurrency 1, 5, and 20 all HTTP 200 | PASS |
| Dependency security | npm zero findings; Python no known findings | PASS |
| Sealed retrieval owner review | 45/47 approved; two discussions; missing reviewer metadata | BLOCKED |
| Semantic owner review | 38/50 approved; 12 rejected; missing reviewer metadata | BLOCKED |
| Sealed three-repeat retrieval | Waiting for qualified owner review | NOT RUN |
| Preview, distributed limit, rollback | Require owner-approved release candidate | NOT RUN |
| Release reconstruction / tree equality | Preconditions not met | NOT RUN |

Automated citation exactness, safety, poison, jailbreak, conflict, and leave-one-out checks passed
in the executed suites. These checks are not presented as a substitute for semantic owner review.

## Reproduction commands

```text
make verify
.venv/bin/python scripts/run_hard_probe.py --mode qualified --max-cost-usd 0.25
.venv/bin/python scripts/run_limitation_probe.py --suites generalization --max-cost-usd 0.25
.venv/bin/python scripts/run_live_qualification.py
.venv/bin/python scripts/retrieval_owner_review.py validate
.venv/bin/python scripts/owner_semantic_review.py validate
git diff --exit-code
```

Paid commands require the existing OpenRouter configuration. They must not be placed in automatic
external pull-request workflows.

## Ignored evidence artifacts

| Artifact | SHA-256 | Observation |
|---|---|---|
| `output/hard_probe/ac0e437_qualified.json` | `6de796f9942358014f05e5cb4e0a4e11252bd09c5ac6a51bb12fd1e88915f2e4` | 104/105, `$0.15027268` |
| `output/hard_probe/91fc37e_c09_gap_guard.json` | `42bd0ee5c63cfbff5472e3ed805cb8b17d1c25936993dcbb3e94581e574617af` | focused C09 1/1, `$0.00317272` |
| `output/naive_user_probe/results.json` | `e43bac75125df44997c24bc8a464266f348e184e67c638558fdd0b9fe15fa356` | generalization 33/33, `$0.12189258` |
| `output/qualification/v1_5_live.json` | `8dd069231ff9c3ed8e16b2d575dfadb9c3a4aa4848347aa36ee04bac83d9a8ad` | live qualified at `91fc37e` |

The generalization artifact is paired with this ledger immediately after execution at `91fc37e`;
the legacy runner does not place a Git field inside its JSON. Its hash is retained to prevent a
later result from being confused with this run.

## Commit dispositions

`PROMOTE` below means suitable for the eventual reconstructed candidate if all release gates pass;
it does not authorize cherry-picking today.

| Commit | Disposition | Reason |
|---|---|---|
| `0e3355f` | PROMOTE | Frozen baseline and experiment harness |
| `3e89e22` | PROMOTE | Corpus-aware evidence-bound planning |
| `6f2c5d0` | EXPERIMENT | Contextual retrieval v2, excluded from production |
| `3db3dc2` | PROMOTE | Typed official live adapters |
| `e07b9cf` | PROMOTE | Compatible live response contracts |
| `9a8e0a7` | PROMOTE | Restrained map experience |
| `77ed686` | EXPERIMENT | Contextual retrieval experiment surface |
| `9021416` | EXPERIMENT | GraphRAG boundary; not promoted |
| `1d4602f` | PROMOTE | Explicit location boundary |
| `c4e770c` | PROMOTE | Evidence and safety calibration |
| `bcb3646` | PROMOTE | Official freshness validation |
| `c984231` | PROMOTE | Retrieval gate reporting |
| `ab3d429` | PROMOTE | Mechanical formatting |
| `bbb1186` | PROMOTE | Historical qualification evidence retained |
| `7e77691` | PROMOTE | Development retrieval gate fix; owner gate still authoritative |
| `fba79cc` | PROMOTE | Live/mixed evidence hardening |
| `ade480e` | PROMOTE | Operational safeguards and identity |
| `6903c86` | PROMOTE | Conflict disclosure and admission controls |
| `4bd5e28` | PROMOTE | Historical trust checkpoint |
| `ebc05eb` | PROMOTE | Frozen holdout qualification tooling |
| `0b5b698` | PROMOTE | Paid-probe cost ceiling |
| `7fce824` | PROMOTE | Live geometry and cache qualification |
| `727110e` | PROMOTE | Paid-probe provenance manifest |
| `0c92a6d` | PROMOTE | Historical qualification ledger |
| `bf336d6` | PROMOTE | Canonical checkout boundary |
| `c5717ad` | EXPERIMENT | Retrieval optimization not promoted |
| `46ae83a` | PROMOTE | Owner semantic release gate |
| `eca9119` | PROMOTE | Sealed 47-case retrieval gate |
| `a679b2f` | PROMOTE | Owner-review handoff evidence |
| `06f4f64` | EXPERIMENT | Retrieval bakeoff; production settings retained |
| `1b3180d` | PROMOTE | Preview qualification tooling |
| `f6bb447` | PROMOTE | Release reconstruction proof documentation |
| `4c52b12` | PROMOTE | Hard-probe RAG and safety fixes |
| `e1c8b7d` | PROMOTE | Map-failure evidence continuity |
| `a093bf0` | PROMOTE | Enumerated evidence completeness |
| `ba42b74` | PROMOTE | Chat/map parity proof |
| `970ca10` | PROMOTE | Repair-contract documentation |
| `8e55f2a` | PROMOTE | Grounded-answer engine seam |
| `df351f4` | PROMOTE | Live coordinator seam |
| `8771e73` | PROMOTE | Permanent hard-probe system |
| `fe5a22b` | PROMOTE | CI and dependency controls |
| `112fcdc` | PROMOTE | Privacy-safe logs and security headers |
| `338f987` | PROMOTE | High-severity dependency findings cleared |
| `626bdac` | PROMOTE | Explicit corpus-source references |
| `10b32d7` | PROMOTE | Ambiguous and mixed-scope safeguards |
| `f27ca10` | PROMOTE | Evidence-sufficiency boundaries |
| `ac0e437` | PROMOTE | Current-fire status paraphrases |
| `91fc37e` | PROMOTE | Fine/penalty corpus-gap guard |

## Promotion sequence still required

1. Resolve and sign the 47-case retrieval review.
2. Resolve and sign the 50-case semantic review.
3. Run the sealed retrieval gate exactly once and require at least 46/47 Recall@5 in every run.
4. Run one unchanged-candidate complete hard probe and require 105/105.
5. Reconstruct `codex/v1-5-release` from `209b4e5` using only approved commits.
6. Prove release-tree equality and rerun all gates from a clean release worktree.
7. Create and qualify an anonymous preview, verify distributed limiting, and rehearse rollback.
8. Obtain owner approval before main merge; production deployment remains a separate action.
