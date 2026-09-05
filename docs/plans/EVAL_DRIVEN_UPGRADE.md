# Evaluation-driven upgrade: execution and decision ledger

## Astra continuation — active local campaign

The Sol terminal below is historical, not the outcome of this continuation.
Verified baseline: `c578de573b7b416e507f60df460fbca96c737bfb`, tree
`4fac479b225d017ba0261df36e49bdb61cee16f2`, clean. Original evidence validates;
a fresh core run reproduces 562/574. Candidate workspace is
`private retained evidence: firelens-astra-continuation`, branch
`codex/firelens-astra-continuation`. New evidence is outside Git at
`private retained evidence: firelens-astra-evidence`.

Preflight: Python 3.12.13, Node 25.9.0, existing locked dependencies, corpus,
index and Playwright Chromium work. Browser CLI is unavailable; installed
Playwright is the local fallback. No configured provider credentials or approved
API spend; external calls remain zero. Local fixture testing is feasible.
No push, merge, preview upload or deployment is authorized. Independent review
must run in a fresh session; it has not been executed here.

Implemented queue (one integration owner, read-only investigations completed):

1. Add versioned local diagnostic adapters and oracle controls/mutations without
   changing frozen rc2.2. Commit evaluator-only bridge and verify unchanged
   production runtime/UI bytes; bind its baseline runs.
2. Repair false source availability/authority, explicit-source downgrade and
   unsupported source identity; preserve real supported/background controls.
3. Repair personal-threat clause classification and terminal boundary retention;
   keep the supported live clause and explicit geographic scope.
4. Reproduce and repair delayed response/geolocation after Home, draft reset and
   evidence-panel task friction; same-fixture browser comparisons.
5. Source-stable protected checks, paired loopback performance, map/docs refresh,
   candidate freeze and neutral review packet. Paid/live/human gates stay pending.

Implementation/results through `bbf970f`: core 566/574, source-aware 106/106,
local RAG/source 30/30, metamorphic 14/14, trajectory 3/3, fault 12/12, lifecycle
7/7 and current browser 7/7. Legacy UI stays 9/19. Candidate `2a03467` was
rejected for a new SA-GQ-15-P1 over-refusal; `386b5f4` repaired the distinction
between personal papers and named sources and bound document preparation to
its existing reviewed capability. Twelve supplemental controls preserve source
attribution and exclude unrelated/extra-clause matches. `bbf970f` is the type-safe
version of that repair. Original and rejected evidence are retained.

Freeze procedure: make the final documentation-only commit, run source-stable
`make verify` and all seven EvalLab suites into `final/`, validate same-evaluator
comparisons, and write external `FINAL_FREEZE.json` plus `REVIEW_PACKET.md`.
Those files record actual completion/identities; absence means freeze is not
complete. No more product changes are queued unless final checks find a defect.
See the [canonical Astra report](../reports/ASTRA_CONTINUATION.md). Performance
is measured, not accepted: six local backend route p95s increased over 10% in
the first quiet pair, with no acceptance invented. Independent review is next;
this builder session does not execute it.

Initial browser probe: fixture server at `127.0.0.1:8776`, original workspace;
`baseline-idle-1536.png` used an older compiled asset set and is excluded from
the candidate comparison. The rebuilt current-interface diagnostics pass five
journeys and reproduce two Home/reset defects. The legacy full-stack suite has
obsolete copy/layout assertions; its original source and red results are retained
separately, not silently amended. This is local fixture UI, not deployed or
human preference evidence. The fixture's readiness and live
summary disagree; do not infer a production readiness regression from it.

Disposition so far: F06/F07/F09/I04/K03/K09 have safe substantive handoffs or
clarifications but enum conflicts and false availability presentation. H01/I08
also mislabel static gaps as live gaps. H02/H03 confirm explicit-source and
source-identity defects (North Bend fixtures are absent from the active corpus).
F10 confirms personal-threat and mixed-scope loss. L05 fake generation cannot
establish model quality, but its background proof authority is false. Original
expectations/results remain unchanged; approval of any replacement stays pending.

Date: 2026-09-04  
Branch: `codex/firelens-eval-driven-upgrade`  
Terminal decision: blocked with evidence; the clean local candidate exists, but
EvalLab core and required external/human gates are not green

## Identity ledger

| Identity | Value |
| --- | --- |
| Prompt-preparation main | `d70f5303113ba2ae088a8f8b5bbff36cf2190720` (superseded observation) |
| Fetched `origin/main` / starting commit | `ae975132c5d65800c1e960c7b6e0c46844959dfe` |
| Starting tree | `c7952d897b09c2640cd0a2cc4313c925c32cd6ac` |
| Candidate SHA | Exact clean branch `HEAD`; resolve with `git rev-parse HEAD` and verify against the retained final EvalLab envelope |
| Production build observed | `40c4c970bf33192ce6a543a6b8dcf5b4799036bd` |
| Production deployment observed | `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh` |
| Production readiness response SHA-256 | `62ef05309dd2a65c5a06d0c7dbe96a8b109733414c58a75892ea63b89510e7f1` |
| Production OpenAPI SHA-256 | `df598029b423c7fbafa84be4e9086c9d1a7b5777abb9685e7d29d9762e38eff7` |

Production reported release `1.6.4`, corpus
`firelens_static_corpus.v1` with 179 chunks, embedding
`openai/text-embedding-3-small`, rerank `cohere/rerank-4-pro`, generation
`openai/gpt-5.6-luna`, and strategy `metadata_context_v1`. Readiness did not
expose production corpus bytes; local corpus/vector hashes are not substituted.

## Understand: architecture before and after

Before this campaign, architecture truth was spread across a long V1.6 file,
historical release reports, source, and test suites. Evaluation had many useful
runners but no canonical inventory, failure schema, status precedence, or
first-divergence interface. Agents had no short repository table of contents or
machine-generated ownership graph.

After the campaign’s local implementation:

- `docs/firelens-map/` provides generated modules, symbols, imports, tests,
  ownership, invariants, capabilities, complexity, and request lifecycle;
- `scripts/firelens_agent/` builds, validates, queries impact, traces a case,
  and checks mechanical documentation drift;
- root `AGENTS.md` is a 140-line table of contents and safety/workflow contract;
- seven repository skills separate mapping, examination, evaluation, UI audit,
  fixing, simplification, and release authority;
- `docs/architecture/` is a 20-chapter current-state book with generated-fact
  appendices;
- the whole-application System Card and documentation-audit ledger bind current
  claims and expose historical/unproven ones;
- EvalLab wraps mature evaluators and emits normalized identity-bound evidence.

These changes improve navigability and evidence discipline. They do not by
themselves improve semantic quality or qualify a release.

## Baseline

The clean pre-fix base was evaluated before production behavior changed. Exact
artifact hashes and limitations are in the
[baseline report](../reports/FIRELENS_BASELINE_REPORT.md).

| Baseline check | Result |
| --- | --- |
| `make verify` | PASS: lint/format/mypy; backend 2,071 non-browser + 2,072 full; Vitest 178; tooling 8; Sites 4; Playwright 41 passed + 1 expected mobile skip; build passed |
| ProductBench offline | 31/31 |
| ClaimBench v2 | 332/332 |
| Source-aware conversation | 106/106 |
| Hard probe rc2.1 | 91/105; declared 86 floor met; 14 mismatches requiring adjudication |
| Provider RAG | BLOCKED; no credentials/spend; estimated maximum $14.4072 |
| Performance | Fake/local, 100 runs/route, zero failures; route p95 0.666–11.798 ms; no generation calls |
| Browser baseline | Production screenshots, live/idle journeys, axe, responsive inspection |

## First-divergence work queue

Fifteen confirmed baseline/production failures are retained as normalized
campaign `FailureRecord`s: 3 at understanding/place binding, 9 at the official
live-data contract, and 3 at the frontend presentation boundary. The permanent
hard-probe evaluation also retains 12 expectation mismatches for owner review;
those are gate failures but are not relabelled product defects.

| Finding | Priority | First divergence | Disposition |
| --- | ---: | --- | --- |
| Directive preamble, same-turn location declarations, and fronted multiword/numeric B.C. places | P0/P1 | typed understanding and place binding | Repaired with explicit response-directive grammar, declaration binding, and generalized place vocabulary; semantic neighbors added |
| Malformed row, geometry, size, timestamp, or published-count contract | P0 | official adapter normalization/publication boundary | Repaired fail-closed: the affected layer is unavailable; valid sibling and legitimate empty remain distinct |
| Incomplete pagination and named-fire roster coverage | P0/P1 | official adapter fetch/completeness owner | Repaired with authoritative-count equality, concurrent metadata/count/page fetch, and bounded complete roster pagination |
| Case/whitespace-sensitive closed status and mixed-scope count loss | P1 | official live status/count composition | Repaired with exact normalized status matching and additive disjoint fire/evacuation totals |
| Incident/perimeter rows shown as separate “active wildfires” | P1 | Frontend record-summary interpretation | Repaired locally using typed kind + incident identity; row breakdown retained |
| Evacuation-only response labelled as wildfires | P1 | Frontend record-summary interpretation | Repaired locally and regression-tested |
| Hard-probe mode vocabulary differs from safe current modes | Gate | rc2.2 expectation contract vs product semantics | Gate remains FAIL; case records stay review; no expectations edited |
| General packing query retrieved pet-specific guidance | P1 | Retrieval/evidence relevance | Review; no downstream copy patch |
| Low-contrast muted text and unlabeled semantic containers | P2 | Design token/component semantics | Repaired locally; candidate idle axe 0 violations |
| Mobile status/map chrome delayed the question; header wrapped | P2 | Responsive order/navigation density | Repaired locally and browser-locked at 320px |

The distribution is dominated by evaluation-contract review because the
permanent hard probe’s allowed-mode vocabulary predates current safe response
modes. Those are not relabelled product successes or failures until adjudicated.

## Generalization and simplification

- Place parsing uses a response-control grammar rather than an exact forbidden
  phrase, recognizes same-turn personal declarations without authorizing a
  background subrequest, and keeps fronted place candidates adjacent to their
  separators. Multiword and numeric B.C. communities share the same vocabulary
  contract.
- Live normalization applies one layer-level fail-closed rule because the public
  contract has no safe partial-row state. Successful empty remains distinct.
  Completeness requires the fetched unique-ID count to equal the authoritative
  published count; every geometry ordinate, size, and timestamp is validated.
- Named-fire lookup pages through the bounded roster; mixed fire/evacuation
  totals add disjoint scopes; closed-state matching is exact after
  whitespace/case normalization.
- UI summary logic keys on typed record kind/incident number, not prose or a
  Kelowna-specific condition.
- Generated OpenAPI types replace duplicated guided-question, live-summary, and
  product-event unions.
- Confirmed-unused `savedScopes.ts` and `exportRecordsCsv.ts` were removed.
- Redundant mobile recent-history state/UI was removed; desktop history stays.

## Before/after measures

| Measure | Before | Current local | Delta/meaning |
| --- | ---: | ---: | --- |
| Production Python LOC (`src/firelens`) | 76,953 | 77,297 | +344; bounded production repair |
| EvalLab Python LOC (`src/firelens_eval`) | 0 | 3,391 | Separate evaluation infrastructure |
| Web TypeScript/TSX LOC | 8,526 | 8,460 | −66; dead modules and duplicate UI removed |
| Web CSS LOC | 3,276 | 3,284 | +8; responsive/accessibility rules |
| Main JS bundle | 546.86 kB / 159.64 gzip | 546.18 kB / 159.78 gzip | −0.68 kB raw / +0.14 kB gzip |
| Main CSS bundle | 79.46 kB / 14.62 gzip | 79.64 kB / 14.67 gzip | +0.18 kB / +0.05 gzip |
| Provider/model calls | 0 in baseline offline evidence | 0 in candidate diagnostic | No provider performance claim |
| Local fake route p50/p95 | Captured per route | Final clean-candidate run retained outside Git | Loopback fixture only; not fleet latency |
| Regex call-site occurrences | 519 | 520 | +1; files containing them remain 89 |
| Modules over 650 / 800 lines | 18 / 0 | 18 / 0 | No new oversized module; enforced caps stay green |

LOC is not the success criterion. The two TypeScript files were removed only
after reference analysis and protected tests. The Python increase is accepted
because it adds a canonical evidence contract rather than another product
decision owner.

## Evaluation and product result

- Clean-candidate EvalLab core: **FAIL 562/574**; ProductBench 31/31,
  ClaimBench 332/332, source-aware 106/106, hard probe 93/105.
- Unsupported EvalLab suites: explicit BLOCKED/NOT_RUN, exit 2.
- Frontend unit/build: 21 Vitest files, 183 tests pass; TypeScript and Vite build
  pass.
- Full local Playwright fixture run: 41 passed with one expected mobile-only
  popup skip; final neutral-label rerun passed 2/2.
- Candidate idle axe at 1024 and 390: 0 violations; live map: 0 violations and
  1 incomplete manual-review group.
- No calibrated judge, sealed retrieval, paid provider, real-feed candidate,
  preview, or production candidate run exists.

## Automation disposition

GitHub Actions should own deterministic map freshness, docs drift, core
evaluation, affected tests, and affected evaluation-family reporting on PR/main.
Reasoning-heavy nightly/weekly diagnosis may emit FailureRecords and
recommendations, but must not autonomously rewrite production. Post-deployment
Reality/readiness/asset checks require an exact deployed SHA and environment.

## Release gate

| Gate | Result |
| --- | --- |
| Exact clean candidate SHA | PASS — branch `HEAD`, bound by final local artifacts |
| Full settled-tree `make verify` | Final local result recorded in campaign handoff |
| `make docs-check` | Final local result recorded in campaign handoff |
| EvalLab core | FAIL |
| RAG/metamorphic/trajectory/fault/performance | BLOCKED or NOT_RUN |
| Human product/accessibility review | NOT RUN |
| Authorized preview and Product Reality Gate | NOT RUN; no `VERCEL_TOKEN` |
| Production deployment/post-deploy qualification | NOT RUN and not authorized |
| Rollback target | Production build `40c4c970…` observed; no candidate rollout exists |

## Decision

The campaign improves architecture knowledge, evaluation discipline, typed
understanding, official-live contract enforcement, typed UI truth,
accessibility, and mobile hierarchy. It is not releasable. The hard
probe/EvalLab gate must be adjudicated without benchmark gaming, missing suites
need real oracles, and preview/human/external qualification must be completed.
