# FireLens v1.6 product rescue — Final Summary

Date: 2026-09-03
Branch: `fable/firelens-product-rescue`

## 1. What did we learn (root causes)?
* Many “wrong answers” were not model failures: they were *contract failures* in routing/binding
  (mis-parsed clauses, unstable record identity, and missing authority boundary semantics).
* Evidence was present but sometimes not “first-class” in the UI (proof visibility + source attribution needed to be obvious).
* Some plain-language interpretation mistakes came from brittle phrase-splitting / scope detection (e.g. “B.C.” sentence boundaries; definition questions treated like record-focused anaphora).

## 2. What did we simplify (and preserve)?
* Simplified: one document flow; evidence inline; answer sections match clause outcomes; record selection + ordinal follow-ups bind deterministically.
* Preserved invariants:
  * No invented official facts/quotes.
  * Safety/authority boundaries are explicit and never treated as personalized decisions.
  * Live record presentation stays bound to fetched official records.
  * Unrelated questions get scoped notes instead of being answered with wildfire authority.

## 3. Deletions / trust boundaries
We moved complexity toward a small number of strong trust boundaries:
* “Understanding” (typed clauses + bound place/record reference)
* “Publication authority” (reviewed wording and exact quotes)
* “Handoff boundaries” (scope + safety + unavailable/unsupported)

## 4. RAG/UI/performance improvements
* RAG publication is now safer: when exact reviewed structured publication cannot be proven, we hand off rather than generate instruction-like prose.
* UI now presents sources inline and separates “what FireLens can establish” from “what it cannot.”
* Performance before/after measurement remains a pending quantification step.

## 5. Tests / gates (evidence of readiness)
* `make verify`: PASS
* Product Reality Gate (local, browser + API): 14/14
* NL mutation set: 50/50 passed
* ClaimBench v2: 332/332 correct; `unsafe_false_accept_rate = 0.0`
* Hard probe (offline rc2.2): 93/105 passed; `minimum_passed_met = true`
* Source-aware conversation: passed = true
* FireLens-200 focused: PASS/REVIEW only; FAIL = 0

## 6. Remaining imperfections
* FireLens-200 harness marks some cases for REVIEW only (quality polish rather than broken contracts).
* Performance measurement (before/after) still needs to be run.
* Preview deploy + preview reality gate are complete; production verification remains pending due to deploy permissions.

## 7. Deployment details
* Local verification is complete.
* Preview deploy + reality gate were completed successfully.
* Next: production deploy → run Product Reality Gate on production → smoke test production → rollback if any critical check fails.

