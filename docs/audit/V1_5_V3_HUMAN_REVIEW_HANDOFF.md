# FireLens BC V1.5 V3 human-review handoff

Updated: 2026-08-15

This handoff prepares named-human review. It does not record any human decision,
does not count a model as a reviewer, and does not qualify a release.

Status of this product after engineering work: **engineering-complete preview
candidate only**. It is not a human-qualified release. Production is no longer
blocked because Cohere Rerank 4 Pro lacks ZDR. Embedding and generation still
require ZDR. Cohere remains the retained retrieval-qualified reranker; Qwen
remains unqualified and must not replace it.

A later non-production preview of dirty HEAD `41f8d626` exists
(`dpl_8hN6LUL6mrjPq5MAGCVCqFnUTUyu`,
`https://firelens-npii22p3w-yusenrong46-9212s-projects.vercel.app`).
Zero-cost identity/ZDR gates passed. Engineering Ask worksheet rescore is in
`docs/audit/V1_5_V3_PREVIEW_ASK_WORKSHEET.md`. Named-human review has not
started. See `docs/audit/V1_5_V3_FINAL_ENGINEERING_LEDGER.md`.
Grok cannot occupy a reviewer role.

Automated checks, LLM analysis, Grok output, dry-run workspaces, and Playwright
journeys are advisory. They cannot occupy any role in the table below.

## Required tracks

Follow `docs/protocols/V1_5_2_HUMAN_REVIEW_RUNBOOK.md` for the frozen protocol,
workspace boundary, and stop conditions. Workspaces must stay outside Git.

| Track | What the humans decide | Launch |
| --- | --- | --- |
| Semantic review | Whether each bound answer, claim, required concept, forbidden claim, and limitation is acceptable | `prepare-conversation` |
| Safety-state review | False reassurance, source/freshness clarity, consent, and emergency escalation on the frozen frontend safety profiles | `prepare-frontend-manual` |
| Keyboard and screen-reader review | Frozen desktop Chromium keyboard, desktop Safari VoiceOver, and mobile Safari VoiceOver/touch profiles | same frontend-manual packet |
| UX review | Frozen five tasks with ≥12 consented participants; facilitator does not rewrite outcomes | `prepare-ux-template` |
| Final release adjudication | Exact-candidate evidence, open findings, and whether promotion is allowed | distinct release adjudicator, not a model |

Retrieval-label review for a *new* V3 sealed set remains blocked until the
owner confirms that freeze. That is not a statement that Cohere Rerank 4 Pro
is unqualified. Do not reuse an already-exposed holdout for that track. Do not
replace Cohere with Qwen.

## Launch commands

Replace every `REAL PERSON` / private path with owner-approved values. Do not
paste capability tokens into chat.

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-conversation \
  --workspace /absolute/private/firelens-semantic-review \
  --session-id semantic-v1-5-v3-candidate-001 \
  --report /absolute/current-candidate-conversation-report.json \
  --reviewer-a-name "REAL PERSON A" \
  --reviewer-b-name "REAL PERSON B" \
  --adjudicator-name "REAL ADJUDICATOR" \
  --origin http://127.0.0.1:8765
```

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

```bash
.venv/bin/python scripts/human_review_workspace.py prepare-ux-template \
  --output /absolute/private/path/ux-after.yaml \
  --label after
```

`--nonqualifying-dry-run` is rehearsal only. LLM or Grok comments on a packet
are advisory and must remain labelled as such; they cannot be copied into an
adjudication sidecar as a human decision.

## Frozen identity the reviewers must see

Confirm in the packet, not from this chat:

- Frozen V1 product-question catalog SHA-256
  `22c14123c5b8868bcd315167836f38f3a7b5daa56913452d13b17edff2c427a5`
- Bound runtime candidate schema `firelens.runtime_candidate.v3`, including
  stage privacy policy (`data_collection`, fallback, embedding/reranking/generation
  ZDR requirements), rerank model, and generation model
- Exact commit, release version, and official source links in the review inputs

Do not fill reviewer names, pass/fail cells, or adjudication records here.

## Later feedback track (not this pass)

A consented distill / DPO / GRPO student-model track remains future work.
This engineering pass does not persist production Ask questions, answers,
deterministic query hashes, or precise locations. Do not add an Ask logger
to satisfy that later track.
