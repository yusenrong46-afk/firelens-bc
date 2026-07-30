# FireLens BC V1.5 execution state

Updated: 2026-07-30 (America/Vancouver)

## Repository truth

- Review worktree: `/Users/thomas/Downloads/firelens-bc-v1-5-lab`
- Current maintenance branch: `maintenance/v1-5-repository-polish`
- V1.5 hardening baseline on `main`: `fc1c7d0bb55aa18c94b2e6540cd6590c5385ad7c`
- Qualified code candidate: `91fc37e8bfd866b710e0b614d95ecbbfc1e5139e`
- Candidate baseline: `ba42b74`
- V1.1 baseline: `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- A dedicated release-reconstruction worktree has not been created.
- `main` contains the review candidate. Production identity must be verified separately.

## Current decision

The codebase-hardening implementation is complete and the candidate is available on `main` for
independent review, but V1.5 is **not release-qualified**.
The latest complete paid hard probe is `104/105`; its only failed corpus-gap case was fixed and
then passed a commit-bound focused run, but that does not substitute for a new complete `105/105`
run. The owner-reviewed retrieval and semantic gates are also incomplete. Do not reconstruct the
claim completion of the deferred qualification gates or deploy on their basis.

## Current evidence

- `make verify`: secret scan, generated-contract drift, Ruff, formatting, mypy over 54 source
  files, 179 Python tests, 66 subtests, 12 UI tests, production build, 4 Sites tests, and 18
  desktop/mobile Playwright tests passed. Ten Python tests were intentionally skipped.
- Qualified hard probe at `ac0e437`: `104/105`, `$0.15027268`, 103.5 seconds. The sole failure was
  `C09`; commit `91fc37e` added the general fine/penalty/fee corpus-gap guard, and a commit-bound
  focused rerun passed `1/1` for `$0.00317272`.
- Static-query p95 in that complete run: `3.7526 s`, below the four-second target.
- Generalization at `91fc37e`: `33/33`, including novel-document grounding `10/10`, conflict
  `3/3`, pollution controls `5/5`, and leave-one-out protections `15/15`; 96,641 tokens and
  `$0.12189258`.
- Official-live qualification at `91fc37e`: all three layers available, metadata complete,
  chat/map IDs and statuses matched, all 26 cached/concurrent requests succeeded, and cached p95
  was `0.3794 s`. Cold fetch was `4.7981 s` and is not the cached-live target.
- Dependency audit: npm audit reported zero vulnerabilities after the lockfile override update;
  the isolated Python audit reported no known vulnerabilities.
- Public API schemas and retrieval/model/live-source configuration remain unchanged.

## Human and external gates

- Sealed retrieval review: `45/47` decisions approved; `V1-HOLD-106` and `V1-HOLD-141` need
  discussion. Reviewer name and review timestamp are absent, so the validator returns unqualified.
- Semantic review: `38/50` approved and 12 rejected. Reviewer name and review timestamp are
  absent, so the validator returns unqualified even though it records zero unclear claims and zero
  unsupported verified claims among accepted entries.
- The neutral automated-review label migration changed dataset hashes without changing questions,
  evidence expectations, or decisions. Regenerate the ignored pending review sidecars before
  resuming owner review; validators intentionally reject sidecars bound to the prior hashes.
- The one-time, three-repetition sealed retrieval run has not been authorized or executed.
- Anonymous preview, distributed rate-limit verification, rollback rehearsal, owner comparison
  approval, and verified production deployment have not occurred. Moving the source candidate to
  `main` for external review did not complete those gates.

## Next authorized action

Use independent engineering feedback to prepare a final bounded improvement pass. Later, resolve
the two retrieval-review discussions and twelve rejected semantic cases, add the actual reviewer
identity and timestamp, and revalidate both sidecars. Then run the sealed retrieval gate exactly
once and one complete hard probe at the unchanged candidate; the hard probe must report `105/105`.

See `docs/reports/V1_5_HARDENING_QUALIFICATION.md` for artifact hashes, commands, commit
dispositions, and the complete gate ledger.
