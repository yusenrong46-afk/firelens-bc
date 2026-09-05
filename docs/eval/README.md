# FireLens evaluation

EvalLab is the canonical navigation and evidence layer over FireLens's existing
evaluators. It preserves mature suite-owned datasets/oracles and fails closed on
source or evidence-identity ambiguity.

## Current disposition

| Evidence | Result | Authority boundary |
| --- | --- | --- |
| Historical Sol core | FAIL 562/574 | Historical bridge; unsealed local diagnostics |
| Frozen Astra core | FAIL 566/574 | Eight failures; F10 pass was a route-switch artifact |
| Local RAG/source | Executed 30/30 on frozen Astra | Source/oracle fixtures; external/sealed provider adapter BLOCKED |
| Metamorphic | Executed 14/14 | Mainly plan-level, not end-to-end generalization |
| Trajectory | Executed 3/3 | Three actual successive-turn fixture flows |
| Fault | Executed 12/12 | Bounded deterministic faults, not provider outage qualification |
| Lifecycle units | Executed 7/7 | Unit state tests, not browser journeys |
| Current built-stack UI | Executed 7/7 on frozen Astra | Synthetic upstreams, built frontend/FastAPI |
| Historical built-stack UI | FAIL 9/19 | Ten retained copy/disclosure/selector failures, owner migration pending |
| Performance controls | Executed 6/6 | Sampling/accounting validity, not latency acceptance |
| Public-path v2 | Draft repair protocol | Same public path, explicit completion/mutant controls; owner approval pending |
| Current browser v2 | Draft additional candidate gate | `make verify-candidate-browser`; old lane preserved |
| External/human/deployed/judge | BLOCKED or NOT_RUN | No authorization or qualifying evidence inferred |

New repair run identities, measured counts and pending approvals live in the
[bounded repair record](../reports/BOUNDED_REPAIR.md) and its external packet.
The frozen runners and expected labels remain reproducible.

An evaluator mismatch is not automatically a confirmed product defect. EvalLab
keeps the run red while a FailureRecord stays under owner review. It never edits
expected answers merely because the product misses them.

## Commands

```bash
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval inventory
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite core --output-dir /absolute/evidence/path
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval run --suite rag
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval diagnose K09
PYTHONPATH=src:tests .venv/bin/python -m firelens_eval compare BASE_SHA CANDIDATE_SHA --artifacts /absolute/evidence/path
```

Executable failures return 1. Missing, unsafe, provider-dependent, or
intentionally unexecuted evidence returns 2. A suite can pass only when its
registered evidence is complete, source-stable, and clean.

## Integrity contract

- A dirty `application_sha` binds the base commit/tree, binary tracked diff,
  and every untracked path and byte; dirty evidence cannot pass.
- Source identity is captured before and after execution. Changed-during-run
  evidence is persisted with `BLOCKED` status and is ineligible for comparison.
- Clean historical comparison opens each envelope's own commit in a detached
  snapshot, validates it there, and semantically replays all four core adapters.
- Policy, registry, failure schema, evaluator, and dataset identities must be
  compatible; volatile vector-manifest self-hashes are rejected.
- ProductBench's random-trace-derived `trace.response_sha256` has no available
  stable preimage. EvalLab omits it from retained/replayed rows and rejects raw
  artifacts that reintroduce it.

The checked-in
[`CURRENT_DIAGNOSTIC.json`](../../evals/eval_lab/core/CURRENT_DIAGNOSTIC.json)
is explicitly a superseded historical dirty-run pointer. Final clean envelopes
are retained outside Git to avoid making the candidate dirty or creating a
self-referential commit identity.

## Contracts and artifacts

- [EvalLab protocol](../protocols/EVAL_LAB_V1.md)
- [Registry](../../data/evaluation/eval_lab_registry.v1.yaml)
- [Fail-closed policy](../../data/evaluation/eval_lab_policy.v1.yaml)
- [FailureRecord schema](../../evals/eval_lab/schema/failure_record.schema.json)
- [Artifact index](../../evals/eval_lab/README.md)
- [Evaluation catalog](../architecture/appendices/evaluation-catalog.md)

Every retained run binds application, dataset, evaluator, provider, embedding,
rerank, and judge identities where applicable. Null means not used or not
available; it never means an identity was inferred.

## Evaluation hierarchy

1. deterministic executable oracle;
2. source/reference truth;
3. browser functional correctness;
4. human-reviewed label;
5. calibrated AI judge.

Preference evidence cannot override factual correctness. AI judges are reserved
for bounded subjective criteria and must record both A/B and B/A orderings,
rubric, prompt hash, sampling settings, and human calibration.

## First-divergence workflow

1. Reproduce on a bound identity.
2. Emit a FailureRecord without assuming the product is wrong.
3. Trace understanding → binding → authority → planning → retrieval → reranking
   → evidence → generation → validation → composition → frontend.
4. Name the earliest divergent owner and confidence.
5. Add the original and neighboring regressions.
6. Repair the smallest general contract.
7. Re-run the case, mutation family, neighbors, and protected invariants.
8. Mark `fixed` only when an exact candidate SHA proves it.

## Release boundary

EvalLab results are evidence inputs. Preview and production also require
identity/readiness preflight, provider and official-feed qualification, Product
Reality Gate, accessibility/product review, rollback target, and human release
authority. No current artifact supplies those gates.
