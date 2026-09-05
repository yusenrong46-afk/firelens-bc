# Pacific Operations central-page design QA

Source visual truth: `private retained evidence: firelens-external-qualification-7c43d17/ui-reference-pacific-operations/REFERENCE.png`.
Implementation: same campaign `ui-central-redesign/final-reference.png`.
Both are 1672x941 pixels, CSS viewport 1672x941, deviceScaleFactor 1, light theme,
nearby-answer state. The source is illustrative; implementation uses two synthetic
records, exact backend prose and real OSM tiles. Values and incident images are not
copied from the mock. There is no density rescaling in the full comparison.

## Findings and comparison history

1. Reopened baseline `ui-rebuild/reference-dbe924d-ready.png` after the owner rejected
   the first UI. P1: a whole serif paragraph, one giant conversation card, uneven
   tall record blocks and oversized source panel changed the intended hierarchy.
2. `iteration-1.png`: separate panels and shared rows corrected that structure.
   P2: answer feedback/routine notes and repeated source metadata still consumed
   too much vertical space. Answer 401px; source panel 426px.
3. `iteration-2.png`: moved feedback into the routine-note footer and map action
   into the record heading. P2: additional-source actions still extended the source
   card below the fold. Consolidated these into one footer row.
4. `iteration-3.png` and `final-reference.png`: answer 341px, source panel 330px;
   central x234/width851 and map x1109/width539 match the reference's major tracks.
   Full source and candidate were opened together in each comparison. Focused
   `reference-center.png` / `final-center.png` crops were also opened together:
   both 850x800 at original density, extracted from x234/y104. These confirm
   headline/body contrast, row consistency, source labels and follow-up spacing.
5. Independent review identified hidden partial coverage, numeric rounding and an
   accessible-label mismatch. All corrected. The partial warning stays visible,
   exact numeric sizes remain unchanged, and the accessible map name starts with
   the visible label. The separate mobile navigation issue is documented in
   `MOBILE_MAP_FAILURE.md`; explicit navigation now brings the map into view.

## Required fidelity surfaces

- Typography: bundled Newsreader is limited to the opening headline per the
  written contract; Inter owns body, rows, metadata and controls. The old entire
  serif paragraph is removed. Backend text, linked Markdown and quotes remain intact.
- Layout/rhythm: distinct answer/results surfaces, 20-24px gaps, 16px panel corners,
  shared compact record rows and matched desktop tracks. Mobile uses document flow,
  a visible current-question label, reachable source/map and full-width controls.
- Tokens: Pacific navy, teal, off-white page and white panels; restrained borders.
  Status colors follow existing status mappings. No invented green live state.
- Assets: existing mark/landscape retained; library icons replace photo slots as
  the written truth contract permits. No fabricated incident photo or drawn map.
  Actual OSM tiles/attribution replace the mock's illustrated terrain.
- Copy: source-backed record fields and unmodified answer text. No fake weather,
  profile, account, notification or unsupported navigation. Routine notes collapse;
  material limits, unavailability and partial coverage remain visible.

The answer retains a full safety qualification and feedback, making it ~70px taller
than the illustrative answer. Two returned fixture rows replace three illustrative rows.
Fetch timestamps and scoped freshness add source detail. These are explicit content
constraints, not hidden visual defects. The design is closer in hierarchy and
proportion; this report does not claim pixel identity or owner acceptance.

Responsive source: `ui-central-redesign/browser-verified`, covering 1536/1440/1366/
1024/768/390/320px plus active empty/partial states. Built browser tests check selected
record coherence, source actions, keyboard navigation, Home and local lazy assets.
Inspected selected-answer axe checks: zero violations at 1536 and 390px. Browser
page exceptions and failed local asset responses: zero in the viewport matrix.
External tiles are deliberately blocked in that matrix, visibly reported as failed.
The separate final-reference capture records no page exceptions with OSM permitted.

## Follow-up polish and limits

Native 200% browser zoom and human screen-reader assessment are unverified; the
existing 640px zoom proxy is not native zoom. Local synthetic data is not external
qualification, live latency or deployed-preview evidence. No further actionable
P0/P1/P2 visual findings remain in the compared, written-contract scope.

final result: passed
