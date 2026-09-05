# Documentation Audit Ledger

Audit date: 2026-09-04  
Inspection base: `ae975132c5d65800c1e960c7b6e0c46844959dfe` /
tree `c7952d897b09c2640cd0a2cc4313c925c32cd6ac`; current candidate is the
exact clean branch `HEAD` named by the final retained EvalLab envelope.

## Labels

- **CURRENT** — matches the inspected implementation or an explicitly current boundary.
- **STALE** — was once useful but no longer describes the current owner/value.
- **UNPROVEN** — lacks required identity or execution evidence.
- **HISTORICAL** — valid only for its named earlier state.
- **CONTRADICTED** — current code/artifact directly disproves the claim.

## Key claims

| Source / claim | Label | Evidence and current replacement |
| --- | --- | --- |
| [`README.md`](../../README.md): FireLens has official, reviewed, and general lanes; models do not own official facts | **CURRENT** | Matches public plan/live/publication contracts. Use the [Product contract](../architecture/01-product-contract.md) for current boundaries. |
| `README.md`: “Open the public V1.6.4 demo” and public demo availability | **CURRENT** | The public baseline was observed on 2026-09-04 at deployment `dpl_Ffh3…`, build `40c4c970…`, with readiness ready. Availability/identity is not candidate or production-product qualification. |
| `README.md`: the [Architecture Book](../architecture/README.md) is the current engineering entry point | **CURRENT** | Matches this campaign’s current-checkout architecture reference; the legacy `docs/ARCHITECTURE_V1_6.md` remains an older bounded record. |
| [`docs/ARCHITECTURE_V1_6.md`](../ARCHITECTURE_V1_6.md): “current architecture authority” and older branch-candidate framing | **STALE** | The architecture principles largely remain, and its LOC rows were refreshed, but this [Architecture Book](../architecture/README.md) is the active current-state reference. |
| `docs/ARCHITECTURE_V1_6.md`: deterministic plan owns exact tools/layers/geography | **CURRENT** | Verified in `AgentQueryPlan` and exact tool dispatch, with documented downstream duplicate/re-parse risk. |
| [`docs/TECHNICAL_HANDBOOK.md`](../TECHNICAL_HANDBOOK.md): V1.5 runtime description | **HISTORICAL** | File already marks itself historical. Do not use its “no agents” or old trace claims for current Ask. |
| [`docs/firelens_complete_system_design.md`](../firelens_complete_system_design.md): learning-first target and early corpus/results | **HISTORICAL** | File identifies itself as a target design and embeds early-state metrics; not current implementation evidence. |
| [`docs/releases/V1_6_RUNBOOK.md`](../releases/V1_6_RUNBOOK.md): V1.6.4 is a local engineering candidate, not a qualified release | **CURRENT** | Matches the active qualification boundary; a clean SHA and local deterministic pass still do not replace external, human, preview, or release gates. |
| [`docs/reports/V1_6_4_COHERENT_TRUTH.md`](../reports/V1_6_4_COHERENT_TRUTH.md): `VERIFIED_READY_FOR_HUMAN_REVIEW` and its test scores | **HISTORICAL** | Explicitly bound to a prior branch/state and admits no exact committed candidate. Cannot qualify this checkout. |
| [`docs/releases/firelens-pacific-clarity.md`](../releases/firelens-pacific-clarity.md): named production deployment was verified | **HISTORICAL** | The report remains historical. Its deployment/build `dpl_Ffh3…` / `40c4c970…` was independently re-observed ready on 2026-09-04, but the old report’s broader conclusions do not transfer to this candidate. |
| [`docs/reports/FABLE_5_1_PRODUCTION_VERIFICATION.md`](../reports/FABLE_5_1_PRODUCTION_VERIFICATION.md): preview/production reality gates passed | **HISTORICAL** | Bound to the Fable product-rescue campaign and earlier artifacts; not current candidate evidence. |
| Fable Round 2 engineering improvement/release implication | **HISTORICAL** | Its recorded state binds commit/tree `40cabcb…` / `446a802…` and concludes `NOT_PROVEN`; preserve that verdict. |
| FireLens-200 as a current release-quality score | **UNPROVEN** | Inspected judge is heuristic, fault cases are `NOT_RUN`, and costs are absent. It can be diagnostic only until corrected and identity-bound. |
| Production baseline deployment/build/readiness and served OpenAPI identity | **CURRENT** | Observed 2026-09-04: `dpl_Ffh3…`, `40c4c970…`, ready response SHA-256 `62ef0530…`, release `1.6.4`, corpus fields `firelens_static_corpus.v1`/179, expected model fields, OpenAPI SHA-256 `df598029…`. No production corpus hash was exposed; this is identity/readiness evidence only. |
| Production baseline accessibility/performance is qualified | **CONTRADICTED** | The [UI audit](../product/FIRELENS_UI_AUDIT.md) found two idle axe violations, and TTFB/FCP/CLS are one observation rather than a distribution. |
| Any EvalLab core result as current release qualification | **CONTRADICTED** | The final clean result is **FAIL 562/574**; it is local fake diagnostic evidence only. See the [Evaluation Catalog](../architecture/appendices/evaluation-catalog.md). |
| EvalLab dirty or source-changing evidence can be compared approximately to a clean baseline | **CONTRADICTED** | EvalLab blocks dirty/unstable envelopes, validates each clean envelope in a detached snapshot of its own commit, replays all four adapters, and rejects material policy/schema/dataset/evaluator incompatibility. Unverifiable ProductBench response hashes are omitted and rejected if reintroduced. |
| Any historical p50/p95, bundle, cost, live count, test total, or screenshot applies to this checkout | **CONTRADICTED** | Evidence identity differs. Current measured claims are limited to the [System Card](../system-card/FIRELENS_SYSTEM_CARD.md) and final campaign evidence. |
| `LiveLayerStatus(available=True, count=0)` always means a fully valid layer in the base | **CONTRADICTED** | Base silently dropped rows that failed `LiveResult`; invalid geometry could also be excluded instead of failing closed. The local repair quarantines the affected layer and adds strict-row, geometry, healthy-sibling, and legitimate-empty regressions. |

## Maintenance rule

Do not delete historical records merely because they are not current. Keep their identity and status visible, remove them from current navigation/authority, and point current claims to executable contracts or newly bound evidence. Re-run the ledger after a clean candidate, deployment verification, or semantic ownership change.
