# 11 — Frontend and UI

The web client is a React/Vite application in [`apps/web/src`](../../apps/web/src). [`App.tsx`](../../apps/web/src/app/App.tsx) composes the conversation, evidence panel, official map, analysis workspace, source handoffs, and responsive shell. [`useFireLensSession.ts`](../../apps/web/src/features/ask/useFireLensSession.ts) owns request/session state.

## Data flow

### Pacific Operations shell

The 2026-09-05 local UI rebuild keeps the same session/API owners. `App.tsx`
owns the single bottom-docked `QuestionComposer`. Guided questions and suggested
follow-ups submit once through the existing session owner; Home resets the session,
selection, retained place, map and evidence state. `shell.css` owns the responsive
frame and `answer.css` owns answer/record presentation. The page is the scroll
owner; the former nested-scroll offset compensation has been removed.

The central-page revision separates `AnswerBody` from the selectable record and
follow-up panel in `ConversationPanel`. `AnswerMarkdown` styles the first plain
sentence as a headline without rewriting or extracting facts. Linked Markdown,
quotes and authority-labelled sections keep their existing representation.
`LiveAnswerSummary` shares one row component between primary and secondary records,
preserves source precision and backend ordering, and keeps partial-roster limits
visible. Explicit map navigation brings an already mounted mobile rail into view;
automatic spatial opening does not scroll away from the answer.

`OfficialSourcesCard` receives the bound selected record from the retained map
roster plus the current response, matching the selection chip. It does not
substitute the response's first record when an explicit selection is unresolved.
Its additional-source list contains only sources in the current response.
Source-update time, retrieval time, record freshness and unavailable layers
remain separate facts. No new API, generation or retrieval request is introduced.

The selected reference's account controls, weather action, incident photographs
and illustrative live values are omitted. Existing bundled fonts, mark,
landscape and real Leaflet attribution are retained. Map and chart bundles
remain lazy. See [rebuild evidence](../product/PACIFIC_OPERATIONS_UI_REBUILD.md)
for candidate-bound validation; local fixtures are not deployment evidence.

[`shared/api/api.ts`](../../apps/web/src/shared/api/api.ts) submits `QueryRequest` JSON and imports most public types from the generated OpenAPI schema. It applies a 60-second browser deadline, distinguishes API envelopes from transport/read/JSON failures, and exposes readiness/live-summary/map endpoints. The server’s public Ask deadline defaults to 45 seconds.

The response drives:

- answer/abstention/unavailable/error view state;
- conversation history using backend `history_text` when present;
- the live roster and selected result identity;
- spatial or analysis presentation shell;
- evidence/proof cards and official handoffs;
- map/list selection coherence.

## Authority rule

The UI is a projection of backend authority. It may reorder layout or offer navigation, but it must not recalculate whether evidence is supported, a live layer is available, or a source is current.

The main duplicate-owner risk is [`features/ask/proofPresentation.ts`](../../apps/web/src/features/ask/proofPresentation.ts), which contains substantial independent support/freshness/status presentation logic beside backend [`proof_presentation.py`](../../src/firelens/proof_presentation.py). Compatibility fallbacks in [`responseModel.ts`](../../apps/web/src/features/ask/responseModel.ts) also infer a mode when it is absent. These paths must fail weak, never strengthen a response, and should shrink as the generated contract becomes authoritative.

## Failure modes, tests, evaluation

Risks include stale bundle recovery, clipped answers, hidden sources, map/list identity drift, tile failure hiding the record list, lost focus, nested scrolling, small touch targets, misleading readiness, and responsive overflow. Automated coverage exists under `apps/web/tests` and Python frontend tests, but the current campaign has not completed independent accessibility, keyboard, screen-reader, mobile, or product-comprehension qualification.

The 2026-09-04 [UI audit](../product/FIRELENS_UI_AUDIT.md) bound the public
baseline to deployment `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh` / build
`40c4c970bf33192ce6a543a6b8dcf5b4799036bd`. Its 1024×768 idle axe check
found two violations affecting six contrast nodes and one item outside a
landmark. Candidate fixture checks found zero automated axe violations at the
inspected idle/live states and 183 frontend tests passed. The candidate also
uses distinct wildfire identity rather than row count, neutral evacuation/mixed
terminology, no unique total for partial data, stronger mobile task order, and
improved landmark/contrast semantics. Candidate screenshots/tests used local
deterministic fixtures and do not establish deployed-candidate quality.
