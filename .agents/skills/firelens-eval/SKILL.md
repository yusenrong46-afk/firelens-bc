---
name: firelens-eval
description: Inventory, run, diagnose, or compare FireLens evaluations while preserving frozen datasets and oracle authority.
---

# FireLens evaluation

## Trigger

Use for baselines, regression runs, suite comparisons, result classification,
or evaluation coverage questions.

## Purpose and input

Input is a suite, case ID, or exact baseline/candidate identity. Produce
reproducible results and normalized failures through the EvalLab adapter layer.

## Allowed actions

- Run `PYTHONPATH=src:tests .venv/bin/python -m firelens_eval inventory|run|diagnose|compare`.
- Invoke existing evaluators through documented adapters.
- Write evaluation artifacts in `evals/eval_lab/` or ignored output paths.
- Prefer separate external output directories for source-bound campaign runs.
- Execute the versioned local diagnostics in
  `data/evaluation/astra_local_diagnostics.v1.json`; Python/browser loopback
  fixtures do not authorize provider calls or external network destinations.

## Forbidden actions

- Do not modify expected answers merely because the product fails.
- Do not treat an AI preference as factual correctness.
- Do not make provider calls without an explicit budget and recorded identity.
- Do not label dry-run or fake-provider evidence as live qualification.

## Workflow

1. Record source, dataset, evaluator, provider, and judge identities.
2. Select the narrowest authoritative suite and execution mode.
3. Run without network/provider access unless explicitly authorized.
4. Normalize failures and identify the first divergence when evidence permits.
5. Separate pass, fail, review, skipped, blocked, and not-run.
6. Compare protected metrics without weakening prior safety floors.

When the evaluator changes, retain the original results and use an
unchanged-application evaluator bridge before product changes. Keep local
diagnostics, legacy assertions and unavailable qualification adapters separate.
Do not interpret native test failure as a proven production owner without
examining its assertion and trace.

## Output schema

`identity`, `suite`, `mode`, `oracle`, `counts`, `cost`, `failures`, `artifacts`,
`qualification_scope`, `blocked_gates`.

## Stop and handoff

Stop when identity or oracle is missing. Hand unexplained failures to
`firelens-examine`; hand confirmed regressions to `firelens-fix`.
