# FireLens BC V1.5 release reconstruction rehearsal

Date: 2026-07-29  
Baseline: `209b4e5f8f16f13d7ac9af56a89e135f697ce052`  
Lab candidate: `1b3180da109eaa739fc942ecdc2c2ae624549301`  
Protected release branch: unchanged at the baseline

## Result

A disposable detached worktree replayed all 31 lab commits from the baseline without a conflict.
The reconstructed head was `b0baaa4d33324f7ef92e54f49ebc6056d23f36bc`; its tree matched the lab
candidate exactly (`git diff --exit-code 1b3180d HEAD`). No merge, release-branch update, push,
preview, production deployment, or firewall publication occurred.

The complete reconstructed tree passed:

- tracked secret scan;
- generated OpenAPI and TypeScript client checks;
- Ruff and format checks;
- mypy across 51 source files;
- Python suite: 155 passed, 10 skipped, 36 subtests passed;
- frontend unit suite: 12 passed;
- frontend production build;
- Sites packaging suite: 4 passed;
- Playwright desktop/mobile suite: 12 passed.

The temporary worktree reused the lab dependency directories through local symlinks. Vite emitted
font allow-list warnings for that symlinked test arrangement; all browser tests passed and the
warnings do not occur in the normal lab verification.

## Promotion interpretation

The complete lab history must be replayed to reproduce the tested tree. Contextual retrieval v2,
GraphRAG, and alternate lexical treatments remain isolated experiment code and are not selected by
the production configuration. Retaining their reproducibility code is not runtime promotion.
Dropping experiment commits from the middle of the sequence was tested and produced a different,
under-qualified tree because later gate and report commits evolved on top of them.

After both owner reviews qualify, replay the complete lab history into `codex/v1-5-release`, rerun
`make verify` from that clean worktree, and confirm the resulting tree matches the approved lab
candidate before creating any preview.

## Commands executed

```bash
git worktree add --detach /private/tmp/firelens-v1-5-release-rehearsal 209b4e5
git cherry-pick 209b4e5..1b3180d
git diff --exit-code 1b3180d HEAD
make verify
```

The executable preview and distributed-rate-limit preparation gates are documented in
`docs/releases/V1_5_RUNBOOK.md` and implemented by `scripts/qualify_preview.py` and
`scripts/prepare_vercel_firewall.py`.
