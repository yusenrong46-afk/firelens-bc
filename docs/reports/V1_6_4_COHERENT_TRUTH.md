# FireLens V1.6.4 — Coherent Truth

Status: `VERIFIED_READY_FOR_HUMAN_REVIEW`

Evidence class: executed local engineering and offline verification. This report
is not independent examination, paid provider proof, preview evidence,
deployment evidence, or a release-GO. Human verdicts remain
`APPROVE_V1_6_4_DEPLOY` / `RETURN_TO_TICKET_<ID>` / `DEFER_AND_DOCUMENT`.

## Evaluated identity

- Parent branch: `codex/v1-6-3-source-aware-conversation`
- Parent commit: `f8543e91b86645cc82221761bf63649e5a865191`
- Implementation branch: `codex/v1-6-4-coherent-truth`
- Public identity: `1.6.4` in Python, web package, Docker, Render, OpenAPI, and
  the candidate workflow `--release-version`
- V1.6.3 remains the historical functional parent. Its current-tree promotion
  bind is historical because this campaign changed governed capability-registry
  files.

Exact HEAD/tree for this candidate must be bound after a clean commit. This
report does not embed a self-referential commit identifier.

## Governing invariant

One request produces one backend-owned interpretation and one authoritative
result set. Answer, map, records, provenance, limitations, and suggestions may
present that set differently. They may not independently reinterpret it.

## Ticket close-out

F164-001 through F164-021 and F164-024 are implemented. Stretch F164-022
(CSV export) and F164-023 (saved scopes) remain helpers only and are not
blocking.

F164-021 paired retrieval experiment recorded `retain_baseline`. Adaptive
retrieval is not promoted.

## Local qualification

| Gate | Result |
| --- | --- |
| pytest excluding paid smoke/bakeoff | 1983 passed, 10 skipped |
| ruff check / format | passed |
| mypy | passed, 269 files |
| frontend vitest | 166 passed, 19 files |
| ClaimBench v1 | frozen floors held in pytest |
| ClaimBench v2 | 332/332; unsafe false-accept 0; faithful false-reject 0 |
| Offline hard probe RC2.2 | 91/105; floor 86 met; $0.00 |
| Hard-probe paired regressions vs Round 3 | none |
| Newly passing vs Round 3 | F11, G03, H04, M03, M04 |
| Remaining hard-probe failures | F06, F07, F09, F10, H01, H02, H03, I04, I08, K03, K09, L01, L02, L05 |
| Adaptive retrieval | `retain_baseline` |

Floors were not weakened. Paid OpenRouter smoke and model bakeoff were not run.

## Browser matrix

Local Vite + API without a provider key (`/api/v1/health/ready` is `not_ready`
because the bound runtime candidate is absent). Header still reads `V1.6.4`
and “Official B.C. wildfire information.” Idle copy shows the live summary
(163 incident / 18 evacuation records on this run) and does not claim
official-source data. 320px and tablet viewports keep the header, answer, and
summary tab readable.

The mixed smoke question degraded to live-only analysis because generation is
unconfigured. The map did not auto-open; Summary was first. Frozen tests still
cover the two-section chat shell with a provider double. Unclear-input and
missing-antecedent clarifications returned from the API. Sky-blue and 9-1-1
need a configured provider in this environment; their offline doubles remain
in pytest.

## Authority rails preserved

- 9-1-1 remains `official_quote_only`; the UI does not synthesize when to call.
- Empty or unavailable official layers are not an all-clear.
- Source failure is not published as zero.
- Incident names are not invented from geography.
- No frontend free-text intent classifier was reintroduced.
- Capability matching uses registry paraphrases only.
- `BACKGROUND_LIMITATION` is unchanged.

## Human review questions

1. `What wildfires are currently listed in B.C.?`
2. `Current wildfire records, and what should I pack?`
3–4. Evacuation-mistake paraphrase pair
5. `What does the official BC Wildfire Service say about this source?`
6. `When should I call 9-1-1?`
7. `Why is the sky blue?`
8. `asdf qwerty zxcv quantum foam`
9. `What fires are near Kelowna?`
10. `Should I evacuate right now?`

## Out of scope / not authorized

Push, deploy, paid H4, sealed retrieval, and production GO are not authorized
by this report.
