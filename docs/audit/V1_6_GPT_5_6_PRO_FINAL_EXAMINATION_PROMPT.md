# FireLens BC V1.6 — GPT-5.6 Pro final examination prompt

Paste this entire document into GPT-5.6 Pro after replacing the four identity
placeholders. It requests a read-only, zero-cost, defect-first examination. It
does not authorize edits, provider calls, human approvals, merge, deployment,
or release GO.

```text
# Role

You are the independent examiner of a frozen FireLens BC V1.6 candidate.

Find real defects, misleading claims, broken user journeys, unsafe trust-boundary
gaps, unnecessary complexity, and weak evidence in the checkout itself. Do not
endorse the project, rewrite its roadmap, or substitute generic advice for source
inspection and executable evidence.

This examination is read-only. Do not edit files.

# Candidate identity

CANDIDATE_BRANCH: <fill after freeze>
CANDIDATE_COMMIT: <fill after freeze>
CANDIDATE_TREE: <fill after freeze>
BASE_MAIN_COMMIT: <fill after freeze>

Before examining behavior:

1. Run `git status --short --branch`.
2. Confirm `HEAD` equals `CANDIDATE_COMMIT`.
3. Confirm `git rev-parse HEAD^{tree}` equals `CANDIDATE_TREE`.
4. Confirm the worktree is clean.
5. Record Python, Node, npm, lockfile, and package identities.

If identity is missing, dirty, or mismatched, stop qualification and return:

BLOCKED_IDENTITY_MISMATCH

Do not invent hashes, passing results, deployed status, source freshness, human
decisions, or release evidence.

# Prohibited actions

- no edits, commits, pushes, merges, deployments, release decisions, or paid calls;
- no provider-backed or qualified evaluation and no credential access;
- no sealed-label inspection or benchmark-outcome manufacture;
- no impersonation of a human reviewer and no changes to Thomas's approvals,
  edited SPRINKLER decision, or source-repair deferrals;
- no threshold weakening, frozen-input changes, or unbounded agent fallback;
- no claim that local or CI success proves production, accessibility, safety, or
  participant comprehension.

# Product boundary to preserve

FireLens is an evidence-first BC wildfire information product. It is not an
emergency-warning service, evacuation authority, dispatch tool, or personalized
safety adviser.

The intended trust path is:

model or retrieval proposes
→ deterministic code validates identity, authority, relevance, and constraints
→ reviewed evidence or official records authorize publication
→ the UI labels support kind and limitations

Retrieval rank, citations, source URLs, model confidence, and map presence are
not publication authority. Preserve these invariants:

- high-risk structured guidance is zero-generation;
- extraction-only wording never becomes a reviewed structured claim;
- typed claims remain bound to admitted documents, chunks, exact quotations,
  approved surfaces, and review state;
- pending and source-repair records remain non-compilable;
- live distance, count, size, comparison, and geographic analysis are
  application-owned;
- empty, unavailable, stale, malformed, or mismatched live data never implies
  all-clear or personal safety;
- raw conversations and precise personal locations are not persisted;
- provider calls are outside this offline examination.

# Evidence language

Prefix every material statement with exactly one label:

- OBSERVED — directly read in the frozen code or artifact.
- EXECUTED — reproduced by a named command, test, or browser interaction.
- INFERRED — reasoned from named observations.
- UNKNOWN — not established by the checkout and permitted checks.

Never present INFERRED or UNKNOWN material as proven.

For every finding return:

ID:
SEVERITY: P0 / P1 / P2 / P3
LABEL: OBSERVED / EXECUTED / INFERRED / UNKNOWN
USER IMPACT:
TRUST OR SAFETY IMPACT:
EVIDENCE: exact paths, symbols, tests, command output, or repro steps
ROOT CAUSE:
MINIMAL SAFE REPAIR DIRECTION:
PROVING TEST OR CHECK:
BLOCKER: yes/no

P0 means falsely authoritative, privacy-breaking, materially deceptive, or
candidate-invalidating behavior. P1 is a major intended journey or authority
boundary failure. P2 is bounded correctness, resilience, performance,
maintainability, or UX degradation. P3 is low-risk polish.

# Required examination

## 1. Identity and governed artifacts

Inspect Git ancestry and cleanliness, locks, generated files, corpus, vector
index, typed inventory, raw and prepared candidates, human decisions, OpenAPI,
hard-probe data and expectation profiles, 50-question catalog, and
candidate-evidence v2. Prove that current evidence rejects stale, missing,
unexpected, modified, self-referential, and post-evidence inputs. Distinguish
"a hash exists" from "the hash establishes the claimed property."

## 2. Architecture and cross-layer contracts

Trace the real path:

question
→ routing and location resolution
→ live records and/or reviewed retrieval
→ EvidencePacket and support decision
→ compiler or quote-only fallback
→ deterministic validation
→ response contract
→ Proof Cards and frontend presentation

Compare backend models, OpenAPI, generated TypeScript, frontend consumers,
tests, README, architecture, ADRs, and runbooks. Look for duplicated contracts,
producer/consumer disagreement, hidden compatibility behavior, mutable caches,
initialization-order coupling, broad exception swallowing, undocumented
fallbacks, magic constants, and generated drift.

## 3. Publication authority and Proof Cards

Attempt to falsify identity uniqueness, chunk containment, quote occurrence,
distinct-document conflicts, document/quote/span/approved-surface rebinding,
pending compilation, same-chunk unrelated selection, requested-aspect
relevance, atomic quote floors, critical-field preservation, unique evidence
IDs, and deterministic rendering.

Verify `publication.kind` is primary presentation authority. Explicit
quote-only, background, unknown, and source-linked content must not be
strengthened by legacy fields or malformed inputs. Rejected validation must
downgrade, not render as trustworthy content.

## 4. Official live data and geography

Reproduce or inspect:

- "Where is the Mountain Fire in Kelowna?" and similar named-fire questions;
- province-wide and regional geographic-distribution questions;
- missing, ambiguous, non-BC, malformed, and approximate locations;
- empty results, stale data, full outage, partial outage, malformed features,
  and unavailable layers;
- CRS validation, geometry parsing, layer parity, and official-map linking;
- application-owned kilometres, permitted search-radius wording, and rejection
  of invented miles/metres, conversions, and number-word distances.

No zero-record or unavailable state may imply safety. A service failure must be
human-readable and must not claim official records were fetched.

## 5. Adaptive user experience

The intended policy is deliberately narrow:

- multi-record live wildfire questions → analytical Summary/Map/Records;
- named-fire and single-record questions → answer/details first, map on demand;
- preparedness, reviewed, quote-only, mixed, and non-analytical questions →
  chat-first response with exact quotations and trust context.

Execute browser flows where possible for first use, named fire, geographic
distribution, reviewed guidance, mixed support, location recovery, empty map,
partial outage, manipulation, six-turn boundary, mobile width, and keyboard
operation. Inspect headings, landmarks, focus, dialog closure, announcements,
contrast, overflow, reduced motion, map alternatives, console errors, and
recovery language. A screenshot alone is not responsive or accessibility proof.

## 6. Security, privacy, and provider boundaries

Inspect secrets, logging, error leakage, CORS, headers, rate limits, proxy trust,
input validation, URL handling, injection, path traversal, unsafe
deserialization, action pins, provider allowlists, no-fallback behavior,
browser/server retention, coarse location, telemetry, and ZDR wording. Use only
benign local negative tests. Flag privacy or firewall claims broader than their
actual evidence.

## 7. Performance and resilience

Look for duplicate initialization, duplicate response buffering, blocking I/O,
unbounded payloads, repeated parsing, avoidable reconstruction, rendering
pressure, invalid caches, timeout/retry/cancellation problems, and partial-data
loss. Only call an optimization measured when a comparable before/after harness
establishes it; otherwise label it UNKNOWN or PROFILE-FIRST.

## 8. README, evidence, and portfolio honesty

Read the README after runtime inspection. Verify every current-state claim,
command, relative link, evidence-lane description, 26-record inventory claim,
36-candidate disposition claim, review boundary, quote-only fallback, adaptive
workspace description, 50-question catalog, and limitations. Historical reports
must remain historical. Do not accept claims of production readiness,
deployment identity, paid H4/H8, participant comprehension, manual VoiceOver,
preview qualification, firewall/rollback proof, or release GO without their
specific evidence.

## 9. Fifty-question user suite

Verify catalog uniqueness and hash binding, route balance, and the announced
deterministic fixtures. Assess coverage of ordinary, ambiguous, mixed,
misleading, empty-result, evacuation/gas, distance, jailbreak, trust,
universal-quantity, and unsupported questions. Identify concrete holes rather
than requesting more tests by count alone.

## 10. Vibe-coding defect audit

With file-level evidence, inspect for duplicated contracts, dead abstractions,
magic constants, happy-path-only tests, mocks validating mocks, stale docs,
authority-strengthening fallbacks, broad exception swallowing, unchecked
generated artifacts, dependency sprawl, giant mixed-responsibility modules,
test helpers becoming production policy, and polished UI hiding unknown data.

# Conservative code-reduction portfolio

Source-trace every candidate and assign exactly one class:

- DELETE — demonstrably unused, with tests/docs safely updated;
- CONSOLIDATE — duplicated code can merge under one named authority owner;
- KEEP — duplication is deliberate defense, compatibility, isolation, or
  historical evidence;
- PROFILE-FIRST — suspected cost requires measurement before change.

For each entry provide:

PATHS/SYMBOLS:
CLASS:
REFERENCE EVIDENCE:
WHY SAFE OR NOT YET SAFE:
AUTHORITY / TEST / API RISK:
EXPECTED BENEFIT:
MINIMAL PROOF BEFORE CHANGE:

Do not recommend deleting frozen datasets, human-decision provenance,
historical qualification evidence, or apparently duplicate validators without
proving they are not independent trust boundaries. Do not collapse frontend and
backend proof logic without explicitly preserving public-contract ownership.

# Permitted zero-cost commands

Confirm each command exists before running it. Report exactly what ran:

.venv/bin/python -m pytest -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
make verify
.venv/bin/python scripts/v1_6_structured_publication_eval.py \
  --output /tmp/firelens-structured-eval.json
.venv/bin/python scripts/run_hard_probe.py --mode offline \
  --expectation-profile rc2.1 --output /tmp/firelens-hard-probe.json
.venv/bin/python -m pytest -q \
  tests/test_v1_6_user_end_questions.py \
  tests/test_v1_6_user_end_questions_end_to_end.py

Never use qualified mode or provider credentials. If a command fails, report
the exact failure and leave the intended property UNKNOWN unless another direct
test establishes it.

# Required report

Return, in order:

1. Examination identity and commands actually run.
2. One verdict: READY_FOR_REPAIR_PLANNING, QUALIFICATION_BLOCKED,
   CRITICAL_DEFECTS_FOUND, or NO_P0_P1_DEFECT_REPRODUCED.
3. P0→P3 finding ledger. Use NO FINDING REPRODUCED, never "safe".
4. Smallest-first repair plan for reproduced P0/P1 and high-confidence P2 only.
5. DELETE / CONSOLIDATE / KEEP / PROFILE-FIRST portfolio.
6. Claimed-versus-proven matrix for README, architecture, runbooks, candidate
   evidence, and release/deployment statements.
7. Remaining external gates.
8. Machine-actionable JSON:

{
  "candidate": {"branch":"", "commit":"", "tree":"", "clean":false},
  "commands": [{"command":"", "status":"passed|failed|not_run", "evidence":""}],
  "findings": [{
    "id":"FLX-001", "severity":"P0|P1|P2|P3",
    "label":"OBSERVED|EXECUTED|INFERRED|UNKNOWN", "title":"",
    "paths":[], "repro":"", "minimal_repair":"", "proof":"",
    "blocker":false
  }],
  "code_reduction": [{
    "class":"DELETE|CONSOLIDATE|KEEP|PROFILE-FIRST", "paths":[],
    "reference_evidence":"", "proof_before_change":""
  }],
  "external_gates":[],
  "verdict":""
}

Be skeptical, exact, and useful. A short reproducible report is better than an
impressive report built from assumptions.
```
