import { expect, test, type Page } from "@playwright/test";

/**
 * Product Reality Gate — the critical journeys a real person takes, run
 * against a live FireLens deployment (see playwright.reality.config.ts).
 *
 * Every journey asserts product behaviour, not data values: official data
 * changes hourly, so "records appear and are attributed" is checked, never
 * "the closest fire is X".
 */

const ASK = "**/api/v1/ask";
const START_HEADING = "What do you want to know about wildfires in B.C.?";

type AskWire = {
  answer?: string | null;
  response_mode: string;
  provenance_class?: string | null;
  reason_code?: string | null;
  live_results?: unknown[] | null;
  evidence?: unknown[] | null;
  answer_sections?: { kind: string }[] | null;
  related_links?: { title: string; url: string }[] | null;
};

function trackAssetFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (response) => {
    const url = response.url();
    if (url.includes("/assets/") && response.status() >= 400) failures.push(`${response.status()} ${url}`);
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes("/assets/")) failures.push(`failed ${request.url()}`);
  });
  page.on("pageerror", (error) => failures.push(`pageerror ${error.message}`));
  return failures;
}

async function ask(page: Page, question: string): Promise<AskWire> {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/api/v1/ask"),
    { timeout: 90_000 },
  );
  const input = page.getByLabel("Ask FireLens a question");
  await input.fill(question);
  await input.press("Enter");
  const response = await responsePromise;
  expect(response.status(), `ask returned ${response.status()} for ${question}`).toBe(200);
  const body = (await response.json()) as AskWire;
  // The answer text must actually be rendered, not just returned.
  await expect(page.locator(".assistant-message")).toBeVisible();
  return body;
}

async function openHome(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
}

/** Nested vertical scrollers other than the document itself (excluding the map, code and form controls). */
async function nestedVerticalScrollers(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const element of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      if (element.closest(".leaflet-container, textarea, pre, select, details")) continue;
      const style = getComputedStyle(element);
      if (!/(auto|scroll)/.test(style.overflowY)) continue;
      if (element.clientHeight === 0 || element.scrollHeight <= element.clientHeight + 1) continue;
      out.push(`${element.tagName.toLowerCase()}.${element.className.toString().split(" ")[0]}`);
    }
    return out;
  });
}

test.describe("Product Reality Gate", () => {
  test("Kelowna: an ordinary question returns official records and offers the map", async ({ page }) => {
    const failures = trackAssetFailures(page);
    await openHome(page);
    const body = await ask(page, "Where is the wildfire near Kelowna?");

    expect(["live", "mixed"], `mode was ${body.response_mode} (${body.reason_code})`).toContain(body.response_mode);
    expect(body.answer ?? "").toMatch(/Kelowna/i);
    expect(body.answer ?? "").toMatch(/BC Wildfire Service/);
    // Nonsense geocoding or a dropped location would produce an unrelated place or a clarification.
    expect(body.answer ?? "").not.toMatch(/could not resolve|which community|not a place/i);

    const mapButton = page.getByRole("button", { name: "Show these on the map" });
    await expect(mapButton).toBeVisible();
    await mapButton.click();
    await expect(page.locator("#official-map")).toBeVisible();
    await expect(page.locator("#official-map .leaflet-container")).toBeVisible({ timeout: 30_000 });
    expect(failures, failures.join("\n")).toEqual([]);
  });

  test("Kelowna variants all resolve to the same place", async ({ page }) => {
    await openHome(page);
    for (const question of ["wildfire kelowna", "Any fires close to Kelowna right now?", "Is there a fire in Kelowna?"]) {
      const body = await ask(page, question);
      expect(["live", "mixed"], `${question}: ${body.response_mode} (${body.reason_code})`).toContain(body.response_mode);
      expect(body.answer ?? "", question).toMatch(/Kelowna/i);
      await page.getByRole("button", { name: "Home" }).first().click();
      await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
    }
  });

  test("Source proof: a guidance answer shows publisher, title and link inline", async ({ page }) => {
    await openHome(page);
    const body = await ask(page, "What should I pack in an evacuation kit?");
    expect(["grounded", "partial"], `mode was ${body.response_mode} (${body.reason_code})`).toContain(body.response_mode);
    expect((body.evidence ?? []).length).toBeGreaterThan(0);

    const proof = page.getByRole("region", { name: /source of this information|where this answer comes from/i });
    await expect(proof).toBeVisible();
    await expect(proof.getByRole("heading", { name: /source of this information|where this comes from/i })).toBeVisible();
    const links = proof.getByRole("link");
    expect(await links.count()).toBeGreaterThan(0);
    const href = await links.first().getAttribute("href");
    expect(href ?? "").toMatch(/^https?:\/\//);
    await expect(proof.locator("strong, .source-proof__publisher").first()).not.toBeEmpty();
  });

  test("Home: one click returns to the start from an answer", async ({ page }) => {
    await openHome(page);
    await ask(page, "how many fires in bc");
    await expect(page.getByRole("heading", { name: START_HEADING })).toHaveCount(0);

    await page.getByRole("button", { name: "Home" }).first().click();
    await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
    await expect(page.getByLabel("Ask FireLens a question")).toHaveValue("");

    await ask(page, "how many fires in bc");
    await page.getByRole("link", { name: /FireLens/ }).first().click();
    await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
  });

  for (const viewport of [
    { name: "phone", width: 390, height: 844 },
    { name: "narrow phone", width: 320, height: 720 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "laptop", width: 1366, height: 768 },
    { name: "laptop at 200% zoom", width: 683, height: 384 },
  ]) {
    test(`UI: no horizontal jam and one scroll owner on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openHome(page);
      const idleOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(idleOverflow, "idle page overflows horizontally").toBeLessThanOrEqual(1);
      await expect(page.getByLabel("Ask FireLens a question")).toBeVisible();

      await ask(page, "Where is the wildfire near Kelowna?");
      const answerOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(answerOverflow, "answer page overflows horizontally").toBeLessThanOrEqual(1);
      const scrollers = await nestedVerticalScrollers(page);
      expect(scrollers, `nested scrollers: ${scrollers.join(", ")}`).toEqual([]);
      await expect(page.getByRole("button", { name: "Home" }).first()).toBeVisible();
    });
  }

  test("Map assets: hard refresh then map open loads every chunk", async ({ page }) => {
    const failures = trackAssetFailures(page);
    await openHome(page);
    await page.reload({ waitUntil: "load" });
    await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
    await ask(page, "wildfire kelowna");
    const mapToggle = page.getByRole("button", { name: "Show these on the map" });
    if (await mapToggle.count()) {
      await mapToggle.click();
    }
    await expect(page.locator("#official-map .leaflet-container")).toBeVisible({ timeout: 30_000 });
    expect(failures, failures.join("\n")).toEqual([]);
  });

  test("Mixed authority: records are answered and the safety decision is handed off, not dropped", async ({ page }) => {
    await openHome(page);
    const body = await ask(page, "What fires are near Kelowna, and should I evacuate?");
    expect(body.response_mode).toBe("mixed");
    const kinds = (body.answer_sections ?? []).map((section) => section.kind);
    expect(kinds).toContain("safety_boundary");
    expect(body.answer ?? "").toMatch(/Kelowna/i);
    expect(body.answer ?? "").toMatch(/cannot decide|cannot tell you whether|follow instructions/i);
    await expect(page.getByRole("link", { name: /EmergencyInfoBC/ }).first()).toBeVisible();
  });

  test("General knowledge is labelled as such and carries no false source proof", async ({ page }) => {
    await openHome(page);
    const body = await ask(page, "Why do wildfires spread faster uphill?");
    expect(["background", "grounded", "partial"], `mode was ${body.response_mode} (${body.reason_code})`).toContain(body.response_mode);
    expect(body.answer ?? "").not.toMatch(/\n[•\x83]|\x83|did not pass claim-support validation/);
    expect((body.answer ?? "").length).toBeGreaterThan(60);
    const proof = page.getByRole("region", { name: /source of this information|where this answer comes from/i });
    if (body.response_mode === "background") {
      await expect(page.locator(".response-badge")).toHaveText("General knowledge");
      await expect(proof).toHaveCount(0);
      await expect(page.getByText(/General knowledge — not checked against FireLens sources|General model knowledge/i)).toBeVisible();
    } else {
      expect((body.evidence ?? []).length).toBeGreaterThan(0);
      await expect(page.locator(".response-badge")).toHaveText(/reviewed guidance|official source/);
      await expect(proof).toBeVisible();
    }
  });

  test("Unsupported live topic hands off to the official service", async ({ page }) => {
    await openHome(page);
    const body = await ask(page, "What's the air quality in Kamloops?");
    expect(body.response_mode).toBe("scope_redirect");
    await expect(page.getByRole("link", { name: /AQHI/ }).first()).toBeVisible();
  });

  test("Failure truth: a broken backend is reported, not disguised", async ({ page }) => {
    await openHome(page);
    await page.route(ASK, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "down" }) }));
    const input = page.getByLabel("Ask FireLens a question");
    await input.fill("how many fires in bc");
    await input.press("Enter");
    await expect(page.getByRole("alert", { name: "We couldn't complete this question" })).toBeVisible();
    await page.unroute(ASK);
    await page.getByRole("button", { name: "Home" }).first().click();
    await expect(page.getByRole("heading", { name: START_HEADING })).toBeVisible();
  });

  test("Multiple Fire Centres: ask which scope instead of silently picking one", async ({ page }) => {
    await openHome(page);
    const body = await ask(page, "What is happening within the Kamloops or Cariboo Fire Centre?");
    expect(["requires_input", "scope_redirect", "abstention"]).toContain(body.response_mode);
    expect(body.answer ?? "").toMatch(/Which Fire Centre should I use|Kamloops|Cariboo/i);
  });

  test("Readiness failure: 503 with release_version is not shown as healthy live data", async ({ page }) => {
    await page.route("**/api/v1/health/ready", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ status: "not_ready", release_version: "1.6.4" }),
      }),
    );
    await openHome(page);
    await expect(page.getByText(/Live data unavailable|Official data delayed/i).first()).toBeVisible();
    await expect(page.locator(".live-data-status--live")).toHaveCount(0);
  });
});
