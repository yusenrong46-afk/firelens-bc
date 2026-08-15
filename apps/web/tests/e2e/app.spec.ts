import { expect, test } from "@playwright/test";

const answer = {
  status: "answer",
  response_mode: "grounded",
  trace_id: "e2e-trace",
  answer: "Prepare water, food, and medication.",
  suggested_questions: ["How often should I update my emergency kit?"],
  claims: [{
    claim_id: "C1",
    text: "Prepare water, food, and medication.",
    evidence_status: "verified_corpus",
    supports: [{ evidence_id: "E1", quote: "Food & water" }],
  }],
  evidence: [{
    evidence_id: "E1",
    title: "Wildfire Preparedness Guide",
    publisher: "PreparedBC",
    canonical_url: "https://example.test/guide.pdf",
    locator: "PDF page 5",
    temporal_class: "stable_guidance",
    primary_text: "Food & water",
    context_text: "A grab-and-go bag includes Food & water and other supplies.",
  }],
  limitations: ["Stable guidance only."],
  validation: {
    accepted: true,
    schema_valid: true,
    citation_ids_valid: true,
    quotes_exact: true,
    policy_valid: true,
    errors: [],
  },
};

type AskRequest = { question: string; history: Array<{ role: string; content: string }> };
let seenRequests: AskRequest[] = [];

test.beforeEach(async ({ page }) => {
  seenRequests = [];
  await page.route("**/api/v1/live/map*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-08-13T19:00:00Z",
        results: [],
        unavailable_layers: [],
        layer_statuses: [],
        limitations: [],
      }),
    });
  });
  await page.route("**/api/v1/ask", async (route) => {
    const request = route.request().postDataJSON() as AskRequest;
    seenRequests.push(request);
    const question = request.question;
    if (question.includes("stale official")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "live",
          trace_id: "stale-live-trace",
          answer: "Cached official information (refresh failed): cached Test Fire record.",
          suggested_questions: [],
          claims: [],
          evidence: [],
          limitations: ["A refresh failed; this cached record is visibly stale."],
          aggregate_freshness: "stale",
          live_results: [{
            result_id: "incident:stale-7",
            kind: "incident",
            authority: "BC Wildfire Service",
            source_url: "https://example.test/incidents/stale-7",
            source_updated_at: "2026-07-28T11:55:00Z",
            retrieved_at: "2026-07-28T12:00:00Z",
            freshness: "stale",
            status: "Out of Control",
            name: "Cached Test Fire",
            geometry_relation: "nearby",
            geometry: { type: "Point", coordinates: [-123.5, 49.5] },
          }],
          unavailable_layers: ["evacuation"],
        }),
      });
      return;
    }
    if (question.includes("active wildfire")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "live",
          trace_id: "live-trace",
          answer: "Current official information: Test Fire is Out of Control.",
          suggested_questions: [],
          claims: [],
          evidence: [],
          limitations: ["No matching record is not a safety determination."],
          live_results: [{
            result_id: "incident:7",
            kind: "incident",
            authority: "BC Wildfire Service",
            source_url: "https://example.test/incidents/7",
            source_updated_at: "2026-07-28T11:55:00Z",
            retrieved_at: "2026-07-28T12:00:00Z",
            freshness: "fresh",
            status: "Out of Control",
            name: "Test Fire",
            geometry_relation: "nearby",
            geometry: { type: "Point", coordinates: [-123.5, 49.5] },
          }],
          unavailable_layers: ["evacuation"],
        }),
      });
      return;
    }
    if (question.includes("embers")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "background",
          trace_id: "background-trace",
          answer: "Embers can travel ahead of a wildfire front.",
          suggested_questions: [],
          claims: [{
            claim_id: "C1",
            text: "Embers can travel ahead of a wildfire front.",
            evidence_status: "general_background",
            supports: [],
          }],
          evidence: [],
          limitations: ["General background — not verified against the FireLens corpus."],
        }),
      });
      return;
    }
    if (question.includes("debug JavaScript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "scope_redirect",
          trace_id: "scope-trace",
          answer: "That request is outside the FireLens guidance collection.",
          suggested_questions: ["What can FireLens help me understand?"],
          claims: [],
          evidence: [],
          limitations: [],
        }),
      });
      return;
    }
    if (question.includes("provider unavailable")) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          trace_id: "error-trace",
          error_kind: "unavailable",
          message: "The required OpenRouter service is unavailable.",
          retryable: true,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(answer),
    });
  });
});

test("submits a question and inspects exact evidence", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("What belongs in a grab-and-go bag?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("Sources supporting this answer")).toBeVisible();
  await expect(page.getByText("Reviewed sources")).toBeVisible();
  await expect(page.locator("mark")).toHaveText("Food & water");
  await expect(page.getByText("PreparedBC")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test("labels general background and exposes no evidence control", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Why can embers be dangerous?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("General background", { exact: true })).toBeVisible();
  await expect(page.getByText("General background — no corpus evidence attached")).toBeVisible();
  await expect(page.getByText("Source passage")).toHaveCount(0);
});

test("sends bounded conversation context and can clear it", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("What should I pack?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("2 of 6 turns in context")).toBeVisible();

  await page.getByLabel("Ask FireLens a question").fill("Why does that matter?");
  await page.getByLabel("Send question").click();
  await expect.poll(() => seenRequests.length).toBe(2);
  expect(seenRequests[1]!.history).toEqual([
    { role: "user", content: "What should I pack?" },
    { role: "assistant", content: answer.answer },
  ]);

  await page.getByLabel("Clear conversation history").click();
  await expect(page.getByText("0 of 6 turns in context")).toBeVisible();
  await page.getByLabel("Ask FireLens a question").fill("Fresh question");
  await page.getByLabel("Send question").click();
  await expect.poll(() => seenRequests.length).toBe(3);
  expect(seenRequests[2]!.history).toEqual([]);
});

test("redirects a completely tangent request", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Can you debug JavaScript for me?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("Related official service", { exact: true })).toBeVisible();
  await expect(page.getByText("That request is outside the FireLens guidance collection.", { exact: true })).toBeVisible();
});

test("shows official live records and a map through keyboard submission", async ({ page }, testInfo) => {
  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByText("Current BC wildfire information")).toBeVisible();
  const testFire = page.getByRole("button", { name: /Test Fire Out of Control/ });
  await expect(testFire).toBeVisible();
  await expect(page.getByText(/Some official layers are unavailable: evacuation/)).toBeVisible();
  await expect(testFire.getByText(/Source updated/)).toBeVisible();
  await expect(testFire.getByText(/Retrieved/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toBeVisible();
  const marker = page.locator(".live-map__record-geometry").first();
  await expect(marker).toBeVisible();
  if (testInfo.project.name === "desktop") {
    await marker.dispatchEvent("click");
    await expect(page.locator(".leaflet-popup").getByText("Test Fire", { exact: true })).toBeVisible();
  } else {
    await testFire.press("Enter");
    await expect(testFire.locator("..")).toHaveClass(/live-list__selected/);
  }
  await expect(
    page.getByRole("status", { name: "Answer limitations" })
      .getByText("No matching record is not a safety determination.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Official wildfire records map" })
      .getByText(/No matching record is not a safety determination\. Follow instructions/),
  ).toBeVisible();
  await expect(page.getByText("Sources supporting this answer")).toHaveCount(0);
});

test("uses local boundary context without third-party basemap requests", async ({ page }) => {
  const thirdPartyMapRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("tile.openstreetmap.org")) thirdPartyMapRequests.push(request.url());
  });
  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByLabel("Question and answer").getByText("Current official information: Test Fire is Out of Control.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Test Fire Out of Control/ })).toBeVisible();
  await expect(page.getByText(/No third-party basemap request is made/)).toBeVisible();
  expect(thirdPartyMapRequests).toEqual([]);
});

test("shows stale and partial-layer state without hiding records", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Show stale official wildfire records");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("BC wildfire information — includes stale records")).toBeVisible();
  await expect(page.getByLabel("Question and answer").getByText(/Cached official information \(refresh failed\)/)).toBeVisible();
  await expect(page.getByText("Official cached records", { exact: true })).toHaveCount(2);
  const staleWarning = page.getByRole("status").filter({ hasText: "Cached official records; refresh failed" });
  await expect(staleWarning).toBeVisible();
  await expect(page.getByText("Current BC wildfire information")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Cached Test Fire Out of Control/ })).toBeVisible();
  expect(await staleWarning.evaluate((warning) => Boolean(
    warning.compareDocumentPosition(document.querySelector(".live-list")!) & Node.DOCUMENT_POSITION_FOLLOWING,
  ))).toBe(true);
  await expect(page.getByText(/Out of Control · stale · BC Wildfire Service/)).toBeVisible();
  await expect(page.getByText(/Some official layers are unavailable: evacuation/)).toBeVisible();
});

test("opens an official source link with keyboard activation", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Is there an active wildfire near me right now?");
  await page.getByLabel("Send question").press("Enter");
  const source = page
    .getByRole("listitem")
    .filter({ hasText: "Test Fire" })
    .getByRole("link", {
      name: "Open Source for Test Fire, record incident:7",
      exact: true,
    });
  await expect(source).toBeVisible();
  await expect(source).toHaveAttribute("href", "https://example.test/incidents/7");
  const [popup] = await Promise.all([page.waitForEvent("popup"), source.press("Enter")]);
  expect(popup).toBeTruthy();
});

test("offers retry for a transient provider outage", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Simulate provider unavailable");
  await page.getByLabel("Send question").click();
  await expect(page.getByRole("button", { name: "Retry this question" })).toBeVisible();
});
