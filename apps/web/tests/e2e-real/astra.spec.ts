import { expect, test } from "@playwright/test";

test.beforeEach(async ({ context }) => {
  await context.route("**/*", async (route) => {
    if (route.request().url().startsWith("http://127.0.0.1:8766/")) await route.continue();
    else await route.abort("blockedbyclient");
  });
});

test("Home clears an unsubmitted private draft and returns keyboard focus", async ({ page }, testInfo) => {
  await page.goto("/");
  const input = page.getByLabel("Ask FireLens a question");
  await input.fill("unsubmitted private draft");
  await page.screenshot({ path: testInfo.outputPath("before-home.png"), fullPage: true });
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("after-home.png"), fullPage: true });
  await expect(input).toHaveValue("");
  await expect(input).toBeFocused();
});

test("Home invalidates a pending browser location callback without sending coordinates", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.geolocation.getCurrentPosition = (success) => {
      Object.assign(window, { finishAstraLocation: () => success({ coords: { latitude: 49.899, longitude: -119.499 } } as GeolocationPosition) });
    };
  });
  const asks: string[] = [];
  page.on("request", (request) => { if (request.url().endsWith("/api/v1/ask")) asks.push(request.postData() ?? ""); });
  await page.goto("/");
  await page.getByRole("button", { name: "Use approximate location", exact: true }).click();
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await page.evaluate(() => (window as unknown as { finishAstraLocation: () => void }).finishAstraLocation());
  // Allow the callback's microtasks and rendering to finish; no arbitrary sleep.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  expect(asks).toEqual([]);
  await expect(page.locator("#conversation")).not.toContainText("Approximate location ready");
});

async function ask(page: import("@playwright/test").Page, question: string) {
  const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/ask"));
  await page.getByLabel("Ask FireLens a question").fill(question);
  await page.getByLabel("Ask FireLens a question").press("Enter");
  const response = await pending;
  expect(response.status()).toBe(200);
  return { request: response.request().postDataJSON(), payload: await response.json() };
}

test("missing place becomes an exact fixture roster and explicit selection survives a follow-up", async ({ page }) => {
  await page.goto("/");
  const missing = await ask(page, "Are there fires near me?");
  expect(missing.payload.required_input.kind).toBe("location");
  expect(missing.payload.live_results).toEqual([]);
  const located = await ask(page, "Kelowna");
  expect(located.request.location.label).toBe("Kelowna");
  expect(located.payload.live_results.map((row: { result_id: string }) => row.result_id).sort()).toEqual(["incident:bear-creek", "incident:mountain"]);
  await expect(page.locator("#conversation")).toContainText("Mountain Fire");
  const named = await ask(page, "Where is Mountain Fire near Kelowna?");
  expect(named.payload.selected_live_result_id).toBe("incident:mountain");
  const follow = await ask(page, "What is the current status of this fire?");
  expect(follow.request.context.selected_live_result_id).toBe("incident:mountain");
  expect(follow.payload.selected_live_result_id).toBe("incident:mountain");
  await expect(page.locator(".assistant-message").last()).toContainText("Out of Control");
});

test("mixed answer exposes distinct current-record and source-proof tasks", async ({ page }, testInfo) => {
  await page.goto("/");
  const { payload } = await ask(page, "What current fires are near Kelowna, and what does an evacuation alert mean?");
  expect(payload.live_results.map((row: { result_id: string }) => row.result_id).sort()).toEqual(["incident:bear-creek", "incident:mountain"]);
  expect(payload.claims.some((claim: { publication?: { kind: string } }) => claim.publication?.kind === "structured_reviewed")).toBe(true);
  await expect(page.getByText("Reviewed preparedness guidance", { exact: true })).toBeVisible();
  await page.getByText("More detail on each statement", { exact: true }).click();
  await page.getByRole("button", { name: /Review technical evidence for/ }).first().click();
  await expect(page.getByText("Reviewed structured claim", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mixed-evidence.png"), fullPage: true });
});

test("valid empty and partial outage remain visibly different", async ({ page }) => {
  await page.goto("/");
  const empty = await ask(page, "Are there current wildfires near Emptytown?");
  expect(empty.payload.live_results).toEqual([]);
  expect(empty.payload.unavailable_layers).toEqual([]);
  await expect(page.locator(".assistant-message").last()).toContainText("not an all-clear");
  const partial = await ask(page, "Show fires and evacuation orders near Outage Ridge");
  expect(partial.payload.unavailable_layers).toContain("evacuation");
  expect(partial.payload.live_results.some((row: { result_id: string }) => row.result_id === "incident:mountain")).toBe(true);
  await expect(page.locator(".assistant-message").last()).toContainText(/evacuation.*unavailable/i);
});

for (const width of [390, 1536]) {
  test(`current interface is usable at ${width}px without hiding warnings`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(page.getByLabel("Ask FireLens a question")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("idle.png"), fullPage: true });
    await ask(page, "Are there current wildfires near Emptytown?");
    await expect(page.locator(".assistant-message").last()).toContainText("not an all-clear");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByLabel("Ask FireLens a question")).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath("empty.png"), fullPage: true });
  });
}
