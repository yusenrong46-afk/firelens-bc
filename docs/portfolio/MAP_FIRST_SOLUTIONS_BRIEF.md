# FireLens: AI implementation / solutions brief

## User need

A B.C. resident needs to find official records, understand what a source says,
and tell when information is incomplete. FireLens combines a map, question entry,
record selection and source inspection in one workflow. Success means completing
those tasks with understandable authority and failure states, not maximizing chat.

## Implementation choices

- Integrate official feeds through deterministic adapters; retain source times,
  coverage and usable record lists during tile failures.
- Use an approved retrieval corpus for guidance, with separate quotation and
  publication controls. Keep general model explanations visibly separate.
- Use approximate location only when requested; exclude coordinates and internal
  identifiers from copied answers. Apply origin-only referrers to map tiles.
- Preserve source evidence as a response snapshot while independently refreshing
  the visible map every five minutes.
- Release to the existing Vercel project through a tested preview, exact commit
  identity, controlled promotion and a recorded rollback deployment.

## Success criteria and handoff

Measure task completion, evidence access, desktop/mobile usability, provider
failure recovery and context continuity. The release has a bounded 24-submission
smoke allowance with prerequisite checks and observation-only spending records.
Unknown cost is reported separately from known charges. The operator receives
setup commands, environment checklist, test receipts, limitations and rollback
steps in the [runbook](../product/map-first-release-v2.md).

## Honest scope

This demonstrates requirements analysis, AI/service integration, evaluation design,
product judgment and operational handoff on a personal project. It does not
establish enterprise consulting experience, customer adoption or business savings.
The owner directed decisions and review; OpenAI Codex assisted implementation and
testing. The application is independent beta software, not an emergency authority.
