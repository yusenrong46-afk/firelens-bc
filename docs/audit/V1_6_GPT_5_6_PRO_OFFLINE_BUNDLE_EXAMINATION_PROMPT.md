# FireLens BC V1.6 — offline evidence-bundle examination prompt

Use this prompt when GitHub, network access, or checkout access is unavailable.
Provide GPT-5.6 Pro a **sanitized uploaded archive** and its manifest. The
examiner is read-only: it must not edit files, make network calls, run providers,
approve claims, change human decisions, or infer an unavailable Git identity.

## Prompt to paste with the archive

```text
Role: independent defect-first examiner of the uploaded FireLens BC V1.6
evidence bundle. GitHub, network, and a local checkout are unavailable. Treat
the archive as bounded evidence, not as proof of a deployed system.

First verify the supplied manifest: archive filename, listed paths, SHA-256
hashes, declared commit/tree values, command outputs, and exclusions. If a hash
cannot be recomputed from the upload, a file is absent, a command was not run,
or Git identity cannot be independently checked, state UNKNOWN. Never invent a
commit, tree, CI outcome, deployment state, test result, or source content.

Inspect the archive read-only. Seek concrete defects before suggestions. Focus
on publication authority, proof-card/claim consistency, request routing,
regional geography, mixed live-and-guidance separation, partial outages,
privacy traces, malformed packets, accessibility claims, frontend trust labels,
benchmark integrity, and documentation truthfulness.

Do not alter human claim decisions. Do not treat a citation, retrieval match,
model fluency, or a test assertion alone as proof that a safety-relevant claim
is authorized. Do not request sealed benchmark labels or paid evaluation.

Return exactly this defect-first schema:

1. Evidence inventory: VERIFIED / CONTRADICTED / UNKNOWN for each manifest
   identity and executed command.
2. P0/P1 defects: id, severity, precise affected file/path if present,
   reproduction using only uploaded material, why the current guard fails, and
   the smallest safe repair. Say NONE FOUND only after explaining scope.
3. Trust-boundary review: publication authority, quotes, live records, request
   plan, provider boundary, privacy, and failure/unknown states.
4. UX review: named fire, regional analysis, mixed answer, unsupported request,
   partial outage, and Proof Card. Distinguish observed evidence from inference.
5. Benchmark review: report supplied results exactly; identify stale, missing,
   self-referential, or non-comparable evidence. Do not reinterpret thresholds.
6. Documentation review: unsupported, stale, or overstated claims.
7. Prioritized repair plan: smallest safe changes, ownership, tests, and
   explicit stop conditions. Do not authorize deployment, release GO, paid H4/H8,
   human approvals, or threshold changes.
8. Remaining external gates and the exact evidence missing from this bundle.

Use concise citations to archive paths and manifest keys. Label every conclusion
as OBSERVED, INFERRED, or UNKNOWN.
```

## Suggested upload contents

- a SHA-256 manifest with archive identity, declared Git commit/tree, and every
  included file;
- sanitized `git diff`, `git status`, and selected source/tests for changed
  authority, routing, privacy, and presentation paths;
- generated OpenAPI and public API types;
- test, lint, type-check, hard-probe, structural-evaluation, and browser output;
- candidate-evidence schema/documentation and current architecture/runbook;
- deterministic fixture screenshots or recordings with a statement of viewport
  and fixture status;
- a command ledger that distinguishes executed, failed, pending, and unexecuted
  steps.

## Exclude from the upload

- `.env` files, API keys, tokens, cookies, and provider credentials;
- raw user conversations, precise locations, production logs, or PII;
- sealed holdout labels and paid-evaluation data;
- unreviewed source material that is not necessary to examine the claimed
  behavior;
- any artifact that would imply authority to make a human review decision.

## Interpretation boundary

An offline bundle can support a code-and-evidence review. It cannot by itself
establish current GitHub state, hosted deployment identity, live-source behavior,
continuous availability, participant comprehension, manual VoiceOver quality,
firewall/rollback proof, paid H4/H8 outcomes, or release GO.
