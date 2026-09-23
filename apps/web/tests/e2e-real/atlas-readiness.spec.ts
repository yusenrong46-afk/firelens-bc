import { expect, test, type Page } from "@playwright/test";
import { localOrigin, openComposer, openSources, openMapRecords, menuAction, goHome } from "../browserNavigation";

// Additional UI-only controls. Historical/fullstack fixture material stays fixed.
const fixtureTime = "2026-08-24T15:02:00Z";
test.beforeEach(async ({ page, context }) => {
  await page.clock.setFixedTime(new Date(fixtureTime));
  await context.route("**/*", async route => {
    if (route.request().url().startsWith(`${localOrigin}/`)) await route.continue();
    else await route.abort("blockedbyclient");
  });
});

async function ask(page: Page, question: string) {
  const pending = page.waitForResponse(response => response.url().endsWith("/api/v1/ask"));
  await (await openComposer(page)).fill(question);
  await page.getByLabel("Ask FireLens a question").press("Enter");
  const response = await pending;
  expect(response.status()).toBe(200);
  await expect(page.locator(".assistant-message")).toBeVisible();
  await expect(page.getByLabel("Ask FireLens a question")).toBeEnabled();
  return response.json();
}

function recordAsks(page: Page) {
  const requests: string[] = [];
  page.on("request", request => { if (request.url().endsWith("/api/v1/ask")) requests.push(request.postData() ?? ""); });
  return requests;
}

test("copy, explanation and source inspection add no answer requests or private fields", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const asks = recordAsks(page);
  await page.goto("/");
  const question = "What does an evacuation alert mean?";
  const response = await ask(page, question);
  await page.getByRole("button", { name: "Copy answer", exact: true }).click();
  await expect(page.getByRole("button", { name: "Copied", exact: true })).toBeVisible();
  const text = await page.evaluate(() => navigator.clipboard.readText());
  expect(text).toContain(response.answer);
  expect(text).toContain(response.status_banner.headline);
  expect(text).toContain(response.evidence[0].canonical_url);
  for (const limitation of response.limitations) expect(text).toContain(limitation);
  expect(text).not.toContain(question);
  expect(text).not.toContain(response.trace_id);
  expect(text).not.toContain(response.history_text);
  await page.getByRole("button", { name: "Why this answer?", exact: true }).click();
  const explanation = page.getByRole("region", { name: "Why this answer", exact: true });
  await expect(explanation).toContainText("PreparedBC");
  await expect(explanation).toContainText("These response checks do not establish safety or imply human review.");
  await explanation.getByRole("button", { name: "Inspect evidence", exact: true }).click();
  await expect(page.getByRole("region", { name: "Answer evidence and context" })).toBeVisible();
  expect(asks).toHaveLength(1);
});

test("clipboard rejection exposes selected answer text and absent metadata remains unavailable", async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => { throw new Error("test clipboard denial"); } } }); });
  await page.route("**/api/v1/ask", route => route.fulfill({ json: {
    status: "answer", trace_id: "internal-ui-control", response_mode: "general_knowledge",
    answer: "General background explanation.", claims: [], evidence: [], limitations: ["Not source-verified."],
    suggested_questions: [], related_links: [], live_results: [], partial_layers: [], unavailable_layers: [], requested_layers: [],
  } }));
  const asks = recordAsks(page);
  await page.goto("/");
  await ask(page, "private question not copied");
  await page.getByRole("button", { name: "Copy answer", exact: true }).click();
  const manual = page.getByLabel("Copy this answer manually", { exact: true });
  await expect(manual).toBeFocused();
  await expect(manual).toHaveValue(/General background explanation\./);
  expect(await manual.evaluate(node => (node as HTMLTextAreaElement).selectionEnd - (node as HTMLTextAreaElement).selectionStart)).toBe((await manual.inputValue()).length);
  expect(await manual.inputValue()).not.toMatch(/private question|internal-ui-control/);
  await page.getByRole("button", { name: "Why this answer?", exact: true }).click();
  const why = page.getByRole("region", { name: "Why this answer", exact: true });
  await expect(why).toContainText("Check details were not supplied with this response.");
  await expect(why).toContainText("Location and distance metadata were not supplied.");
  await expect(why).toContainText("Response checked: Not supplied");
  expect(asks).toHaveLength(1);
});

test("same source URL keeps distinct revisions and every retained passage accessible", async ({ page }) => {
  const canonical_url = "https://example.test/guide.pdf";
  const evidence = { evidence_id: "E1", title: "UI control guide", publisher: "PreparedBC", canonical_url, locator: "page:5", temporal_class: "stable_guidance", review_provenance: "native_text", primary_text: "First retained passage.", context_text: "First retained passage.", document_sha256: "a".repeat(64) };
  await page.route("**/api/v1/ask", route => route.fulfill({ json: {
    status: "answer", trace_id: "ui-revision-control", response_mode: "grounded", answer: "Source revision UI control.", claims: [],
    evidence: [evidence, { ...evidence, evidence_id: "E2", locator: "page:6", primary_text: "Second retained passage." }, { ...evidence, evidence_id: "E3", document_sha256: "b".repeat(64), primary_text: "Different revision passage." }],
    validation: { accepted: true }, limitations: [], suggested_questions: [], related_links: [], live_results: [], partial_layers: [], unavailable_layers: [], requested_layers: [],
  } }));
  const asks = recordAsks(page);
  await page.goto("/"); await ask(page, "revision control"); await openSources(page);
  const sources = page.getByRole("region", { name: "Source of this information" });
  await expect(sources.getByRole("heading", { name: "2 sources", exact: true })).toBeVisible();
  await sources.getByText("1 more source", { exact: true }).click();
  for (const summary of await sources.locator("summary").all()) {
    if ((await summary.textContent())?.includes("supporting text")) await summary.click();
  }
  await expect(sources.getByText("Second retained passage.", { exact: true })).toBeVisible();
  await expect(sources.getByText("Different revision passage.", { exact: true }).last()).toBeVisible();
  for (const summary of await sources.getByText("Technical provenance", { exact: true }).all()) await summary.click();
  for (const hash of ["a".repeat(64), "b".repeat(64)]) await expect(sources.getByText(hash, { exact: true })).toBeVisible();
  for (const link of await sources.getByRole("link", { name: /Open official source/ }).all()) await expect(link).toHaveAttribute("href", canonical_url);
  expect(asks).toHaveLength(1);
});

test("location denial preserves community entry and sends no coordinates", async ({ page }) => {
  await page.addInitScript(() => { navigator.geolocation.getCurrentPosition = (_success, error) => { error?.({ code: 1, message: "denied" } as GeolocationPositionError); }; });
  const asks = recordAsks(page);
  await page.goto("/"); await menuAction(page, "Use approximate location");
  await expect(page.getByText("Location was not shared. You can enter a BC community name instead.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("BC community for a nearby lookup")).toBeVisible();
  expect(asks).toHaveLength(0);
});

test("map refresh keeps selected records through tile failure and refresh failure, then exposes newer absence", async ({ page }) => {
  await page.clock.install({ time: new Date(fixtureTime) });
  let stage: "initial" | "failed" | "recovered" | "absent" = "initial";
  let mapCalls = 0;
  const point = { result_id: "incident:mountain", kind: "incident", authority: "BC Wildfire Service", source_url: "https://wildfiresituation.nrs.gov.bc.ca/", source_updated_at: fixtureTime, retrieved_at: fixtureTime, freshness: "fresh", name: "Mountain Fire", incident_name: "Mountain Fire", incident_number: "K00001", status: "Out of Control", geometry: { type: "Point", coordinates: [-119.43, 49.91] }, distance_km: 12 };
  await page.route("**/api/v1/live/map*", async route => {
    mapCalls += 1;
    if (stage === "failed") { await route.fulfill({ status: 503, json: { error: "upstream_unavailable", message: "Fixture refresh failed", trace_id: "map-ui-failure" } }); return; }
    const time = stage === "initial" ? fixtureTime : "2026-08-24T15:08:00Z";
    await route.fulfill({ json: { generated_at: time, aggregate_freshness: "fresh", results: stage === "absent" ? [] : [{ ...point, retrieved_at: time, status: stage === "recovered" ? "Under Control" : point.status }], layer_statuses: ["incident", "perimeter", "evacuation"].map(kind => ({ kind, available: true, freshness: "fresh", retrieved_at: time, source_updated_at: time, feature_count: kind === "incident" && stage !== "absent" ? 1 : 0 })), limitations: [] } });
  });
  const asks = recordAsks(page);
  await page.goto("/");
  const answer = await ask(page, "Where is Mountain Fire near Kelowna?");
  expect(answer.live_results.find((record: { result_id: string }) => record.result_id === point.result_id).geometry).toEqual(point.geometry);
  const map = await openMapRecords(page);
  const selection = map.locator('.live-map__record-geometry[data-result-id="incident:mountain"]');
  await expect(selection).toBeVisible();
  await expect(map.getByRole("button", { name: /Mountain Fire Out of Control/ }).locator("xpath=ancestor::li[1]")).toHaveClass(/live-list__selected/);
  // Exercise actual Leaflet zoom and keyboard pan, then retain that camera
  // through a same-scope data refresh (status changes, coordinates do not).
  const markerPosition = () => selection.evaluate(element => {
    const box = element.getBoundingClientRect();
    const mapBox = element.closest(".leaflet-container")!.getBoundingClientRect();
    return { x: Math.round(box.x - mapBox.x), y: Math.round(box.y - mapBox.y) };
  });
  const zoomBefore = await map.locator(".leaflet-tile").first().getAttribute("src");
  await map.getByRole("button", { name: "Zoom in", exact: true }).click();
  await page.clock.runFor(300);
  const zoomAfter = await map.locator(".leaflet-tile").first().getAttribute("src");
  expect(zoomAfter).not.toBe(zoomBefore);
  const beforePan = await markerPosition();
  await map.locator(".leaflet-container").focus();
  await page.keyboard.press("ArrowLeft");
  await page.clock.runFor(300);
  const camera = await markerPosition();
  expect(camera).not.toEqual(beforePan);
  stage = "failed";
  await page.clock.fastForward(300_001);
  await expect(map.getByText(/Refresh failed\. Showing the previously retrieved map snapshot/)).toBeVisible();
  await expect(selection).toBeVisible();
  stage = "recovered";
  await map.getByRole("button", { name: "Retry map", exact: true }).click();
  await expect(map.getByRole("button", { name: /Mountain Fire Under Control/ }).locator("xpath=ancestor::li[1]")).toHaveClass(/live-list__selected/);
  await page.clock.runFor(300);
  expect(await markerPosition()).toEqual(camera);
  stage = "absent";
  await map.getByRole("button", { name: "Refresh map", exact: true }).click();
  await expect(map.getByLabel("Official record totals")).toContainText("0 displayed official records");
  const history = map.locator(".map-historical-records");
  await history.locator("summary").click();
  await expect(history).toContainText("absence does not establish that an incident ended");
  await expect(history.getByRole("button", { name: "Mountain Fire", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(map.getByText(/Street-map tiles failed to load/)).toBeVisible();
  expect(asks).toHaveLength(1);
  expect(mapCalls).toBe(4);
});

test("keyboard answer actions remain unobscured at desktop, 390 and 320 with reduced motion", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/"); await ask(page, "What does an evacuation alert mean?");
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const copy = page.getByRole("button", { name: "Copy answer", exact: true });
    await copy.focus();
    await page.keyboard.press("Tab");
    const why = page.getByRole("button", { name: "Why this answer?", exact: true });
    await expect(why).toBeFocused();
    expect(await why.evaluate(element => {
      const box = element.getBoundingClientRect();
      const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
      return box.top >= 0 && box.bottom <= innerHeight && top !== null && (element === top || element.contains(top));
    }), `focused answer action must be unobscured at ${width}px`).toBe(true);
    await page.keyboard.press("Enter");
    const explanation = page.getByRole("region", { name: "Why this answer", exact: true });
    await expect(explanation).toBeVisible();
    expect(await explanation.evaluate(element => getComputedStyle(element).animationName)).toBe("none");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`after-answer-keyboard-${width}.png`), fullPage: true });
    await why.press("Enter");
  }
});


test("Home community submits all nearby layers at 50km, binds a record follow-up and resets", async ({ page }) => {
  const asks = recordAsks(page);
  await page.goto("/");
  await openComposer(page);
  await page.getByRole("button", { name: "Near me", exact: true }).click();
  await page.getByLabel("BC community for a nearby lookup").fill("Kelowna");
  expect(asks).toHaveLength(0);
  const pending = page.waitForResponse(response => response.url().endsWith("/api/v1/ask"));
  await page.getByRole("button", { name: "Check my area", exact: true }).click();
  const response = await pending;
  const request = response.request().postDataJSON();
  expect(request.question).toBe("Show the incident, perimeter, and evacuation records near Kelowna.");
  expect(request.location).toMatchObject({ label: "Kelowna", radius_km: 50 });
  const payload = await response.json();
  expect([...payload.requested_layers].sort()).toEqual(["evacuation", "incident", "perimeter"]);
  const map = await openMapRecords(page);
  await map.getByRole("button", { name: /Mountain Fire Out of Control/ }).click();
  const follow = await ask(page, "What is the current status of this fire?");
  expect(JSON.parse(asks[1]!).context.selected_live_result_id).toBe("incident:mountain");
  expect(follow.selected_live_result_id).toBe("incident:mountain");
  await openSources(page);
  await expect(page.locator("#conversation details.sheet-sources")).toHaveAttribute("open", "");
  await goHome(page);
  await expect(page.getByLabel("Ask FireLens a question")).toBeFocused();
  await expect(await openComposer(page)).toHaveValue("");
  expect(asks).toHaveLength(2);
});

test("Preparedness fills and focuses the composer while submission stays explicit", async ({ page }) => {
  const asks = recordAsks(page);
  await page.goto("/"); await menuAction(page, "Preparedness");
  const composer = page.getByLabel("Ask FireLens a question");
  await expect(composer).toHaveValue("What belongs in a wildfire grab-and-go bag?");
  await expect(composer).toBeFocused();
  expect(asks).toHaveLength(0);
  const pending = page.waitForResponse(response => response.url().endsWith("/api/v1/ask"));
  await composer.press("Enter");
  const response = await pending;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON().question).toBe("What belongs in a wildfire grab-and-go bag?");
  await expect(page.locator(".assistant-message")).toBeVisible();
  expect(asks).toHaveLength(1);
});
