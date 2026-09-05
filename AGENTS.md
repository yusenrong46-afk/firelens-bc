# FireLens agent guide

This file is a table of contents, not the architecture manual.

## Product

FireLens is evidence-bound wildfire intelligence for British Columbia.
It combines official current records, reviewed static guidance, and clearly
labelled general background without blending their authority.

## Non-negotiable invariants

- Source failure is not zero.
- Unavailable is not empty.
- Empty is not safe.
- Stale is not current.
- Partial is not complete.
- A missing record is not evidence of no danger.
- Never fabricate an incident, evacuation record, source, quote, timestamp,
  geometry, size, distance, or ranking.
- Deterministic code owns official record identity, count, status, size,
  geometry, distance, ranking, and timestamps.
- Models may explain bound facts; they do not own those facts.
- A model cannot grant itself tools, sources, geography, or authority.
- General model knowledge is never official or reviewed information.
- FireLens does not independently tell a person to stay, return, or evacuate.
- Telemetry excludes raw questions, answers, history, exact private locations,
  credentials, and unnecessary identity.
- OpenRouter is the production model-provider boundary.

## Working policy

Use Medium reasoning by default. Escalate to High for difficult causal work,
architecture decisions or independent review; use XHigh only for a material
issue unresolved after a serious High investigation. Max needs explicit
current authorization.

Keep accepted work closed unless a concrete reproducer shows a regression.
Resolve routine reversible engineering choices within the active authorization.
Historical campaign or deployment permission is not permission for a new action.
Prefer one typed owner and the smallest evidenced repair; do not add duplicate
parsers, validators, fallbacks or provider calls for hypothetical failures.

## Engineering loop

1. Understand the relevant owner and contracts.
2. Establish a reproducible baseline.
3. Evaluate the behavior, not a desired score.
4. Record the failure and its first divergent layer.
5. Fix the smallest general cause in the true owner.
6. Add the original case and semantic neighbors as regression data.
7. Re-run protected invariants and adjacent capabilities.
8. Remove an obsolete workaround only after evaluation protects the behavior.
9. Re-measure product, performance, and bundle consequences.
10. Qualify the exact candidate before any release action.

For a localized failure, begin with `firelens-map` or `firelens-examine`.
Do not start by reading the entire repository.

## Source of truth index

- Generated engineering map: `docs/firelens-map/`
- Architecture book: `docs/architecture/`
- Whole-application system card: `docs/system-card/`
- Evaluation catalog and results: `docs/eval/`
- Product/UI evidence: `docs/product/`
- Current-state evidence: `docs/firelens-current-state/`
- Plans and bounded follow-up: `docs/plans/`
- API contract: `docs/openapi.v1.json`
- Architecture decisions: `docs/adr/`
- Repository skills: `.agents/skills/`
- Normalized evaluation artifacts: `evals/eval_lab/`

The repository copies in `.agents/skills/` are canonical. When a skill is not
available in session discovery, open its repository `SKILL.md` directly.

## Semantic owners

- Public contracts: `src/firelens/contracts.py`
- Typed intent: `src/firelens/answering/intent_automaton.py`
- Place recognition: `src/firelens/understanding/place.py`
- Location projection: `src/firelens/answering/location_intent.py`
- Immutable agent plan: `src/firelens/agent/query_plan.py`
- Runtime tool authorization: `src/firelens/agent/runtime_tools.py`
- Official adapters: `src/firelens/live.py`
- Static retrieval: `src/firelens/retrieval/pipeline.py`
- Evidence packet: `src/firelens/answering/context_packet.py`
- Publication compiler: `src/firelens/publication/compiler.py`
- Public response composition: `src/firelens/agent/compose.py`
- Final contract validation: `src/firelens/contracts.py`
- API composition: `src/firelens/api/factory.py`
- Frontend application shell: `apps/web/src/app/App.tsx`

The generated ownership map is authoritative for the maintained index. These
short pointers are navigation aids and must not become duplicate policy.

## Evaluation authority

Use the narrowest valid oracle, in this order:

1. deterministic executable oracle;
2. source/reference truth;
3. browser functional correctness;
4. human-reviewed label;
5. calibrated AI judge.

Do not use an AI judge for IDs, counts, distances, ranks, status, timestamps,
URLs, source authority, requested layers, selected records, or schema validity.
Never change a frozen expected answer merely because the product fails it.

## Critical commands

```bash
make setup
PYTHONPATH=src:tests make check
PYTHONPATH=src:tests make verify
PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/build_map.py
PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/validate_map.py
PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/impact.py <file-or-symbol>
PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/trace_case.py "..."
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval inventory
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite core
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval diagnose CASE_ID
make docs-check
```

Provider-backed evaluation requires an explicit positive cost ceiling. Local
success is engineering evidence, not deployment or production qualification.

## Change routing

- Map or ownership question: use `firelens-map`.
- Reproduce and localize a failure: use `firelens-examine`.
- Run or compare evaluations: use `firelens-eval`.
- Inspect deployed/local UX: use `firelens-ui-audit`.
- Patch a confirmed failure: use `firelens-fix`.
- Remove duplication/dead paths: use `firelens-simplify`.
- Qualify or release an exact candidate: use `firelens-release`.

## Release boundary

Pin commit, tree, dataset/evaluator identities, provider models, corpus/index,
OpenAPI, and frontend assets. A Vercel READY state is not product readiness.
Do not push, merge, deploy, promote, or declare release GO without the required
authorization and current gates. Record the rollback target before production.

## Working-tree safety

Preserve unrelated edits. Do not force-push or destroy history. Generated map
or evaluation output must identify whether its source tree was dirty. Historical
artifacts are evidence, not current truth, and must remain labelled historical.
