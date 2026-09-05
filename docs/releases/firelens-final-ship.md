# FireLens final release — September 2026

## Deployed with incomplete verification

Main and the existing Vercel production project were updated on September 5,
2026. Production serves build `c06474d34ff92433357be443d7c44eeffe28f0fe`, deployment
`dpl_FeF5mba9xBMUWAPZqVTHtprhDXin`, at [FireLens](https://firelens-bc.vercel.app/).
The factual documentation follow-up leaves all runtime and build inputs unchanged.
Exact final main identity and the consolidated outcome are recorded in
[release PR #66](https://github.com/yusenrong46-afk/firelens-bc/pull/66).

**Required current-source verification failed.** The live
[PreparedBC wildfire guide](https://www2.gov.bc.ca/assets/gov/public-safety-and-emergency-services/emergency-preparedness-response-recovery/embc/preparedbc/preparedbc-guides/wildfire_preparedness_guide.pdf)
differs from the reviewed corpus document. Production's grab-and-go guidance,
significance follow-up and mixed guidance response contain excerpts from the older
version. The current checklist includes insurance/important papers alongside the
emergency plan; the retained checklist omits those added words. Other supporting
wording also changed. The current PDF SHA-256 is
`9185b43a8b9b57820c2fdd17a8e7887d483e02519358d001445460b4f44446d2`;
the admitted document is
`f82166e0c05cb3f46a42aa4023da7cdd71e3c3fdae64965c8f436426f5702ea3`.
The source link works, but its current contents cannot substantiate the displayed
excerpts as exact current quotations. Existing approval was not transferred to
the new document.

The same corpus and reviewed claims were present in the prior production build.
This is a release-significant source-maintenance gap, with no demonstrated
candidate-caused regression that a rollback would repair. Production was **not
rolled back**. The terminal outcome is
`FIRELENS_MAIN_UPDATED_PRODUCTION_DEPLOYED_BUT_VERIFICATION_INCOMPLETE`.

## Scope

The release combines accepted backend runtime `37de779`, accepted documentation
candidate `6d41a4c`, and the separately verified UI follow-up `2a9ecb6`.
The final documentation pass updates the front page, screenshot and composer
behavior description. It keeps the Pacific Operations design, production models,
source authority and existing corpus/index unchanged.

## Evidence and integration

Remote main was `ae975132c5d65800c1e960c7b6e0c46844959dfe` at integration preflight
and is an ancestor of the candidate. No remote commits require conflict resolution.
The accepted release packet SHA-256 is
`aa4bac2ececb46c07ba2b96a1f8f366319a3b8360b5ffb4b04d26b402dccaef5`.

The [System Card](../system-card/FIRELENS_SYSTEM_CARD.md) records the accepted
12 fresh and nine retained external cases, scoped local and fixture browser
checks, dated official snapshots and historical core **FAIL 565/574**.
No human usability study, sealed generalization or sustained availability/SLO is
established. The README image is synthetic demonstration data.

Fresh source-identical built-stack inspection passed at 1536px, 390px and
320px, including selected-source identity and Home/reset. Native browser zoom
reported factor 2, DPR 1 to 2 and layout width 1280 to 640 with no horizontal
overflow; the bottom composer remained usable. This is automated fixture
evidence, not human accessibility assessment.

The frozen integrated candidate `fc5731ee8d8ad1ae35d15fe00291f0c7c7bdba07`
has tree `d7fe25851da2c2876a377d1350e7a6f103ab152b`, identical to the production
merge tree. Fresh `make verify` passed: 2,581 backend tests, 13 skips and 709
subtests in each of its two backend passes; 198 frontend tests; 45 mocked browser
passes and one skip; documentation, type, format, lock and secret checks.
The separate current built-stack gate passed 22 tests.

A separate read-only AI reviewer accepted that frozen candidate for main and
production in one preproduction review iteration. Coordinator and reviewer
session configuration both reported `gpt-6-astra` with `xhigh` effort; realized
internal effort is unobservable. This acceptance preceded actual production
testing and does not supersede the failed current-source check above.

Current main CI is also **not green**. The
[verification run](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/33998174672)
passed canonical local verification and ProductBench, then failed the source-aware
conversation step. A fresh local reproduction passed 105/106: `SA-GQ-14-P3`
returned a conservative scope redirect for a pet evacuation packing question
instead of the expected supported partial quotation. The
[candidate-evidence run](https://github.com/yusenrong46-afk/firelens-bc/actions/runs/33998174735)
refused its bundle because legacy hard-probe `J01` did not satisfy its migration
invariant; the missing upload was secondary. Neither branch protection nor checks
were changed or bypassed. The repository had no required merge checks. These
current failures are separate from the retained historical core 565/574 result.

## Actual production observations

Eight sequential public Ask requests ran in a fresh browser with no API, feed or
tile interception. Nearby Kelowna records, selected Bradley Creek FSR follow-up,
missing-origin clarification, grab-and-go guidance, significance, mixed safety,
ordinary uphill-fire background explanation and a fresh Kamloops query all
returned HTTP 200. HTTP success does not mean all eight tasks passed: the three
guidance-related requests failed current-document passage verification.

Selected-record identity and Home/reset behaved correctly. Missing personal origin
prompted clarification; the mixed response retained the personal-decision boundary.
Kamloops returned an explicitly qualified empty result, not an all-clear.
The ordinary background answer exercised actual planning, embedding, reranking
and Luna generation, confirmed by content-free provider logs for its trace.

Desktop, 390px and 320px views had no observed page exceptions or horizontal
overflow. Required assets and lazy JS/CSS chunks returned HTTP 200 and matched
the qualified local bytes; cache-disabled refresh succeeded. Real OpenStreetMap
tiles, attribution and map controls worked. Official evacuation records were
unavailable and the interface disclosed that condition. These are bounded
observations, not an availability or latency SLO, human accessibility assessment
or an actual cross-deployment old-tab test.

All eight request envelopes remain reserved because complete provider receipts
were not available: **USD 1.799698578 additional exposure**, for conservative
cumulative exposure **USD 2.262765780** including all prior receipts and unknown
reservations. One background-generation component reported USD 0.00022352; that
partial observation is already covered by the reservation and is neither a whole
query price nor a reason to release unverified reservations.

## Remaining work

- Review the updated official source under valid publication authority, rebuild
  the affected corpus/index and proof, and requalify affected guidance paths.
- Resolve the current source-aware pet-guidance failure and legacy J01 candidate
  evidence refusal in a separately scoped effort; preserve frozen expectations.
- Retain the documented historical failures and unestablished human, sealed-test
  and sustained-availability limits.

## Release constraints

Use the canonical deployment wrapper with `--generation-provider-only azure/eu`.
Generation and embedding require ZDR, reranking ZDR is optional, data collection
is denied and fallback disabled. Reuse the approved production inference secret.
Production verification must use real public requests without Ask, feed or tile
fixtures. A ready deployment alone is not a successful release.

The successor permits USD 2 additional campaign exposure within the cumulative
USD 10 ceiling. Prior settled receipts are USD 0.087233700 and uncertain
reservations USD 0.375833502, preserved independently of lower server snapshots.
These are campaign totals, not per-query prices or total development costs.

Rollback restores the prior deployment through the existing Vercel process,
including only relevant nonsecret configuration changes. Deployment rollback
does not revert Git history. Private raw evidence stays outside this repository.
The verified rollback target remains build `40c4c970` and deployment
`dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh`; no rollback or corrective deployment was used.
