# FireLens V1.6.2 Evaluation Framework

## Goal

This framework converts the Product Constitution into a repeatable
development loop. It is designed to make FireLens more useful without
weakening evidence authority. It is not a release certificate and does not
claim that V1.6.2 has been deployed or qualified.

## Evaluation lifecycle

For each finding, retain an issue record containing the observed user journey,
the violated constitutional contract, a minimal reproducer, the root-cause
hypothesis, a red test, the smallest patch, and post-patch falsification.

```text
Observe → Reproduce → Falsify → Contract → Root cause → Red test → Small fix
→ Narrow verify → Regression → Falsify again → Gate
```

No more than three issue clusters may be active at one time. If a proposed fix
changes a public schema, support kind, human decision, benchmark threshold, or
publication authority, stop and make that design decision explicit before
continuing.

## Benchmark pyramid

| Layer | Question answered | Primary artifact | Evidence grade |
| --- | --- | --- | --- |
| Contract tests | Does one invariant hold? | `tests/` | Executed |
| ProductBench v2 | Do representative journeys obey observable contracts? | [protocol](../protocols/PRODUCTBENCH_V2.md), [catalog](../../data/evaluation/productbench_journeys_50.json) | Executed development evidence |
| User questions | Do 50 ordinary-to-adversarial prompts retain intended product behavior? | [suite](../reports/V1_6_USER_END_QUESTIONS_50.md) | Executed regression evidence |
| Publication probe | Are structural publication leaks and authority boundaries preserved? | [structured-publication evaluator](../../scripts/v1_6_structured_publication_eval.py) | Executed |
| Hard probe | Does the frozen public probe retain its declared floor and paired-case behavior? | [dataset](../../data/evaluation/hard_probe.v1.yaml), [RC2.2 ADR](../adr/0019-rc2-2-hard-probe-expectation-profile.md) | Executed; not sealed |
| Frontend protocol | Are visible trust and workspace states rendered correctly? | [surface fixture](../../data/evaluation/frontend_surface.v1.yaml) | Executed |
| Human and live gates | Can people use the product and do remote systems behave? | [runbook](../releases/V1_6_RUNBOOK.md) | Human, measured, or release when actually performed |

ProductBench v2 snapshot-binds the current unsealed 50-ID journey catalog; it
does not establish that the catalog was immutable before the v2 manifest. Its
31-case offline tier uses deterministic doubles at zero cost; its 19
provider-backed cases are manual and cost-capped. It is development evidence
only and cannot substitute for ClaimBench, the hard probe, sealed evaluation,
human review, or release qualification.

## Scorecard

Each evaluation run should record the following fields rather than a single
unqualified “pass”:

| Field | Required value |
| --- | --- |
| Candidate identity | Commit, tree, branch, clean/dirty state |
| Scope recall | In-domain related questions routed to a useful lane |
| Authority precision | Published live/structured/quote-only material matches its lane |
| Safety boundary | No personalized evacuation, route, medical, or all-clear decision |
| Identity binding | Selected record and follow-up refer to the same official ID |
| Mixed coverage | Each requested live and static aspect is either covered or explicit missing |
| Useful failure | Missing input, source gap, or handoff is short and actionable |
| Trust presentation | Labels do not strengthen quote-only, background, or unknown content |
| Cost and provider activity | Model/provider calls, cost, and disabled-path evidence |
| Latency | Workload, hardware, sample count, p50/p95, and comparison method |
| Outcome | Pass, fail, not proven, or blocked—with linked artifacts |

## Evidence interpretation

Use the grades from the [Product Constitution](FIRELENS_PRODUCT_CONSTITUTION.md):

- **Inspected**: code or artifacts were read.
- **Executed**: a deterministic local command or fixture was run.
- **Measured**: a metric includes the precise candidate, method, and raw output.
- **Human**: named people completed a defined review or session.
- **Release**: the exact candidate has complete gate evidence and an authorized
  release decision.

Never promote one grade into another. For example, a local browser fixture is
not participant comprehension; a fixture-backed live response is not current
incident data; a green regression suite is not deployment proof.

## V1.6.2 focus matrix

| Cluster | Contract under test | Representative falsifier | Intended outcome |
| --- | --- | --- |
| Scope and safety | Scope understanding; useful failure | Ambiguous location, “Should I leave?”, map-absence all-clear | Bounded lookup or concise handoff, never a personal decision |
| Record identity and relevance | Deterministic ownership; evidence authority | Closest record, ordinal selection, adjacent typed claims | Bound selected ID; omit unrelated claims |
| Presentation and degraded behavior | User-first presentation; runtime truth | Mixed lanes, stale/unavailable layers, mobile and keyboard flow | Answer-first, locally labelled support, explicit gaps |

PB15-style malformed extraction is a tracked source-repair limitation, not a
license to paraphrase. A quote-only candidate must remain atomic and readable;
otherwise it is omitted and the existing official handoff remains available.

## Minimum commands

Commands are evidence-producing only when run against the recorded candidate:

```text
PYTHONPATH=src:tests .venv/bin/python -m pytest -q
make productbench-offline
.venv/bin/python scripts/v1_6_structured_publication_eval.py
.venv/bin/python scripts/run_hard_probe.py --mode offline --expectation-profile rc2.2
npm --prefix apps/web test -- --run
```

If any command fails, report the failure and affected scorecard rows. Do not
rewrite frozen data, lower a threshold, or alter a human decision to recover a
green result.
