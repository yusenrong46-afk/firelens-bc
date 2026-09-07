# FireLens polish release — 2026-09-07

**FIRELENS_POLISH_RELEASE_DEPLOYED_AND_VERIFIED**

[Open FireLens](https://firelens-bc.vercel.app/). [PR #78](https://github.com/yusenrong46-afk/firelens-bc/pull/78)
merged as `8688c000017e4f1f54ef8b3e957de101c74c69b3`. Its complete tree,
`3dfefc0b67921ea8881c20a53ef62d210a7d227b`, is byte-identical to independently
reviewed candidate `20bbafd2c44e4bb298a861b656d33224ec5b4966`.

The canonical deployment wrapper published production deployment
`dpl_DXBrUYroDBzLdEMoXasv1q48sUzq`, with the actual merge SHA as its build identity.
The production alias, runtime candidate hash, 178-chunk corpus/index identity,
models and approved privacy policy match the merged candidate. All 20 deployed
client files match the reviewed build. No second deployment is needed for this
release-record update; documentation changes do not alter production inputs.

## Acceptance and independent review

Maintained remote [Verify](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/34147436838)
and [candidate evidence](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/34148023105)
passed on the exact PR revision. The downloaded candidate bundle passes the
repository's integrity verifier; all 12 recorded command exits are zero,
including dependency audits and candidate-artifact checks. Normal main workflows
also run on the merge revision; their outcomes remain separate from PR evidence.

Current EvalLab acceptance is PASS under the independently reviewed v2 policy.
Raw historical results remain **565/574 with nine failure records**, rc2.2
**96/105**, and rc2.3 **97/105**, against the unchanged 86/105 floor. The raw
hard-probe runners exit zero because the floor is met; the former EvalLab
critical-veto gate exits one. No historical FAIL has been rewritten as PASS.
Current J01 remains accepted while the same answer fails frozen rc2.2.

All nine dispositions are bounded class A semantic-contract disagreements,
not ID-only exemptions: F06/F07/K03 preserve official-source handoffs;
F09/I04/K09 require missing location; I08 preserves the actual two-turn clarification
trajectory; L05 binds a real two-concept background response; J01 binds the
approved current source rationale. The [disposition table and executable checks](firelens-polish-ci-policy.md)
preserve the exact questions, evidence and reasons. New failures, changed meaning,
missing evidence, runtime-policy changes and modified frozen inputs are rejected.

Independent read-only High review accepted the policy after one bounded
applicability repair, then accepted the dependency/documentation delta with no
remaining actionable finding. Final review SHA-256:
`287932db8b45295cf79f7f9f6aeae57de04e5b6134a2c5eea99b9107d174ea9d`.

The release adds the approved source/index/UI work, the narrow mixed-contents
coordinator repair, versioned CI acceptance in existing evaluation owners, and
targeted pypdf/Browserslist security updates. It introduces no runtime parser,
safety layer, retrieval architecture, model or provider. Dependency equivalence
checks preserve the adopted PDF properties and byte-identical client assets.

Fresh frozen checks include two backend passes of 2,648 tests, 12 skips and 709
subtests; 203 frontend tests; 45 mocked browser passes and one skip; source-aware
conversation 106/106; offline ProductBench 31/31; zero structural-publication
violations; docs, generated-file, full `make verify`, audits and candidate bundle
build/verify. The earlier 51/51 built-stack/accessibility matrix and accepted
implementation/provider evidence are retained through demonstrated runtime
identity; they are not relabelled as new production runs.

## Actual production observations

Two browser Ask requests ran against the production alias with empty history and
no interception or synthetic upstreams:

- Mixed contents and evacuation question: HTTP 200, adopted page-5 contents,
  separately identified reviewed claim, and an explicit personal evacuation
  boundary. Trace `7e92a8875c0346a9b8726e8b67c221bd`.
- Pet-packing question: HTTP 200, exact page-6 pet passage, partial/extraction-only
  publication rather than a complete interpreted checklist. Trace
  `2e886bd8d8644e1ca9a350b59d899c33`.

Both semantic payloads match their retained qualified responses; supporting
passages match the adopted corpus with line-wrap whitespace normalization.
Production logs show a successful embedding request and rerank request for each,
with zero generation. No rate-limit failure was observed in these production
requests. The source link opens the canonical PreparedBC PDF; a fresh fetch
matches adopted SHA-256
`9185b43a8b9b57820c2fdd17a8e7887d483e02519358d001445460b4f44446d2`.
Browser PDF rendering is not claimed.

At `2026-09-07T17:52:54Z`, the live-map response contained 131 incident records.
Selecting returned ID `incident:C10467` showed Swede Creek, Under Control,
1,815 hectares and its matching official source/freshness details. Home cleared
conversation and selection; reopening the map retained no selection. These are
dated observations, not current wildfire information.

Perimeter and evacuation layers were unavailable because source geometry failed
validation. The UI displayed partial coverage and unavailable-layer wording,
including that missing evacuation data is neither a zero count nor an all-clear.
Geometry validation was not weakened. Desktop and mobile production views were
inspected; the 320px view had no horizontal overflow.

## Accounting, rollback and limits

The unchanged US$1 ceiling contains **US$0.01434842 settled** and
**US$0.9326656 reserved**, total **US$0.94701402**. Unreserved headroom is
US$0.05298598. This includes the full US$0.48 production request reservations:
operational logs are not complete billing receipts, and null cost is not zero.
All prior unsettled reservations, including the original US$0.05 embedding
attempt, remain held. Six of eight extension Ask requests are used; two remain,
but the remaining cash headroom does not fund another conservatively reserved
production Ask without settlement evidence. No further calls are planned.

No rollback was needed. The recorded preceding production deployment is
`dpl_FeF5mba9xBMUWAPZqVTHtprhDXin`, build
`c06474d34ff92433357be443d7c44eeffe28f0fe`. Provider availability can vary;
L05's earlier upstream rate limits remain evidence. FireLens does not decide
personal evacuation, certify complete live coverage, or turn static guidance
into current conditions. The retained grouped mixed-answer heading is a known
presentation limitation; source proof distinguishes the reviewed paraphrase
from exact quoted contents.

The checkpoints below retain earlier failures and intermediate states. They do
not supersede this release result.

---

# Historical CI migration checkpoint — 2026-09-07

Draft [PR78](https://github.com/yusenrong46-afk/firelens-bc/pull/78) carries the
reviewed source/UI changes and [versioned CI policy](firelens-polish-ci-policy.md).
Independent High review accepted the semantic policy after one bounded
applicability repair. Exact1ec7445 passed full local verification and maintained
EvalLab, with historical565/574 and nine raw failure records preserved.

The remaining candidate security commands correctly failed on pypdf and
Browserslist advisories. Targeted dependency upgrades now have clean audits;
PDF validation properties and all20 client assets remain identical. Revised
full checks and dependency/documentation review are pending. No merge or production
deployment is claimed by this checkpoint.

Four of eight extension Ask requests are used. Accounting remains
US$0.01434842 settled plus US$0.7026656 reserved, including US$0.25 protected for
production smoke. No failed-provider reservation has been released. Production
remains on its recorded rollback deployment until all preproduction gates pass.

The checkpoints below retain the earlier observations and failures.

---

# FireLens final qualification continuation — 2026-09-07

**Mixed and pet real-provider qualification completed; release remains NO-GO
pending final independent review and maintained CI acceptance.** No push, merge
or deployment occurred in this continuation checkpoint.

Qualified repair implementation: `287772bbf2f07c53456d4171a53e58fca69ad0fc`, tree
`a6db8b268d1efefcc955220d3399a121113de539`. It starts from documentation candidate
`845fdecddc737bd8c439252b60e98fafff04df3a`; all 1,103 unchanged tracked paths were
byte-compared against reviewed implementation `1161367`, and the six changed paths
were documentation/image files. Runtime identity and assets were rebuilt for the
exact starting candidate before paid requests and again for the repair. The final
documentation successor is bound separately in the external qualification freeze.

Only three of eight additional Ask attempts were used:

1. Exact mixed question: HTTP 200, but only bag-construction guidance, without the
   requested contents. Preserved as a semantic failure, not qualified success.
2. Exact pet question: HTTP 200, partial exact quotation from adopted PreparedBC
   page 6, including food, water, leashes and carriers. No invented full checklist.
3. Exact mixed question after accepted repair: HTTP 200 with the page-5 contents
   quotation, separately typed reviewed claim and personal evacuation boundary.

The sole repair preserves the original isolated contents clause in the existing
coordinator, using the existing `requests_contents` predicate. No parser, safety
layer, source, model, provider, compiler or evaluation contract changed. The
independent High repair review accepted it for paid confirmation; 214 protected
tests plus 39 subtests passed. Standalone pet execution is unaffected and its
successful prior response is explicitly carried forward, not rerun or relabelled
as a fresh response from the repair. The current pet regression still passes.

Actual provider completion includes two new transient rerank 429s, each followed
by a successful normal-policy retry. They remain availability evidence. All three
requests used the approved model/privacy policy and real index. The repaired
mixed confirmation used no generation. No calls were made after both missing
journeys qualified. Current accounting is US$0.01392722 settled receipts plus
US$0.425 retained reservations under the unchanged US$1 ceiling. The original
US$0.05 failed embedding reservation remains. Only unallocated Ask-envelope
balances were released; no dispatched failed-provider reservation was released.

Fresh implementation matrix: `make verify` passed (two backend passes of 2,625
passed, 12 skipped and 709 subtests; frontend 203 tests; mocked browser 45 passed,
one skipped); built-stack 51/51; source-aware 106/106; offline ProductBench 31/31;
rc2.3 hard probe 97/105 against floor 86; structured-publication violations zero.
The current same-response J01 pass and frozen rc2.2 failure remain distinct.
Desktop/390px/320px presentation replay of the actual successful responses has no
horizontal overflow; those screenshots replay retained provider responses and
make no new provider or deployment claim.

A separate run of the exact maintained Verify EvalLab core command is **FAIL
565/574**. Its validator rejects six retained CRITICAL-labelled failures:
F06, F07, F09, I04, K03 and K09. J01, I08 and L05 also remain individual failures.
The candidate-evidence workflow uses rc2.3, but Verify still requires a PASS core
envelope from the frozen rc2.2 adapter. This failure is preserved, not waived or
replaced with the current profile's floor pass. No evaluator/CI acceptance rule
was changed in this bounded repair. Final independent review must adjudicate the
release disposition; current CI must pass before release.

Evidence: `firelens-polish-evidence/final-qualification/`, including the original
and fixed FailureRecords, exact public requests/responses/traces, budget ledger
snapshot, repair High review, fresh matrix logs and final qualification freeze.
The five-minute GMT script remains conditional on release gates; there is no
production success claim. Earlier checkpoints below are historical.

---

# Historical FireLens polish checkpoint — 2026-09-07

**FIRELENS_POLISH_BLOCKED_WITH_EVIDENCE** — independent High review accepted the
code; required mixed/pet real-provider qualification remains incomplete after
upstream rate limiting. All eight allowed Ask requests have been used. The
credential, source decision, J01 migration and real index rebuild are resolved.
No push, merge or deployment occurred.

Reviewed implementation: `11613679c7910c0c15962ee16da49ba7bc530ff2`, tree
`37a6cca440ddeae3687482fcb0999ec77d24e9bf`. The documentation successor's exact
commit/tree is recorded in the external final handoff; its runtime files are
unchanged from this reviewed implementation.

## Identity and source

Baseline/main: `fc9b72368456bfefa4b1251c41a62422939cc0ab`, tree
`0be841458f4589b4a2919aaa57349e7569404334`. Branch: `codex/firelens-polish`.
The prior pet repair `b2265de` was inspected and cherry-picked as `cbe6329`.
This record describes the subsequent working changes; the external checkpoint
manifest records their exact file hashes and final commit/tree.

PreparedBC changed from `f82166e0c05cb3f46a42aa4023da7cdd71e3c3fdae64965c8f436426f5702ea3`
to `9185b43a8b9b57820c2fdd17a8e7887d483e02519358d001445460b4f44446d2`.
A fresh official fetch matched the reviewed packet. Thomas adopted the packet's
three scoped repairs, sixteen replacement statements and withdrawal of
`TC-GENERAL-036-01`; the [decision record](../reports/PREPAREDBC_REVISION_DECISIONS.json)
accurately identifies the AI-assisted basis. Historical extracted artifacts,
inventory and tests are retained in `data/history/preparedbc-f82166e0`; the old
raw PDF has not been recovered.

Current corpus: 178 chunks, comprising 45 PreparedBC and 133 unchanged other
source chunks. Corpus SHA-256:
`4045d15f475c4987571dc190b2f67053cdd95690eeb02506b45cccb532d1578c`.
Inventory SHA-256:
`5fcda128c37bd366227a8d5f0c7637de83a14be0d67a3637c0c4b74d462a6cb3`.
The real `metadata_context_v1` index was rebuilt through the existing cache writer:
144 complete rendered inputs were verified reusable, and exactly 34 new inputs were
embedded with `openai/text-embedding-3-small`, dimension 1536. Every preexisting
cache record was preserved. Matrix SHA-256:
`d746759193fdbd844dfa173fca3898dba380ea2d3ad37da12d422643e2d4ce0d`.
Offline fixtures remain separately labelled; no fixture vector entered this index.

## Implemented behavior

- Pet inclusion inflections reuse the prior repair. The revised guide's page 6
  still supports leashes/carriers; page 4 alone is not a full pet checklist.
- The publication quote fallback now uses the existing omission-polarity check.
  The original negative pet request had correctly failed support checking but
  then received an unrelated quote; the fallback no longer admits that quote.
- Relevance scoring includes existing typed action/object fields, distinguishing
  cautious entry, perimeter inspection and generator use under shared clearance
  conditions. Conditions and publication authority were not widened.
- Public evidence carries its deterministic document hash. Source proof groups
  by URL plus revision, reveals revision/location on demand, and warns that a
  publisher link may show a newer edition. Quotations and paraphrases remain distinct.
- Missing official coverage and record freshness are separate. Retrieval time
  reads “Checked by FireLens”; publisher time reads “Source updated”. One session
  timer updates age each minute and refreshes visible sessions at most every five
  minutes; superseded and unmounted requests cannot overwrite state.
- The nearby starter now asks for records rather than implying one specific fire.
  All four original starter requests were exercised with current-source offline
  fixtures; packing returns a supported partial quotation without generation.

## Verification completed on the reviewed implementation

- `make verify`: exit 0; two backend passes of 2,623 tests and 709 subtests,
  with 12 existing skips; lint, formatting, typing, secret scan,
  OpenAPI generation, build, tooling and Sites worker checks pass.
- Source/admission/corpus/index/typed-publication and accepted evaluator regressions
  are included in that backend run. A separate check confirms all sixteen revised
  span bindings, withdrawn-claim absence and no retired document in active retrieval.
- Source-aware conversation: 106/106. Offline ProductBench: 31/31.
- Current rc2.3 hard probe: 97/105, unchanged floor 86. Candidate-evidence validation
  passes. J01 is current PASS and recomputed legacy FAIL; eight historical hard-probe
  failures remain retained. Frozen dataset and profiles remain unchanged.
- Frontend: 203 unit tests; 45 mocked browser passes, one existing skip.
- Built-stack browser: 51/51 with deterministic upstream fixtures, including axe,
  keyboard/evidence controls and 1536/390/320px behavior. These are not real-provider
  qualification. Docs/map/index checks: 19/19. Typing: 295 source files.
- Fresh independent read-only High review: all 1,107 frozen tracked hashes match,
  79 additional focused tests pass; no blocking code regression established.
  [Sealed review](../reports/FIRELENS_POLISH_INDEPENDENT_REVIEW.md).

The full matrix first exposed a J01 evaluator import cycle and historical tests
bound to the successor corpus. Shared response predicates were moved unchanged to
one module; historical review tests now use their preserved corpus. Current-source
phrase checks account for PDF line breaks and revised wording. Browser assertions
now exercise the existing collapsed proof and current record/map controls. An axe
finding placed the active question in a labelled region; an overbroad backend
freshness label was corrected. Original failures remain in the external logs.

## Real-provider smoke and accounting

The real built stack used the actual successor index, normal OpenRouter models,
approved embedding/generation ZDR requirements and real official services.
Nearby records, selected-record follow-up and grab-and-go guidance succeeded.
J01 initially failed with rerank HTTP 429 and retryable API 503; a bounded retry
also failed. Mixed packing/personal-evacuation guidance failed with the same rate
limit, and pet packing failed after the circuit opened. These used a single-attempt
smoke setting. Ask 8 used the normal three-attempt policy and recovered J01: HTTP
200, current-source exact quotation, zero generation attempts. It does not qualify
the failed mixed/pet journeys. Home/reset and 320px overflow checks passed.

The canonical source link/click was verified, and a separate HTTP-200 fetch matched
the adopted PDF hash. Browser PDF rendering was not verified.

Reported settled spend: **US$0.00642678**. Retained reservations: **US$0.275**, including
the initial US$0.05 authentication-failed reservation and US$0.225 for three
unsettled rerank failures. The original ledger entries remain; no failed-request
reservation was silently released. The **US$1** ceiling still has room, but all
**eight Ask requests** are used. No new key or production secret change occurred.

Artifacts live in `firelens-polish-evidence/credential-resume`, with earlier evidence
retained in `resumed` and `approved-execution`. Before/after screenshots are linked
from the [README](../../README.md); the [five-minute GMT script](../product/GMT_DEMO_CHECKLIST.md)
remains a script for a qualified successor, not a claim of current release readiness.

## Bounded findings and limits

The live official snapshot had 40 province-wide evacuation features, including
four active invalid alert polygons; the bounded Kelowna fetch returned four valid
features. Keep the existing whole-layer failure behavior. Quarantining records
would require consistent partial-layer counting across spatial answers, maps and
exports. No invalid geometry is admitted and missing coverage is not a zero count.

The reported spatial evidence control was not reachable in observed built paths:
nearby spatial answers have no statement claims; mixed/selected answers use chat.
The mixed evidence control works at all three widths. No speculative panel fix.

Map and analysis charts already load separately. Initial JS remains about 554 kB
minified (161 kB gzip), CSS about 73 kB (13.5 kB gzip). No bundler rewrite or new
dependency. The first-use hierarchy and optional community copy remain; source
revision detail is collapsed to limit extra content. Detailed source repetition
can be reduced later once the integrated candidate's final evidence is known.

## Remote state and next gate

Remote main was reverified at baseline `fc9b72368456bfefa4b1251c41a62422939cc0ab`.
Its latest [Verify pull request](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/33999056559)
and [Build candidate evidence](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/33999056554)
runs remain failed. No candidate CI run is claimed because this work was not pushed.
Production was rechecked: build `c06474d34ff92433357be443d7c44eeffe28f0fe`, deployment
`dpl_FeF5mba9xBMUWAPZqVTHtprhDXin`, release 1.6.4, 179 chunks,
[public app](https://firelens-bc.vercel.app/). It remains the rollback reference.

Production runtime source changed by net **+5 lines** versus main; evaluation code
changed by net **+169**, chiefly the versioned J01 contract and paired validation.
Generated API types are excluded from those counts. No dependency, model, provider,
retrieval architecture or geometry-validation policy was added or replaced.

Independent verdict: **CODE_ACCEPTED_FOR_DOCUMENTATION_FINALIZATION**;
**LIVE_PROVIDER_QUALIFICATION_BLOCKED**; **RELEASE_NO_GO**. Successful mixed/pet
real-provider checks require a separately available Ask allowance. Do not infer
them from fixture passes or J01 recovery. Preserve all failed attempts. Then resume
normal exact-candidate PR/CI/release gates without force push or bypassing failures.
