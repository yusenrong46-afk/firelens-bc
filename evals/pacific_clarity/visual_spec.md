# Pacific Clarity — visual spec (authoritative written contract summary)

## Tokens
Pacific Clarity palette in `apps/web/src/app/tokens.css` (navy actions, ocean structure, orange only for fire/status).

## Desktop geometry (1536×1024 target)
- Sidebar 288–320px; main 560–720px; map rail 360–440px; gap 24px; max-width 1600px.
- One document scroll owner.

## Shell
- ProductSidebar: Home / How it works / Official map / recent questions / landscape SVG / Clear conversation.
- No permanent topbar or boundary ribbon.
- Quiet footer disclaimer under composer.
- LiveDataStatus from `liveSummary` + readiness (never green on 503/unavailable).

## Answers
- LiveAnswerSummary: headline, lead record, up to 3 secondary rows, status pills (color+text), map CTA.
- SourceProof: primary source open; N more sources disclosure; Inspect evidence secondary.
- LiveMap `variant="compact"|"full"`; compact desaturates tile pane only.
- Explanation card omitted unless existing reviewed content supports it (not implemented as fabricated glossary).

## Differences from mood image
- Image is mood only; no YVR/BCWS artwork copied.
- Place/radius chips only when typed session location exists (API `resolved_location` has no label).
- No fabricated timestamps on recent questions.
