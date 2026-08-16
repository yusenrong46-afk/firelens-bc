# ADR 0005: Bounded conversation with explicit evidence modes

Status: accepted
Date: 2026-07-26

## Context

V1 treated every request as a single corpus question. That made the evidence
boundary strong, but it also made normal follow-ups difficult and redirected
related explanatory questions merely because the reviewed corpus did not
directly support them.

## Decision

V1.1 accepts at most six untrusted user/assistant turns and assigns each public
response one mode:

- `grounded`: factual claims are verified against the current evidence packet;
- `background`: low-risk, wildfire-adjacent explanation is visibly marked as
  general background and has no FireLens citations;
- `capability`: a local description of the governed corpus and example prompts;
- `scope_redirect`: a brief redirect for a genuinely tangent request;
- `abstention`: a fail-closed response for current or personalized decisions.

Every public claim also carries an evidence status. `verified_corpus` claims
require local support pairs and exact quotes. `general_background` claims must
have no support pairs and must include the prescribed limitation. A response
cannot mix the two kinds of factual claim.

Deterministic safety routing runs before planning and every paid provider call
for personalized evacuation, safety-to-return, and medical advice. That
seatbelt remains authoritative and cannot be disabled by the model.

**Superseded 2026-08-15 by ADR 0011:** topic routing (live vs related vs
closest) is no longer a pre-call regex forest. Luna chooses official-fetch and
RAG tools for fire-related questions. Current incident *analysis* comes from
fetched official records plus Luna, not from the static corpus. Tangent
requests still receive a short redirect rather than an invented answer.

This decision changes ADR 0001's corpus-only conversation boundary and
supersedes ADR 0002's single-turn request restriction. It does not change the
static-evidence or exact-citation invariants.

## Consequences

Conversation becomes more natural without presenting model background as
reviewed evidence. The public contract and frontend must render evidence mode
explicitly. Evaluation must separately measure follow-up resolution, background
labelling, tangent redirects, safety exits, and citation leakage.
