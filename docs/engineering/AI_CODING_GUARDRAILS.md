# Evidence-backed coding guardrails

## Required loop

1. Discover the active Git state, implementation, callers, contracts, tests, and configuration.
2. Record the intended behavior and acceptance checks before editing.
3. Verify every interface in code or version-matched primary documentation.
4. Implement the smallest coherent change.
5. Run targeted static, contract, unit, and runtime checks.
6. Inspect the final diff for phantom interfaces, unsafe defaults, hidden fallbacks, accidental benchmark changes, duplication, and dead code.
7. Report exactly what was inspected and executed.

## Non-negotiable rules

- Behavior changes need a frozen failing test; refactors need passing characterization tests.
- Human review records, benchmark outputs, deployment evidence, and screenshots are never synthesized.
- A model may not redefine a test oracle after observing a failure.
- Product safety, provider privacy, evidence validation, benchmark, and deployment changes require human code review before release.
- External APIs are checked against the installed version or primary documentation.
- Release summaries contain no unresolved placeholders and no claims stronger than their evidence.

## Completion evidence

Every implementation handoff records the commit, changed behavior, tests executed, tests not run, known limitations, human approvals still required, and deployment identity when applicable.
