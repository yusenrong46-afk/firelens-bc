# FireLens BC V1.5 V3 final engineering ledger

Updated: 2026-08-15 (America/Vancouver)

This ledger is the durable issue record for the final engineering pass on
branch `codex/v1-5-v3`. Status values:

- `OPEN` — reproduced or required, not yet closed with executed evidence
- `TEST_WRITTEN` — failing or characterization test exists
- `FIXED` — patch applied; focused tests executed
- `VERIFIED` — focused plus affected suite executed on this worktree
- `EXTERNAL` — needs paid access, deployment, human review, or missing auth
- `WONT_CHANGE` — inspected, out of V1.5 V3 product scope, with rationale

Do not mark closed from source inspection alone. Automated checks are
engineering evidence only. They are not human review, deployed evidence, or
ISO/WCAG/ASVS/SLSA/privacy certification.

Standards below are requirement sources, not certifications. Access date for
all external references in this file: **2026-08-15**.

## Repository identity at start of this pass

| Field | Inspected value |
| --- | --- |
| Branch | `codex/v1-5-v3` |
| HEAD | `fbfb5d383f76068a9f6458f6939341f3308f19b5` |
| Message | Bypass model planning for reviewed guidance |
| Worktree | Dirty: 50 modified tracked files, 19 untracked production/test/docs files |
| Diff stat | 3699 insertions, 817 deletions across 50 tracked files |
| Frozen V1 catalog SHA-256 | `22c14123c5b8868bcd315167836f38f3a7b5daa56913452d13b17edff2c427a5` (162 cases) |
| Dirty `config/runtime_candidate.v1.json` | Gitignored generated file; `schema_version=firelens.runtime_candidate.v2`; `release_version=1.5.3-rc.1`; `require_zdr=true`; `build_commit` **does not equal HEAD** |
| Secret scan (tracked) | Passed (`make secret-scan` / `scripts/secret_scan.py`) |
| Secret scan (19 untracked) | No matches using the same detector |

The dirty candidate is **not** the final commit identity. Deployment packaging
must generate a candidate bound to the exact committed artifact at build time.
A circular “commit contains its own SHA” file is not tracked.

## Recovery method

Secret scan ran **before** the recovery artifact.

| Method | Location | Identity |
| --- | --- | --- |
| Local recovery branch (not pushed) | `recovery/v1-5-v3-pre-clean-20260815` | `c1babddfb3ba3bb1c31df17c911a1a9be9f0867f` |
| Git bundle + tracked patch + untracked copies | `tmp/v1-5-v3-recovery-20260815/` (gitignored) | See `IDENTITY.txt` and `RECOVERY_COMMIT.txt` |

Recovery excludes `.env`, traces, questions/answers, precise locations, and
the dirty generated candidate. The working tree and `HEAD` were left unchanged
when the recovery commit was created via a temporary index.

## Phase cards

### Phase 1 — Preserve and clean

- **Objective:** Recover the dirty worktree, classify every change, keep
  generated candidate gitignored, commit by issue family, do not push.
- **Inspected evidence:** `git status`, `git diff --stat`, `.gitignore`,
  `scripts/secret_scan.py`, `Dockerfile`, `scripts/prepare_vercel_build.py`,
  `scripts/write_runtime_candidate.py`, `src/firelens/runtime_candidate.py`.
- **Acceptance tests:** Secret scan before recovery; recovery commit exists;
  worktree still on `codex/v1-5-v3`; no secrets in recovery; candidate file
  remains gitignored.
- **Risks:** Accidental deletion of unreviewed production files; committing
  caches/test-results; treating dirty candidate SHA as release identity.
- **Files:** See classification table.
- **Commands:** `git rev-parse`, `git status`, `.venv/bin/python scripts/secret_scan.py`,
  recovery `git commit-tree` / `git bundle create`.
- **Stop conditions:** Do not `git reset --hard`; do not push; do not copy `.env`.
- **Verdict:** recorded after the Phase 1 commits in this pass.

### Phase 2 — Heavy debugging

- **Objective:** Broad ordinary-user matrix (≥250 single-turn, ≥60 multi-turn)
  on zero-cost FakeProvider / deterministic intent / live answering paths.
- **Inspected evidence:** existing V3 intent/composition tests, product-question
  catalog (frozen 162), V3 regressions (separate family).
- **Acceptance tests:** New exploratory roster tests; do not mutate frozen
  catalog SHA; paid OpenRouter calls forbidden.
- **Risks:** Weakening thresholds; storing private user content; treating
  FakeProvider pass as semantic qualification.
- **Stop conditions:** No paid calls; no frozen-catalog rewrite.
- **Verdict:** pending execution.

### Phase 3 — UI/UX

- **Objective:** One map-first assistant; connected conversation/map/evidence;
  distinguishable authority; recovery language; keyboard/zoom/contrast evidence.
- **Acceptance tests:** Vitest, Playwright, browser screenshots. VoiceOver
  human review remains EXTERNAL.
- **Stop conditions:** No accounts, notifications, saved locations, or
  persistence. No second primary mode.
- **Verdict:** pending browser evidence.

### Phase 4 — Performance

- **Objective:** Measure before changing. Laboratory budgets only.
- **Acceptance tests:** Bundle gzip sizes, interaction/LCP proxies, backend
  cached-live timing if locally measurable without paid providers.
- **Stop conditions:** Revert speculative changes without measured improvement.
  Do not change embedding/reranker.
- **Verdict:** pending measurement.

### Phase 5 — Pre-deployment (no deploy)

- **Objective:** Local reversible rehearsal: build, OpenAPI, Docker path,
  Vercel packaging, health, ZDR fail-closed, runbook, env inventory without
  values.
- **Stop conditions:** Do not deploy, push, merge, spend money, or perform
  human review. Production remains blocked while configured reranker is not
  proven ZDR-eligible **and** retrieval-qualified.
- **Verdict:** pending rehearsal.

## File classification (dirty worktree)

### Production source

| Path | Notes |
| --- | --- |
| `src/firelens/answering/live_composition.py` | Untracked; mixed live+static composition |
| `src/firelens/answering/live_distance.py` | Untracked |
| `src/firelens/answering/live_handoffs.py` | Untracked; official unsupported-topic links |
| `src/firelens/answering/live_request_intent.py` | Untracked |
| `src/firelens/answering/live_response_support.py` | Untracked |
| `src/firelens/api_contracts.py` | Untracked; OpenAPI composition helper |
| `src/firelens/deployment_gates.py` | Untracked |
| `src/firelens/runtime_candidate.py` | Untracked; v2 candidate bind/generate |
| `src/firelens/answering/{intent,location_intent,grounded,validate,service,context}.py` | Modified |
| `src/firelens/live_answering.py` | Modified; split toward new modules |
| `src/firelens/agent/coordinator.py` | Modified |
| `src/firelens/contracts.py` | Modified; 800-line ceiling |
| `src/firelens/api/factory.py` | Candidate binding at startup |
| `src/firelens/config.py` | `DEFAULT_RELEASE_VERSION` |
| `src/firelens/runtime.py` | Candidate apply |
| `src/firelens/runtime_artifact.py` / `_common.py` / `_comparison.py` | v2 identity fields |
| `apps/web/src/features/ask/{ConversationPanel.tsx,useFireLensSession.ts,abstentionPresentation.ts,answerSections.ts}` | UI |
| `apps/web/src/features/near-me/{LiveMap.tsx,LiveRecordLists.tsx,liveResultPresentation.ts}` | Map/list split |
| `apps/web/src/features/evidence/EvidencePanel.tsx` | Evidence |
| `apps/web/src/app/styles.css` | Presentation |
| `Dockerfile`, `render.yaml`, `scripts/prepare_vercel_build.py`, `scripts/write_runtime_candidate.py`, `scripts/qualify_deployment_gates.py` | Packaging / gates |

### Generated contract

| Path | Notes |
| --- | --- |
| `docs/openapi.v1.json` | Backend contract source for frontend |
| `apps/web/src/shared/api/api-schema.d.ts` | Generated types |
| `apps/web/src/shared/api/api.ts` | Thin re-exports including `AnswerSection` |

### Tests

All `tests/test_*.py` modifications and new V3/deployment/candidate tests;
`apps/web/tests/**` modifications.

### Documentation

`README.md`, `docs/plans/V1_5_V3_IMPLEMENTATION.md`,
`docs/releases/V1_5_V3_RUNBOOK.md`,
`docs/audit/V1_5_V3_HUMAN_REVIEW_HANDOFF.md`, this ledger.

### Gitignored generated / runtime (do not commit)

| Path | Classification |
| --- | --- |
| `config/runtime_candidate.v1.json` | Build-time generated candidate; dirty SHA ≠ HEAD |
| `.env`, `.env.local` | Secrets |
| `apps/web/dist/`, `apps/web/node_modules/`, `apps/web/test-results/` | Build/cache/browser output |
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` | Tooling |
| `output/`, `tmp/`, `data/raw/*` extras, traces | Runtime / local data |

### Immutable fixture (must not change)

`data/evaluation/product_question_probe.v1.json` catalog identity SHA-256
`22c14123c5b8868bcd315167836f38f3a7b5daa56913452d13b17edff2c427a5`.

## Runtime candidate identity (CLEAN-002)

`config/runtime_candidate.v1.json` is listed in `.gitignore`. Docker and Vercel
packaging **generate** it:

- `Dockerfile` `RUN python scripts/write_runtime_candidate.py --commit "${FIRELENS_BUILD_COMMIT:-$RENDER_GIT_COMMIT}"`
- `scripts/prepare_vercel_build.py` uses `VERCEL_GIT_COMMIT_SHA` or `git rev-parse HEAD`

`build_runtime_candidate()` binds `candidate_id` to `{benchmark}:{40-char SHA}`.
The dirty local file is a previous local generation and must not be treated as
the committed release identity. Tests in `tests/test_runtime_candidate_build.py`
and `tests/test_runtime_candidate_binding.py` encode this.

## External reference translation (accessed 2026-08-15)

These become ledger items. They are **not** compliance claims.

| Source | Applicable requirement | Ledger ID |
| --- | --- | --- |
| [BCWS app reference guide](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/appreferenceguide) | Official app is a dashboard+map with saved locations, notifications, fire bans, danger, smoke forecast, road events, report-a-fire. FireLens V3 remains one assistant, not a clone. Evacuation data may lag local authority. | UX-EXT-001, WONT_CHANGE saved-locations |
| [BCWS disclaimer](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/disclaimer) | Live data is general reference, not a risk/insurance tool; perimeters/evacuations can be incomplete; coordinates approximate. | REL-001, DBG safety empty-result language |
| [Watch Duty overview](https://www.watchduty.org/how-it-works/overview) | Crowdsourced reports and alerting are a different product. Do not add. | UX-EXT-002 |
| [Frontline Wildfire app](https://www.frontlinewildfire.com/frontline-wildfire-app/) | Hardware/alerting product; out of scope. | UX-EXT-003 |
| [ISO 27001:2022 (ISO 78176 page)](https://www.iso.org/standard/78176.html) | ISMS certification is organizational; not claimed. Map access control, logging, and supplier (OpenRouter) residual risk. | EXT-ISO-001 |
| [NIST SP 800-218 SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | PW (tests, review), PS (protect code), RV (respond). Local verify maps to PW.8 engineering tests only. | EXT-SSDF-001 |
| [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/) | L1-relevant: validation, output encoding, logging without sensitive data, sessionless anonymous API, rate limits. Full ASVS verification EXTERNAL. | EXT-ASVS-001 |
| [OWASP GenAI LLM Top 10](https://genai.owasp.org/llm-top-10/) | LLM01 injection, LLM02 disclosure, LLM05 output handling, LLM06 agency, LLM08 embeddings, LLM09 misinformation, LLM10 consumption. 2026 list exists; 2025 categories still used as requirement source. | PRIV-LLM-001 |
| [SLSA v1.2](https://slsa.dev/spec/v1.2/) | Build provenance / protected build. Local Docker/Vercel generation is not a SLSA Build L2+ attestation. | EXT-SLSA-001 |
| [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr) | Production ZDR required; no non-ZDR fallback. Roster GET is zero-cost if no inference. | REL-ZDR-001 |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Keyboard, focus visible, name/role/value, status messages, 200% zoom, reflow, contrast, target size. Human AT review EXTERNAL. | UX-A11Y-001 |
| [Core Web Vitals thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds) | Good: LCP ≤2.5s, INP ≤200ms, CLS ≤0.1. Laboratory proxies ≠ field p75. | PERF-001 |
| [OPC mobile/digital guidance](https://www.priv.gc.ca/en/privacy-topics/technology/mobile-and-digital-devices/mobile-apps/gd_app_201210/) | Minimize collection; no persistence of precise location; purpose limitation; transparency. | PRIV-001 |
| [OTel HTTP semconv](https://opentelemetry.io/docs/specs/semconv/http/) | If emitting HTTP telemetry, do not put questions/answers/precise location in span attributes. Current product forbids content tracing in production. | PRIV-002 |
| [xAI Grok Build CLI](https://x.ai/news/grok-build-cli) | Engineering-agent workflow: inspect, test, stop before external gates. | CLEAN-PROC-001 |
| [xAI GOAL](https://x.ai/news/introducing-goal) | Goal-conditioned execution; keep acceptance frozen before patches. | CLEAN-PROC-001 |
| [xAI structured outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs) | Model proposes structured drafts; validators remain authoritative. | DBG-AUTH-001 |
| [xAI function calling](https://docs.x.ai/developers/tools/function-calling) | App owns tool schemas and executes tools; model cannot select a different provider or arbitrary tools. | DBG-AUTH-001 |

## Issues

### CLEAN-001 — Dirty production worktree at start

- **Severity:** P2
- **Reproduction:** `git status --porcelain` on `codex/v1-5-v3` at `fbfb5d3` shows 50 modified and 19 untracked files.
- **Expected:** Reviewable commits by family; clean worktree of intended production/test/docs changes.
- **Actual:** Uncommitted prior-agent production work.
- **Root cause:** Sequential engineering on a dirty branch without family commits.
- **Fix:** Recovery snapshot, then local commits by family. Do not push.
- **Tests added:** None (process).
- **Commands executed:** `git status`, `git diff --stat`, recovery branch create.
- **Evidence:** inspected, executed (recovery).
- **Disposition:** OPEN until post-commit `git status` is clean of intended files.

### CLEAN-002 — Gitignored candidate is not commit identity

- **Severity:** P1
- **Reproduction:** `config/runtime_candidate.v1.json` exists, is gitignored, `build_commit != HEAD`.
- **Expected:** Deployment build generates a candidate bound to the exact committed artifact SHA.
- **Actual:** Local dirty file bound to a different SHA; file is correctly gitignored.
- **Root cause:** `src/firelens/runtime_candidate.py::build_runtime_candidate` plus gitignore of `CANDIDATE_RELATIVE_PATH`.
- **Fix:** Keep gitignored; Docker/Vercel writers remain the source of deployed identity. Document in runbook.
- **Tests added:** already in `tests/test_runtime_candidate_build.py`, `tests/test_runtime_candidate_binding.py` (uncommitted at start).
- **Evidence:** inspected.
- **Disposition:** OPEN pending executed packaging tests after commit.

### CLEAN-003 — Browser/test artifacts must stay untracked

- **Severity:** P3
- **Reproduction:** `apps/web/test-results/.last-run.json` exists and is gitignored.
- **Expected:** Not committed.
- **Actual:** Present locally, ignored.
- **Root cause:** Playwright local output.
- **Fix:** Do not add. No deletion of uncertain files.
- **Evidence:** inspected.
- **Disposition:** VERIFIED for ignore rule (`.gitignore` lines 20–21); file presence is local-only.

### REL-ZDR-001 — Production ZDR fail-closed; reranker not dual-qualified

- **Severity:** P0
- **Reproduction:** Production config with `require_zdr=true`; configured rerank `cohere/rerank-4-pro`. Last account check (prior pass, stale until re-verified) did not list that reranker on ZDR roster. `qwen/qwen3-reranker-8b` appeared roster-eligible but is **not** retrieval-qualified. Switching reranker is forbidden.
- **Expected:** Production starts only if every bound stage is on the current ZDR roster **and** the reranker is retrieval-qualified.
- **Actual:** Engineering fail-closed code exists; live roster + retrieval qualification are EXTERNAL.
- **Root cause:** Provider roster vs frozen retrieval holdout are independent gates.
- **Fix:** Keep fail-closed. Do not switch models. Zero-cost roster GET allowed later if no inference cost and keys are not printed.
- **Tests:** `tests/test_runtime_candidate_binding.py::RuntimeCandidateStartupTests.test_production_lifespan_fails_when_reranker_is_zdr_ineligible`; OpenRouter privacy tests in `tests/test_provider_api.py`.
- **Evidence:** inspected; roster re-check EXTERNAL.
- **Disposition:** EXTERNAL for live roster and retrieval qualification; engineering fail-closed remains required.

### REL-001 — BCWS disclaimer: live data is not a safety determination

- **Severity:** P0
- **Reproduction:** Any empty/stale/partial live answer that could be read as “all clear”.
- **Expected:** No-result and stale states never imply safety; disclaimer-aligned limitations remain.
- **Actual:** V3 scoring already flags unsafe empty-result language (`product_question_cli._score`).
- **Root cause:** Product-safety copy vs official dynamic data.
- **Fix:** Preserve limitations; expand exploratory roster coverage.
- **Evidence:** inspected (source + tests). Not closed until exploratory run executes.
- **Disposition:** OPEN.

### DBG-AUTH-001 — Models propose; app owns tools and validation

- **Severity:** P0
- **Reproduction:** Agent tool surface in `src/firelens/agent/coordinator.py`; structured drafts in answering pipeline.
- **Expected:** Model cannot execute arbitrary tools or pick another provider; validators remain authoritative.
- **Actual:** Implementation contract and coordinator exist in dirty worktree.
- **Root cause:** V3 agent design.
- **Fix:** Keep bounded tools; add adversarial exploratory cases for jailbreak/tool hijack.
- **Evidence:** inspected.
- **Disposition:** OPEN pending exploratory execution.

### PRIV-001 — No persistence of questions, answers, precise location, query hashes

- **Severity:** P0
- **Reproduction:** Production config and OPC-style purpose limitation.
- **Expected:** Round coordinates to two decimals; no content tracing.
- **Actual:** Product rules already encode this; production probes EXTERNAL.
- **Evidence:** inspected.
- **Disposition:** OPEN for local privacy probes; EXTERNAL for deployed origin.

### PRIV-002 — Telemetry must not carry content

- **Severity:** P1
- **Reproduction:** OTel HTTP semconv would otherwise allow `http.request.body` style attributes.
- **Expected:** Production content tracing off; no questions/answers/precise location in logs.
- **Actual:** Runbook says keep content tracing off. Local proof pending.
- **Evidence:** inspected.
- **Disposition:** OPEN.

### PRIV-LLM-001 — LLM Top 10 mapped controls

- **Severity:** P1
- **Reproduction:** Prompt-injection, output handling, excessive agency, unbounded consumption.
- **Expected:** Deterministic prohibited/policy patterns; validated outputs; app-owned tools; rate/size limits.
- **Actual:** Patterns in `intent.py`; validation in `validate.py`; request guards exist.
- **Evidence:** inspected.
- **Disposition:** OPEN pending exploratory adversarial slice.

### UX-A11Y-001 — WCAG 2.2 applicable engineering checks

- **Severity:** P1
- **Reproduction:** Keyboard, 200% zoom, narrow reflow, contrast, 44px targets, status names.
- **Expected:** Engineering browser evidence; VoiceOver human review EXTERNAL.
- **Actual:** Some Playwright coverage exists; visual quality not claimed from source.
- **Evidence:** not yet reproduced in this pass.
- **Disposition:** OPEN; VoiceOver EXTERNAL.

### UX-EXT-001 — Do not clone BCWS dashboard / saved locations / notifications

- **Severity:** P2
- **Reproduction:** BCWS app reference guide lists Dashboard, Saved (up to 3 locations), notifications, Report a Fire.
- **Expected:** FireLens stays one assistant with tools; no accounts/saved locations/notifications.
- **Actual:** Current App.tsx is conversation + evidence/map workspace.
- **Evidence:** inspected.
- **Disposition:** WONT_CHANGE for those official-app features (product scope).

### UX-EXT-002 / UX-EXT-003 — Watch Duty / Frontline features out of scope

- **Severity:** P3
- **Expected:** No crowdsourced reports or hardware alerting.
- **Disposition:** WONT_CHANGE.

### PERF-001 — Laboratory Web Vitals / bundle budgets

- **Severity:** P2
- **Reproduction:** Last known gzip sizes (prior pass, re-measure required): initial ~78.63 KiB, lazy map ~54.61 KiB.
- **Expected:** Re-measure after commits; keep/revert only with numbers.
- **Evidence:** not run in this pass yet.
- **Disposition:** OPEN.

### EXT-ISO-001 / EXT-SSDF-001 / EXT-ASVS-001 / EXT-SLSA-001

- **Severity:** P2
- **Expected:** Map requirements; do not claim certification.
- **Disposition:** EXTERNAL for independent audit/attestation; engineering mappings recorded above.

### TEST-001 — Frozen catalog must remain byte-identical

- **Severity:** P0
- **Reproduction:** `tests/test_product_question_cases.py::test_frozen_v1_artifact_is_not_rewritten_by_development_cases`.
- **Expected:** SHA-256 `22c14123c5b8868bcd315167836f38f3a7b5daa56913452d13b17edff2c427a5`, 162 cases.
- **Actual:** Test exists in dirty worktree; not executed yet in this pass.
- **Disposition:** OPEN pending execution.

### TEST-002 — Exploratory roster below required breadth

- **Severity:** P1
- **Reproduction:** Frozen catalog is 162 single-turn-ish cases plus 15 V3 structural regressions and 8 follow-ups. Assignment requires ≥250 single-turn and ≥60 multi-turn with expected **classes**.
- **Expected:** Separate non-sealed roster; FakeProvider/deterministic execution; sanitized results.
- **Actual:** Not present at start of this pass.
- **Root cause:** Prior work froze V1 catalog and added a small V3 regression family only.
- **Fix:** Add `v3_exploratory_roster` (name TBD) without rewriting the frozen artifact.
- **Evidence:** inspected.
- **Disposition:** OPEN.

## Command log (this pass, Phase 1 start)

| Command | Exit | Notes |
| --- | --- | --- |
| `git rev-parse --abbrev-ref HEAD` / `git rev-parse HEAD` | 0 | `codex/v1-5-v3`, `fbfb5d3…` |
| `git status --porcelain=v1` | 0 | Dirty as classified |
| `.venv/bin/python scripts/secret_scan.py` | 0 | Tracked secret scan passed |
| Untracked secret detector (same prefixes) | 0 | 19 files, no matches |
| Recovery `git commit-tree` + `git branch recovery/v1-5-v3-pre-clean-20260815` | 0 | `c1babdd…`; not pushed |
| `git bundle create tmp/v1-5-v3-recovery-20260815/recovery.bundle …` | 0 | Gitignored path |

Later phases append rows. Do not invent browser, performance, or human-review results.
