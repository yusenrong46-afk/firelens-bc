---
name: firelens-release
description: Qualify an exact FireLens candidate and update release evidence or deploy only when every required gate and authorization is present.
---

# FireLens release

## Trigger

Use for candidate qualification, preview comparison, release documentation,
deployment, promotion, rollback planning, or post-deploy verification.

## Purpose and input

Input is an exact clean candidate SHA/tree, target environment, gate matrix,
budget, authorization, and rollback target. Produce evidence, not assumed GO.

## Allowed actions

- Run deterministic, provider-budgeted, browser, performance, and docs gates.
- Update release metadata and evidence bound to the exact candidate.
- Deploy only when requested, authorized, and all prerequisite gates permit it.

## Forbidden actions

- Do not call local/CI/Vercel READY success production verified.
- Do not deploy with P0, safety, authority, identity, or required-gate failures.
- Do not invent human review, provider runs, deployment identity, or rollback.
- Do not push, merge, promote, or spend without the needed authority.

## Workflow

1. Pin candidate, tree, datasets, evaluators, models, corpus/index, API, and assets.
2. Run the documented qualification matrix without weakening floors.
3. Deploy the exact SHA to preview only when authorized and credentials exist.
4. Run the Product Reality Gate and compare preview with production.
5. Record GO/NO-GO and rollback target; production requires explicit authority.
6. After production, rerun identity, readiness, source, browser, and UI gates.

## Output schema

`candidate`, `target`, `gate_results`, `cost`, `preview_identity`,
`production_identity`, `rollback_target`, `decision`, `blocked_by`, `artifacts`.

## Stop and handoff

Stop at preview-only or blocked-with-evidence whenever any required proof,
credential, budget, or authorization is absent. Never manufacture release GO.
