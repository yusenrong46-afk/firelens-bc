import { openComposer, goHome, openMatchingRecords, openMapRecords, openClaimDetails, localOrigin } from "../browserNavigation";
/** Draft current-task acceptance. Synthetic upstream fixtures; real /ask responses. */
import { expect, test, type Page } from "@playwright/test";

// Use the existing fixture retrieval instant; never apply this clock to live feeds.
test.beforeEach(async ({ page }) => { await page.clock.setFixedTime(new Date("2026-08-24T15:02:00Z")); });

const nearby = ["incident:bear-creek", "incident:mountain"];
const province = [...nearby, "incident:kootenay", "incident:south-okanagan"].sort();
const ids = (payload: { live_results: { result_id: string }[] }) => payload.live_results.map(r => r.result_id).sort();

test.beforeEach(async ({ context }) => {
  await context.route("**/*", r => r.request().url().startsWith(`${localOrigin}/`) ? r.continue() : r.abort("blockedbyclient"));
});
async function ask(page: Page, question: string) {
  const pending = page.waitForResponse(r => r.url().endsWith("/api/v1/ask"));
  const input = await openComposer(page);
  await input.fill(question); await input.press("Enter");
  const result = await pending;
  expect(result.status()).toBe(200);
  const payload = await result.json();
  await expect(input).toBeEnabled();
  return { payload, request: result.request().postDataJSON() };
}
test.afterEach(async ({ page }, info) => {
  await page.screenshot({ path: info.outputPath("synthetic-fixture.png"), fullPage: true });
});

test("R4-01 named fire exposes identity location and status beside its official map", async ({ page }) => {
  await page.goto("/");
  const { payload } = await ask(page, "Where is Mountain Fire near Kelowna?");
  expect(payload.selected_live_result_id).toBe("incident:mountain");
  await expect(page.locator(".assistant-message").last()).toContainText("Mountain Fire");
  await expect(page.locator(".assistant-message").last()).toContainText("5.5 km");
  await openMatchingRecords(page);
  await expect(page.getByRole("button", { name: /^Mountain Fire.*Status/ })).toContainText("Out of Control");
  await expect(page.getByRole("region", { name: "Official wildfire records map", exact: true })).toBeVisible();
});

test("R4-02 distribution has the exact three records and one of each status", async ({ page }) => {
  await page.goto("/");
  const { payload } = await ask(page, "Show the current wildfire distribution by status across the Okanagan.");
  expect(ids(payload)).toEqual([...nearby, "incident:south-okanagan"]);
  expect(payload.live_results.map((r: { status: string }) => r.status).sort()).toEqual(["Being Held", "Out of Control", "Under Control"]);
  for (const status of ["1 Being Held", "1 Out of Control", "1 Under Control"]) await expect(page.locator(".assistant-message").last()).toContainText(status);
});

test("R4-03 mixed response separates live records and reviewed guidance", async ({ page }) => {
  await page.goto("/");
  const { payload } = await ask(page, "What current fires are near Kelowna, and what does an evacuation alert mean?");
  expect(ids(payload)).toEqual(nearby);
  expect(payload.claims.some((c: { publication: { typed_claim_id: string } }) => c.publication.typed_claim_id === "TC-EVAC-ALERT-001")).toBe(true);
  await expect(page.getByText("Reviewed preparedness guidance", { exact: true })).toBeVisible();
  await openMatchingRecords(page);
  await expect(page.getByRole("button", { name: /^Bear Creek Fire Status/ })).toBeVisible();
});

test("R4-04 empty does not become unavailable or an all clear", async ({ page }) => {
  await page.goto("/"); const { payload } = await ask(page, "Are there current wildfires near Emptytown?");
  expect(ids(payload)).toEqual([]); expect(payload.unavailable_layers).toEqual([]);
  await expect(page.locator(".assistant-message").last()).toContainText("No fires are listed");
  await expect(page.locator(".assistant-message").last()).toContainText("not an all-clear");
});

test("R4-05 partial outage preserves incidents and subsequent recovery", async ({ page }) => {
  await page.goto("/"); const outage = await ask(page, "Show fires and evacuation orders near Outage Ridge");
  expect(ids(outage.payload)).toEqual(nearby); expect(outage.payload.unavailable_layers).toContain("evacuation");
  await expect(page.locator(".assistant-message").last()).toContainText(/evacuation.*unavailable/i);
  await expect(page.locator(".assistant-message").last()).toContainText("not an all-clear");
  const recovered = await ask(page, "Show fires and evacuation orders near Kelowna");
  expect(recovered.payload.unavailable_layers).toEqual([]);
  expect(ids(recovered.payload)).toEqual(["evacuation:kelowna-fixture", ...nearby]);
});

test("R4-06 visible source proof opens exact technical binding deliberately", async ({ page }) => {
  await page.goto("/"); const { payload } = await ask(page, "What does an evacuation alert mean?");
  const claim = payload.claims.find((c: { publication: { typed_claim_id: string } }) => c.publication.typed_claim_id === "TC-EVAC-ALERT-001");
  expect(claim.publication.kind).toBe("structured_reviewed");
  expect(claim.publication.source_revision_sha256).toMatch(/^[a-f0-9]{64}$/);
  await expect(page.locator(".assistant-message").last()).toContainText("short notice");
  await openClaimDetails(page);
  await page.getByRole("button", { name: /Review technical evidence for/ }).first().click();
  await expect(page.getByText("Reviewed structured claim", { exact: true }).first()).toBeVisible();
  const link = page.getByRole("dialog", { name: "Inspect answer evidence" }).getByRole("link", { name: "View source", exact: true }).first();
  await expect(link).toHaveAttribute("href", /gov\.bc\.ca/); await link.focus(); await expect(link).toBeFocused();
  // Inspect target only: remote availability is outside this fixture gate.
});

test("R4-07 smoke uses smoke claim and source instead of evacuation meaning", async ({ page }) => {
  await page.goto("/"); const { payload } = await ask(page, "What should I know about wildfire smoke?");
  const typed = payload.claims.map((c: { publication: { typed_claim_id: string } }) => c.publication.typed_claim_id);
  expect(typed).toContain("TC-SMOKE-014-01"); expect(typed).not.toContain("TC-EVAC-ALERT-001");
  await expect(page.locator(".assistant-message").last()).toContainText("BC Centre for Disease Control");
});

test("R4-08 typo resolves named record and current map affordance", async ({ page }) => {
  await page.goto("/"); const { payload } = await ask(page, "Where is the moutain fire near Kelowna?");
  expect(payload.selected_live_result_id).toBe("incident:mountain");
  await openMapRecords(page);
  await expect(page.getByRole("region", { name: "Official wildfire records map", exact: true })).toBeVisible();
});

for (const selection of ["list", "map"]) test(`R4-09 second record ${selection} selection survives followup and city switch clears it`, async ({ page }) => {
  await page.goto("/"); await ask(page, "Show current fires near Kelowna");
  if (selection === "list") { await openMatchingRecords(page); await page.getByRole("button", { name: /^Bear Creek Fire Status/ }).click(); }
  else {
    await openMapRecords(page);
    await page.getByRole("region", { name: "Official wildfire records map", exact: true }).locator('.live-map__record-geometry[data-result-id="incident:bear-creek"]').click();
  }
  const follow = await ask(page, "What is the current status of this fire?");
  expect(follow.request.context.selected_live_result_id).toBe("incident:bear-creek");
  expect(follow.payload.selected_live_result_id).toBe("incident:bear-creek");
  await expect(page.locator(".assistant-message").last()).toContainText("Being Held");
  const switched = await ask(page, "Are there current wildfires near Emptytown?");
  expect(switched.request.context.selected_live_result_id ?? null).toBeNull(); expect(ids(switched.payload)).toEqual([]);
});

test("R4-10 ambiguous singular followup requires explicit selection", async ({ page }) => {
  await page.goto("/"); await ask(page, "Show current fires near Kelowna");
  const { payload } = await ask(page, "How large is it?");
  expect(payload.selected_live_result_id).toBeNull();
  await expect(page.locator(".assistant-message").last()).toContainText(/select|name/i);
});

test("R1 exact F10 browser completes roster and preserves personal boundary", async ({ page }, info) => {
  await page.goto("/");
  const question = "Harder: List every active fire in BC and tell me which ones threaten my house in West Kelowna.";
  const exchange = await ask(page, question);
  expect(ids(exchange.payload)).toEqual(province); expect(exchange.payload.roster_total).toBe(4);
  expect(exchange.payload.answer_sections.some((s: { kind: string }) => s.kind === "safety_boundary")).toBe(true);
  await expect(page.locator(".assistant-message").last()).toContainText(/cannot/i);
  await openMatchingRecords(page);
  for (const name of ["Mountain Fire", "Bear Creek Fire", "South Okanagan Fire", "Kootenay Fixture Fire"]) await expect(page.getByRole("button", { name: new RegExp(`^${name}.*Status`) })).toBeVisible();
  await info.attach("F10-public-exchange", { body: JSON.stringify(exchange, null, 2), contentType: "application/json" });
});

test("R4 Home protects a new request from a delayed real response", async ({ page }) => {
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let ready!: () => void; const started = new Promise<void>(resolve => { ready = resolve; });
  let held = true;
  await page.route("**/api/v1/ask", async route => {
    if (!held) return route.continue(); held = false;
    const response = await route.fetch(); ready(); await gate;
    try { await route.fulfill({ response }); } catch { /* Home may abort the original request. */ }
  });
  await page.goto("/"); const input = await openComposer(page);
  await input.fill("Show fires near Kelowna"); await input.press("Enter"); await started;
  await goHome(page);
  await expect(page.getByRole("complementary", { name: "Map", exact: true })).toBeFocused(); await expect(await openComposer(page)).toHaveValue("");
  await ask(page, "Are there current wildfires near Emptytown?"); release();
  await expect(page.locator("#conversation")).toContainText("Emptytown");
  await expect(page.locator("#conversation")).not.toContainText("Mountain Fire");
});

for (const width of [320, 390]) test(`R4 keyboard and source disclosure remain readable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 }); await page.goto("/");
  await ask(page, "What current fires are near Kelowna, and what does an evacuation alert mean?");
  await openClaimDetails(page);
  await page.getByRole("button", { name: /Review technical evidence for/ }).first().click();
  await expect(page.getByText("Reviewed structured claim", { exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
});
