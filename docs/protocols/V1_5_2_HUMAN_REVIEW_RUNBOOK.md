# FireLens V1.5-2 human-review runbook

Status: frozen operational draft; no human review is complete merely because this file or a
workspace exists.

This runbook governs five separate review tracks: semantic quality, retrieval labels,
accessibility, product safety, and task-level UX. Human judgments remain the authority. Automated
validators may check identity, completeness, and arithmetic, but they must not generate, infer, or
silently repair a person's decision.

## Evidence language

- **Prepared** means the inputs, protocol, named roles, and isolated workspace exist.
- **Executed** means the named people actually performed every required task.
- **Verified** means the retained artifacts replay and validate against the exact candidate.
- **Qualified** means every applicable frozen gate accepts the artifacts. A prepared workspace,
  API smoke test, synthetic decision, dry run, or automated accessibility scan is not qualified
  human evidence.

The current review-workspace implementation writes
`implementation_status=nonqualifying_backend_scaffold` and `qualification_eligible=false` into its
genesis, receipts, and final export. Do not manually copy its adjudication into a release-gate
sidecar. The implemented adapter is the only conversion path, and it remains fail-closed until an
independent storage review and externally retained final-head anchor are supplied.

## Required people and separation

Before a session starts, record real names and obtain consent for retained review evidence.

| Track | Required people | Separation rule |
| --- | --- | --- |
| Semantic | Reviewer A, Reviewer B, adjudicator | Three distinct people; reviewers cannot see each other's decisions before locking. |
| Retrieval | Reviewer A, Reviewer B, adjudicator | Three distinct people; no one may inspect retrieval rankings or model output. |
| Accessibility | Accessibility specialist | Must perform the frozen manual profiles; automated scans are supplemental. |
| Product safety | Wildfire product-safety reviewer | Must review false reassurance, source/freshness clarity, consent, and emergency escalation. |
| Frontend release | Release adjudicator | Distinct from both specialists; verifies exact-candidate evidence and open findings. |
| UX | At least 12 consented participants plus facilitator | Participant IDs are pseudonymous; facilitator does not rewrite outcomes. |

The release adjudicator should not be the semantic/retrieval adjudicator when practical. No model,
including a fine-tuned judge, can occupy any human role in this table.

## Workspace boundary

Review workspaces must live outside the repository. They can contain private paths, capability
tokens, reviewer notes, and later private holdout commitments. Never commit, upload, paste into an
issue, or attach the workspace to a pull request.

The preparation command creates one `0600` capability file per actor. Give each person only their
own file using an owner-approved private channel. Do not paste tokens into chat or command history.
The local service accepts loopback clients only, disables CORS and API documentation, requires the
exact frozen Origin on writes, derives actor identity exclusively from the bearer capability,
bounds JSON bodies, suppresses access logs, and returns sanitized errors.

## 1. Semantic development review (50 cases)

Prerequisites:

1. Generate a complete 50-case `firelens_conversation_benchmark_report.v1_1` in
   `execution_mode=live_provider` for the exact candidate commit and configuration.
2. Confirm all dataset, corpus, vector, document-context, repair, configuration, and commit
   identities are present and current. The historical report presently under `output/benchmark/`
   is not current-candidate proof by its filename or prior existence.
3. Freeze this runbook and the candidate before opening the first case.

Prepare, using real names and an owner-controlled workspace path:

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-conversation \
  --workspace /absolute/private/firelens-semantic-review \
  --session-id semantic-v1-5-2-candidate-001 \
  --report /absolute/current-candidate-conversation-report.json \
  --reviewer-a-name "REAL PERSON A" \
  --reviewer-b-name "REAL PERSON B" \
  --adjudicator-name "REAL ADJUDICATOR" \
  --origin http://127.0.0.1:8765
```

`--nonqualifying-dry-run` is permitted only for workflow rehearsal. Its outputs can never establish
the semantic gate. Each reviewer must assess the answer, every atomic claim, all required concepts,
forbidden claims, and required limitations. After both reviewer journals lock, the adjudicator
resolves every case without being told model identity or automated verdict.

## 2. Retrieval-label review (47 cases)

Do not run this track on the currently exposed V2 holdout if it has already influenced tuning. The
recommended disposition in the V1.5-2 gate ledger is to retire it and create a new V3 sealed set;
the owner has not yet confirmed that decision. Until confirmation and a frozen V3 file, this track
remains not started.

The workspace importer accepts the reviewed dataset and governed corpus chunks only. It rejects
ranking reports and never presents retrieval scores, positions, model names, or candidate output.

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-retrieval \
  --workspace /absolute/private/firelens-retrieval-review \
  --session-id retrieval-v3-v1-5-2-001 \
  --dataset /absolute/frozen-v3-retrieval.yaml \
  --corpus "$PWD/data/processed/firelens_static_corpus.chunks.jsonl" \
  --corpus-manifest "$PWD/data/processed/firelens_static_corpus.manifest.json" \
  --reviewer-a-name "REAL PERSON A" \
  --reviewer-b-name "REAL PERSON B" \
  --adjudicator-name "REAL ADJUDICATOR" \
  --origin http://127.0.0.1:8765
```

For all 47 cases, judge whether the question was independently authored after the configuration
freeze, whether its answerability label is correct, and whether every declared acceptable-evidence
set is actually acceptable. Complete and lock this review before the one-time final retrieval run.

## 3. Private semantic holdout

Follow `docs/protocols/V1_5_2_SEMANTIC_HOLDOUT_FREEZE.md` first. The private payload stays outside
the repository. The public V3 manifest must predate candidate generation, remain source-disjoint
from development material, require double review, and match the candidate report commitments.

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-semantic-holdout \
  --workspace /absolute/private/firelens-holdout-review \
  --session-id semantic-holdout-v1-5-2-001 \
  --private-payload /absolute/private/semantic-holdout.json \
  --manifest "$PWD/data/evaluation/benchmark_v1_5_2_semantic_holdout.manifest.json" \
  --development-registry "$PWD/data/evaluation/benchmark_v1_5_2_semantic_development_registry.json" \
  --candidate-report /absolute/private/exact-candidate-holdout-report.json \
  --reviewer-a-name "REAL PERSON A" \
  --reviewer-b-name "REAL PERSON B" \
  --adjudicator-name "REAL ADJUDICATOR" \
  --origin http://127.0.0.1:8765
```

## 4. Serving, transitions, and final export

The frozen Origin determines the host and port; the service refuses a mismatch.

```bash
.venv/bin/python scripts/human_review_workspace.py serve \
  --workspace /absolute/private/firelens-semantic-review \
  --host 127.0.0.1 \
  --port 8765
```

In the reviewer's owner-approved browser, open the frozen Origin at `/review`, select only that
person's assigned capability JSON, and keep the tab open. The token stays in tab memory and is not
saved to browser storage. If the tab reloads after a case opens, select the same capability again;
the client can recover only that actor's already-open deterministic presentation and cannot advance
or switch cases.

The reviewer client must follow this irreversible sequence for each actor:

1. `GET /api/v1/review/progress`
2. `POST /api/v1/review/present` with `{}`
3. Render the complete response, rubric, claims, and local evidence; do not truncate safety text.
4. `POST /api/v1/review/acknowledge` with the `presentation_id` only after the display is complete.
5. `POST /api/v1/review/decision` once. Decisions cannot be edited or reopened.
6. Repeat; then each reviewer calls `POST /api/v1/review/lock` with `{}`.
7. Only after both locks, the adjudicator follows the same case sequence and calls
   `POST /api/v1/review/finalize` with `{}`.

The coordinator can monitor content-free progress without loading a capability or seeing another
person's decisions. The command rechecks the frozen inputs and every journal/receipt before it
reports per-role completion and the next allowed state; it never prints capability tokens:

```bash
.venv/bin/python scripts/human_review_workspace.py session-status \
  --workspace /absolute/private/firelens-semantic-review
```

Export and reverify the receipt-bound evidence:

```bash
.venv/bin/python scripts/human_review_workspace.py export-finalized \
  --workspace /absolute/private/firelens-semantic-review

.venv/bin/python scripts/human_review_workspace.py verify-export \
  --workspace /absolute/private/firelens-semantic-review

.venv/bin/python scripts/human_review_workspace.py analyze-finalized \
  --workspace /absolute/private/firelens-semantic-review

.venv/bin/python scripts/human_review_workspace.py verify-analysis \
  --workspace /absolute/private/firelens-semantic-review
```

The export intentionally remains nonqualifying. Independently retain its SHA-256 and byte count
outside the workspace before any release-side conversion. The analysis is also nonqualifying. It
recomputes disposition, rubric, and claim agreement; Cohen's kappa where mathematically defined;
disagreement and adjudicated-finding case rosters; adjudicator alignment; and unsupported/unclear
claim counts. It binds each case to all three decision-event hashes while excluding questions,
answers, source text, and reviewer notes. A high agreement score cannot override any adjudicated
finding, and a degenerate kappa is reported as undefined rather than converted to a perfect score.
Pause experimentation when disagreement shows the rubric is unstable; do not tune against reviewer
differences before adjudication and owner disposition.

The release-side adapter remains fail-closed until a fourth named human, distinct from all session
actors, reviews the private storage boundary and confirms that the final journal head is retained in
an owner-controlled external system. Generate a hash-bound blank attestation only after export and
analysis verification:

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-storage-attestation \
  --workspace /absolute/private/firelens-semantic-review \
  --output /absolute/private/storage-attestation.yaml
```

The independent reviewer must inspect the workspace permissions, symlink/hard-link protections,
journal/receipt replay, export/analysis recomputation, and external anchor. They then fill the
identity, timestamp, anchor reference, checks, and decision directly. A session actor cannot sign
this attestation. If any adjudicated finding remains, conversion is refused even with an approved
storage attestation.

After the independent review, create and reverify the content-free qualification package outside
the repository:

```bash
.venv/bin/python scripts/human_review_workspace.py qualify-finalized \
  --workspace /absolute/private/firelens-semantic-review \
  --storage-attestation /absolute/private/storage-attestation.yaml \
  --output-dir /absolute/private/semantic-qualification

.venv/bin/python scripts/human_review_workspace.py verify-qualification \
  --manifest /absolute/private/semantic-qualification/review-qualification.json \
  --source /absolute/current-candidate-conversation-report.json \
  --sidecar /absolute/private/semantic-qualification/review-sidecar.yaml \
  --summary /absolute/private/semantic-qualification/review-summary.json \
  --storage-attestation /absolute/private/storage-attestation.yaml \
  --suite-kind conversation \
  --case-count 50
```

The manifest retains all three actor identities and journal heads, independent storage-review
identity, external-anchor reference, disagreement/finding counts, and hashes for the source,
private export, analysis, sidecar, and summary. It contains no questions, answers, passages, or
notes. Retrieval uses the same sequence with `--suite-kind retrieval --case-count 47` and the frozen
reviewed dataset as `--source`.

## 5. Accessibility and product-safety review

Use the exact after-candidate and the frozen protocol
`data/evaluation/frontend_manual_review.v1.yaml`. The accessibility specialist must complete the
desktop Chromium keyboard, desktop Safari VoiceOver, and mobile Safari VoiceOver/touch profiles.
The wildfire product-safety reviewer must complete both desktop and mobile safety profiles. The
distinct release adjudicator must reconcile the exact 30 atomic checks, 50 profile/state cells,
hash-bound evidence roster, and open findings.

After the candidate has an exact commit and a local or preview origin, create the private blank
packet outside the repository. The command binds the complete frozen roster and the three named
humans, but deliberately records no pass/fail result, evidence, attestation, or adjudication:

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-frontend-manual \
  --workspace /absolute/private/path/frontend-manual-review \
  --commit <40-character-candidate-commit> \
  --target-url https://candidate.example \
  --accessibility-reviewer-id <pseudonymous-id> \
  --accessibility-reviewer-name "<named accessibility specialist>" \
  --accessibility-credentials "<relevant credentials>" \
  --safety-reviewer-id <pseudonymous-id> \
  --safety-reviewer-name "<named wildfire product-safety reviewer>" \
  --safety-credentials "<relevant credentials>" \
  --release-adjudicator-id <pseudonymous-id> \
  --release-adjudicator-name "<named independent adjudicator>" \
  --release-adjudicator-credentials "<relevant credentials>"
```

The generated file is mode `0600`, its evidence directory is mode `0700`, and rerunning against an
existing path is refused. Complete the null fields only from direct observation of the bound
candidate. Keep retained evidence outside Git and let the after-capture validator recompute the
final accessibility, product-safety, and open-finding results.

Before after-capture, verify the completed bundle and exact commit directly:

```bash
.venv/bin/python scripts/human_review_workspace.py verify-frontend-manual \
  --bundle /absolute/private/path/frontend-manual-review/frontend_manual_review.completed.yaml \
  --commit <40-character-candidate-commit>
```

Required state coverage is: idle, grounded, partial, abstention, provider failure, live, mixed,
stale, no result, and partial layer. Evidence must include the exact candidate identity, target URL,
viewport/profile, timestamp, finding IDs, media type, byte count, and SHA-256. Accessibility is not
qualified by Lighthouse, axe, Playwright, screenshots, or a keyboard-only check alone. Product
safety is not qualified by generic content review.

The release comparator must report all of the following on the same candidate:

- `frontend_manual_accessibility_qualified=true`
- `frontend_manual_product_safety_qualified=true`
- `frontend_manual_open_findings=0`

## 6. UX review (12 or more participants per round)

Use the frozen five tasks in `data/evaluation/upgrade_benchmark_v1_5_2.yaml` and the generated
`ux_tasks.template.yaml` from the before/after snapshot. Run the same protocol before and after.
Recruit at least four novice BC residents and four wildfire-aware participants, with at least three
mobile and three desktop participants. Retain keyboard and screen-reader access-method coverage as
UX slices, not as a substitute for the specialist accessibility review.

The same blank 12-participant/60-attempt matrix can be prepared independently of a benchmark run:

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-ux-template \
  --output /absolute/private/path/ux-before.yaml \
  --label before
```

Use `--label after` for the independent after cohort. The template freezes the minimum cohort,
device, access-method, and task matrix while leaving every observed outcome and score null. Before
validation, bind the exact commit and deployment, name the human moderator, record the observation
timestamp, and complete every participant/task row. The validator rejects placeholder/model
moderators, unknown device/access values, extra hidden fields, incomplete rows, and noncanonical
candidate identity.

Verify each completed round before benchmark capture:

```bash
.venv/bin/python scripts/human_review_workspace.py verify-ux-report \
  --report /absolute/private/path/ux-before.completed.yaml
```

Standalone verification recomputes the round but remains nonqualifying; only the paired benchmark
comparison can establish the before/after UX disposition.

For every participant/task pair, record each frozen criterion result, any frozen critical-error
codes plus an observation note, capped duration, SEQ, confidence, and the observed outcome. The v3
validator derives completion from the criterion results and critical-error roster; it does not
accept a moderator-entered completion boolean. An unsuccessful Near Me attempt is scored at the
frozen 120-second cap. A participant interpreting stale, partial, unavailable, or no-result output
as confirmation of safety is a critical error. Do not remove outliers after seeing the result. The
before/after cohort and device share delta must remain at or below 0.15.

Qualification requires at least 90 percent aggregate task completion, zero critical errors,
complete participant/task coverage, reported task/cohort/device/access-method slices, and
exact-candidate identity. The derived report includes Wilson intervals, worst core-cohort and
device slices, a seeded participant bootstrap for each round, and an independent-cohort bootstrap
for the before/after completion and Near Me effects. When the Near Me interval crosses or reaches
zero, report only an observed sample difference rather than an established improvement.

## Stop conditions

Stop and preserve evidence without qualifying when any of these occurs:

- a reviewer identity is missing, duplicated, or replaced by a model;
- a reviewer sees a ranking, automated verdict, provider/model identity, or another reviewer's
  unlocked decision;
- input, protocol, candidate, journal, capability, receipt, or evidence identity changes;
- any review case is skipped, reopened, silently repaired, or copied from a dry run;
- the accessibility, safety, UX, and release roles are conflated;
- the frontend review targets a different commit or deployment than the benchmark candidate;
- a critical safety/UX error or unresolved manual finding remains; or
- someone proposes pushing or promoting before the no-push examination and owner approval.
