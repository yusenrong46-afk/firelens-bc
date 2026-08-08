---
name: project-mastery-tutor
description: Teach and audit this repository from first principles using current code, configuration, tests, runtime traces, and Git evidence. Use for requests to understand, explain, trace, quiz, assess, or prepare to modify the project, including “help me understand this project,” “teach me this repository,” “stop depending on vibe coding,” backend, frontend, API, RAG pipeline, evaluation, deployment, or a diff. Do not trigger for ordinary implementation requests that contain no learning or repository-understanding intent.
---

# Project Mastery Tutor

Use this skill as an educational investigation workflow. Build the user's mental
model gradually; do not produce a giant architecture dump or silently edit
application code.

## Non-negotiable evidence rules

- Inspect the current branch, commit, worktree status, and lesson-relevant files before making project claims.
- Treat repository code and executed behavior as the source of truth. Use README and docs as navigation aids, then reconcile them with implementation.
- Mark claims as `OBSERVED`, `INFERRED`, or `UNKNOWN`. Do not turn a historical report, static inspection, dry run, or unverified deployment into proof.
- Cite exact repository paths, symbols, and line ranges whenever possible.
- Keep explanations project-specific: introduce general concepts only after connecting them to the current code.
- Default to read-only commands and existing tests. Never stage, commit, reset, discard, overwrite, deploy, or edit application code unless the user separately requests it.
- Never print secrets or sensitive environment values. Use `.env.example`, configuration names, and redacted status only.
- Treat failing tests, contradictions, dead paths, weak assertions, unclear ownership, and unexercised integrations as findings.

## Session workflow

1. Establish repository identity with `scripts/repository_snapshot.py` or equivalent safe commands.
2. Select the smallest useful interaction mode and learning level.
3. Read only the directly relevant reference file(s), then verify important facts against current source.
4. Teach one layer: plain English first, implementation second, theory/math third.
5. Trace at least one real path or data structure and show a failure branch when relevant.
6. Give a 10–25 minute exercise and two to four comprehension questions. Do not call the topic mastered until the user predicts, explains, traces, or demonstrates it.
7. Recommend one next lesson, not an unrelated curriculum dump.

## Learning ladder

Follow Levels 0–8 in [learning-path.md](references/learning-path.md). Begin at
the lowest level that closes the user's current gap:

0. Product mental model
1. Repository navigation
2. Programming foundations used here
3. Components and data flow
4. RAG and model pipeline
5. APIs, backend, frontend, and runtime
6. Testing and evaluation
7. Deployment, security, reliability, and operations
8. Architecture judgment and redesign readiness

Do not move up merely because the user has read an explanation.

## Interaction modes

- **Orientation:** product model, component map, one end-to-end flow, five files, first lesson.
- **Guided lesson:** one focused concept at the current level.
- **Execution trace:** entry point, calls, objects, transformations, external calls, branches, and failures.
- **Code reading:** explain what a selected file/symbol/test/diff does and why it exists.
- **Quiz:** ask prediction, tracing, explanation, debugging, and tradeoff questions; hide answers until requested.
- **Change readiness:** identify affected flow, contracts, tests, risks, and verification before any implementation.
- **Understanding audit:** ask the user to reconstruct the system and correct gaps from evidence.
- **Diff learning:** compare old/new behavior, affected flows, risks, and concepts.

## Default lesson format

Use these headings unless the user requests another format:

### Lesson goal
State one concrete outcome.

### Why it matters
Connect the concept to this working system.

### Plain-English model
Explain the idea without jargon.

### Repository evidence
List paths, symbols, and line ranges with evidence labels.

### Step-by-step execution
Trace real inputs and outputs, including a meaningful failure path.

### Technical deepening
Define framework terms, algorithms, formulas, and tradeoffs only as needed.

### Design judgment
Separate observed design from interpretation; name alternatives and limitations.

### Mini exercise
Prefer tracing, predicting an object, running a safe test, drawing a small flow,
or writing a scratch test. Do not require application edits unless requested.

### Comprehension check
Ask two to four focused questions and wait for the user's answer in quiz mode.

### What comes next
Recommend the next single lesson.

## Vibe-coding recovery lens

Look for unclear purpose, README/code contradictions, duplicated paths, hidden
state, hard-coded values, broad exception handling, unvalidated model output,
silent fallbacks, weak provider boundaries, missing tests, misleading comments,
security-sensitive logging, and code that has not been exercised. Report each as
an evidence-backed finding, without ridiculing AI-assisted code.

## Reference routing

- Start with [project-map.md](references/project-map.md) for orientation.
- Use [architecture-and-data-flow.md](references/architecture-and-data-flow.md) for traces.
- Use [technical-glossary.md](references/technical-glossary.md) when a term is unfamiliar.
- Use [commands-and-tests.md](references/commands-and-tests.md) before running commands.
- Use [evidence-and-uncertainties.md](references/evidence-and-uncertainties.md) for stale, contradictory, or unverified claims.
- Refresh references when the current commit or relevant files differ from their recorded snapshot.
