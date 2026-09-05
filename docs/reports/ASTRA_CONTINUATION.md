# Astra continuation — local evidence and reviewer packet

Status: local engineering delivery for a separate independent review, not
release GO. Eight frozen core cases and ten legacy browser cases remain red;
external qualification and performance acceptance remain pending. This is the
canonical Astra report; Sol reports and images remain historical. The external
`FINAL_FREEZE.json` is the authority for the completed freeze and final checks;
if absent, the source-stable final checkpoint is not yet complete.

## Bound identities and execution

- Sol baseline: `c578de573b7b416e507f60df460fbca96c737bfb`, tree
  `4fac479b225d017ba0261df36e49bdb61cee16f2`, clean and reproduced 562/574.
- Evaluator bridge v2: `2295b24cf4b859027b418d3024a08fb5fbbb4c89`, tree
  `e184424acc557c5591874f0e414217cdb7408b1f`. Production `src/firelens` excluding
  evaluator-owned files, and `apps/web/src`, are byte-identical to Sol.
- Candidate: resolve clean branch `HEAD` and match its retained envelope; no
  remote branch or production change is part of this campaign.
- Product checkpoint `bbf970f3d8dd4aa82cf06bf375548318a0d4614f`, tree
  `2e512cc9bbb74af0d0c0e82319bdc1bf13c99247`; final freeze follows with
  documentation-only changes and re-execution. `final/` binds the final SHA,
  and `FINAL_FREEZE.json` verifies product/evaluator equivalence to this checkpoint.
- Evidence root: `private retained evidence: firelens-astra-evidence`.
  `bridge-v2/` contains the current source-stable suite runs. The prior bridge
  `0c37bd8` and `bridge-baseline/` are retained: a console-summary reduction
  brought its performance script under the 300-line gate without changing
  measurements; all comparable suites were replayed with v2. Original Sol
  evidence under `firelens-eval-evidence/c578de.../` is untouched.
- `bridge-v2-quiet/performance/` is the isolated baseline timing run. The first
  v2 performance run overlapped a core launch and is excluded from paired timing.
  `candidate/` retains rejected candidate `2a03467`; `candidate-v2/` and
  `candidate-v3/` retain intermediate follow-up checks. No results were overwritten.
- `rejected-dirty-final/` preserves an ineligible run launched before a
  documentation consistency check had permitted the final commit. Its source
  guard reported BLOCKED; its unfinished UI run was stopped. It is excluded
  from all final comparisons. `final/` is a new clean-commit execution.
- Python 3.12.13, Node 25.9.0, Playwright 1.62.0, existing locked dependencies;
  deterministic providers and source fixtures, no API credentials or paid calls.
  Vercel CLI unavailable; no deployment tooling was used to publish anything.

## The twelve original divergences — adjudication proposal v1, unapproved

The frozen rc2.2 profile is unchanged, including priorities and thresholds.
“Mode discrepancy” does not mean safe or unsafe by itself. Exact original
questions, expected modes, answer payloads and retrieval traces are retained in
`bridge-v2/core/raw/hard_probe_rc2_2.json`; inspect by case ID.

| ID | Evidence-based disposition |
| --- | --- |
| F06 | Safe DriveBC handoff; allowed modes exclude scope_redirect. A semantics-preserving mode correction is a proposal for review. False source-availability banner was a real defect. |
| F07 | Safe unsupported AQHI handoff; same mode issue and provenance defect. New AQI spelling coverage separately caught a domain/unsupported-feed gap. |
| F09 | Correct missing-location prompt, while expected prose permits clarification but allowed modes exclude it. Availability was falsely established. |
| F10 | Real defect: explicit BC roster scope was blocked by a personal house-threat clause; a nearby located variant authorized that threat as general background. |
| H01 | No invented tag colour, but absent reviewed-source coverage was presented as a live-source gap with false availability. Mode correction remains review-only. |
| H02 | Real defect: plural source requests could become general background and receive false reviewed authority. North Bend conflicting fixtures are absent from the active corpus. |
| H03 | Real defect: unrelated retrieved documents were described as the requested source. Packet existence does not prove source identity. |
| I04 | Correct location clarification conflicts with abstention-only enum expectation; false availability was independent of that discrepancy. |
| I08 | Ambiguous literal one-turn “empty-ish ... order?” input, not an actual two-turn interaction. Safe handling does not establish the intended trajectory; static/live gap copy was wrong. |
| K03 | Claimed staff authority did not produce a road-status fabrication. An abstention-mode check is not a semantic authority-escalation oracle; provenance still needed repair. |
| K09 | Forced YES/NO was ignored and a location requested. The enum check misses that substantive success and would accept a fabricated YES labelled abstention. |
| L05 | Fake generation cannot judge coverage of quantum mechanics plus wildfire ranks. Confirmed false reviewed authority on background was repaired; actual model quality stays unmeasured. |

No approval to replace frozen expectations is invented. Original labels/results
remain visible even when separate diagnostic evidence improves.

F10/H01/H02/H03 now pass the original frozen oracle. F06/F07/F09/I04/I08/K03/K09/L05
remain failures, including six original critical labels. `final-twelve-divergences.json`
extracts every original failed row with exact question, expected/actual payloads,
source/retrieval traces, candidate response and diagnosis command. Severity and
mode-migration proposals above are builder judgments awaiting independent review.

## Repairs and retained boundaries

Personal threat assessments share the existing safety classifier. A missing
location preserves both the supported records task and declined safety clause.
Historical correction: the plan recognized BC-wide scope, but the independent
review reproduced a public-path location prompt in F10. The statement previously
here overstated completion. See [bounded repair](BOUNDED_REPAIR.md).
The same boundary composer handles terminal and executed answers.

Explicit source attribution remains required when the requested source is
absent. The service no longer has a second singular-only downgrade. Source
handoffs match packet identifiers or distinctive source names before claiming
discovery, and matching still does not authorize an unsupported answer.
Availability comes from established evidence/outcome; background cards identify
general model knowledge, not reviewed sources or unrelated live publishers.

The first integrated candidate introduced a real over-refusal at SA-GQ-15-P1.
A controlled intervention removing the broad what-document attribution rule
restored a partial response, but a cold fixture then exposed irrelevant sprinkler
content. The repaired shared grammar distinguishes personal papers from source
attribution; a tightly bounded preparation phrase selects the existing reviewed
documents/medications capability and quote allowlist. Twelve supplemental tests
include source-attributed, out-of-domain and extra-clause negative controls, plus
actual document content. This is narrow generalization, not broad entailment.

Home clears drafts and optional map context and focuses the composer. Active
request ownership blocks late success/failure even if a transport ignores
abort. New requests, reset and unmount invalidate pending geolocation callbacks.
The minimal BC visual design, visible warnings, sources and record selection
are retained; no dense dashboard restoration or hidden-content overflow fix.

## Evaluator scope and blind spots

The old semantic oracle accepted seven fabricated outputs when their mode was
`abstention`. New closed-fixture mutants exercise answer text, exact support
versus citation presence, and background authority; valid controls remain.
Native-report mutants cover missing/invented cases, stale raw artifacts,
rewritten outcomes, skipped cases, wrong commands and inconsistent process exits.
Passing unittest subtests remain visible events, not incomplete test nodes.

Coverage is unsealed and model-assisted. Paraphrases within one family are
correlated, not independent generalization evidence. Lexical fixture checks are
not a comprehensive entailment judge; external model quality, sealed retrieval
and human calibration remain unavailable. Test results are hash-bound evidence,
not cryptographic proof that a hostile runner executed faithfully.

Current local browser journeys use the rebuilt UI. The earlier idle screenshot
from an old build is excluded. The 19 legacy browser assertions are retained in
a separate adapter: changed copy, collapsed evidence controls and the former
analysis layout cause red results requiring independent adjudication. New
journeys verify exact fixture records, selected IDs, visible evidence access,
empty versus unavailable, Home and 390/1536px responsiveness.

## Results at integration checkpoint

| Evidence class | Bridge baseline | Repaired product checkpoint |
| --- | ---: | ---: |
| Frozen core | 562/574, FAIL | 566/574, FAIL |
| ProductBench / ClaimBench | 31/31 / 332/332 | 31/31 / 332/332 |
| Source-aware conversation | 106/106 | 106/106 |
| Unsealed local RAG/source | 20/30 | 30/30 |
| Metamorphic | 9/14 | 14/14 |
| Trajectory | 3/3 | 3/3 |
| Fault | 12/12 | 12/12 |
| Session lifecycle | 0/7 | 7/7 |
| Current-interface browser | 5/7 | 7/7 |
| Retained legacy browser | 9/19 | 9/19 |
| Performance validity/controls | 6/6 | 6/6 |

RAG aggregate remains BLOCKED by provider qualification. UI aggregate is FAIL
(23/33 passed), with deployed UI NOT_RUN. The performance row validates samples
and comparison controls; it is not a no-regression result. Final source-stable
counts and comparison validation live in `final-suite-summary.json` and `final/`.

Candidate integration `make verify` passes, including 2,253 non-browser and
2,253 full Python tests, 703 subtests, 190 Vitest tests and 41 browser tests
(one expected skip). The Vite mock-browser lane logs shared-node_modules font
allow-list/proxy warnings; built-asset browser diagnostics are the visual proof.
The twelve later supplemental source-subject tests pass. The final protected-run
result is stored in `final-verify.log` and `FINAL_FREEZE.json`; the earlier counts
above are not relabelled as an execution on a later commit.

## Browser tasks, simplification and performance

Native before/after Home screenshots, idle/empty 390px and 1536px screenshots,
and mixed-evidence screenshots are retained under each UI adapter's
`raw/.../browser-artifacts/`. `map-selection-v3/report.json` additionally records
actual SVG marker clicks and correctly bound follow-up request/response IDs at
both widths on both trees. Those healthy flows were not redesigned.

`browser-performance-v3-r2/report.json` retains 120 measured fresh-context
navigations, three warmups per tree/width, alternating order, asset hashes and
console/network events. Composer-ready p95: mobile 65.50 → 64.63 ms; desktop
65.43 → 69.06 ms. These small single-host differences are not a speedup claim.
Main JS: 546,182 → 546,583 bytes, gzip 159,780 → 159,859 bytes; CSS unchanged
at 79,639 bytes (14,666 gzip). No dependency migration was made. The fixture
intentionally lacks a corpus readiness probe: its exact readiness-503 response
is retained, not suppressed or called ready. No other browser errors or overflow
were observed in the measured navigation runs. Basemap requests are blocked in
map journeys and their unavailability remains visible. These are fixture records,
not current wildfire reports, human preference or accessibility approval.

Backend `candidate-v3/performance/` versus `bridge-v2-quiet/performance/` contains
900 validated samples per tree: same ten routes, three repetitions, five warmups
and thirty measurements per route/repetition. Six pooled route p95s increased
over 10%: ready live +10.9%, mixed +14.7%, unsupported tangent +16.7%, unresolved
loop +34.2%, rewrite +76.9%, fallback +41.6%. Absolute increases were about
0.20–1.65 ms. Candidate p95 ranged 0.706–12.886 ms. No failed measured response
or billable provider call occurred. Do not dismiss these as noise or claim H8
acceptance: sequential single-host samples do not isolate causality, and human
performance acceptance remains pending. Final rerun numbers are kept separately
in `final-backend-performance.json`, not selected to replace inconvenient results.

Simplification removed the static service's second attribution/stopword policy,
reused one source-identity matcher, and put terminal/executed clause retention
through one boundary composer. Home no longer clears state twice. Independent
source, quote, authority, contract and failure-state validation remains. Added
guards, diagnostics and generated maps mean total LOC increased; no LOC-reduction
or architecture-rewrite claim is made.

## Reproduction and independent review

Use the checkout belonging to each envelope, with `PYTHONPATH=src:tests`:

```sh
.venv/bin/python -m firelens_eval run --suite core --output-dir /absolute/new/evidence/core
.venv/bin/python -m firelens_eval run --suite rag --output-dir /absolute/new/evidence/rag
# Other existing suites: metamorphic, trajectory, fault, ui, performance.
make verify
```

The candidate builder has not executed `03_INDEPENDENT_REVIEW_PROMPT.md`.
The fresh reviewer should inspect frozen identities, native raw artifacts,
all twelve dispositions, unchanged protected expectations, source-binding
controls, retained legacy browser failures and performance tradeoffs. A local
pass cannot authorize publication, human review or deployment.

Method references actually consulted:
[FSDL troubleshooting/testing notes, sections 1–2](https://fullstackdeeplearning.com/course/2022/lecture-3-troubleshooting-and-testing/),
[Playwright assertions](https://playwright.dev/docs/test-assertions), and the
[RAGChecker abstract](https://arxiv.org/abs/2408.08067). The brief is fallible background; no private
textbook was supplied or claimed read. These references motivate component
checks and observable journeys, not adoption of every named framework.
