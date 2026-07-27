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

Deterministic safety routing runs before planning and every paid provider call.
It remains authoritative for current incident status, personalized evacuation
or safety decisions, and personalized medical advice. The planner cannot
override it. Tangent requests receive a short redirect rather than an invented
answer.

This decision changes ADR 0001's corpus-only conversation boundary and
supersedes ADR 0002's single-turn request restriction. It does not change the
static-evidence or exact-citation invariants.

## Consequences

Conversation becomes more natural without presenting model background as
reviewed evidence. The public contract and frontend must render evidence mode
explicitly. Evaluation must separately measure follow-up resolution, background
labelling, tangent redirects, safety exits, and citation leakage.
