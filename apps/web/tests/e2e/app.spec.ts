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
    publication: {
      kind: "source_linked_explanation",
      review_status: "source_linked",
      renderer_id: "firelens.explanation_renderer.v1",
      support_provenance: "validated_grounded_explanation",
    },
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
    if (question.includes("rejected air quality")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "scope_redirect",
          trace_id: "rejected-scope-trace",
          answer: "Use the official air-quality service for current observations.",
          suggested_questions: [],
          claims: [],
          evidence: [],
          limitations: [],
          related_links: [{
            title: "Current B.C. AQHI",
            url: "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
            description: "Environment Canada current AQHI observations and forecasts.",
          }],
          validation: { accepted: false },
          status_banner: {
            headline: "Grounded in reviewed official sources",
            detail: "All content was validated against reviewed sources.",
            freshness_label: "Stable reviewed guidance",
            availability_label: "Sources required for this request were available.",
          },
        }),
      });
      return;
    }
    if (question.includes("distribution")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "answer",
          response_mode: "live",
          trace_id: question.includes("new distribution") ? "analysis-trace-next" : "analysis-trace",
          answer: "Three official incident records are in this bounded result.",
          suggested_questions: [],
          claims: [],
          evidence: [],
          limitations: [],
          aggregate_freshness: "fresh",
          live_results: [{
            result_id: "incident:1",
            kind: "incident",
            authority: "BC Wildfire Service",
            source_url: "https://example.test/incidents/1",
            source_updated_at: "2026-08-23T12:00:00Z",
            retrieved_at: "2026-08-23T12:01:00Z",
            freshness: "fresh",
            status: "Out of Control",
            fire_centre: "Kamloops Fire Centre",
            name: "Alpha Fire",
            geometry: { type: "Point", coordinates: [-119.5, 49.9] },
          }, {
            result_id: "incident:2",
            kind: "incident",
            authority: "BC Wildfire Service",
            source_url: "https://example.test/incidents/2",
            source_updated_at: "2026-08-23T12:00:00Z",
            retrieved_at: "2026-08-23T12:01:00Z",
            freshness: "fresh",
            status: "Being Held",
            fire_centre: "Kamloops Fire Centre",
            name: "Beta Fire",
            geometry: { type: "Point", coordinates: [-119.6, 50.0] },
          }, {
            result_id: "incident:3",
            kind: "incident",
            authority: "BC Wildfire Service",
            source_url: "https://example.test/incidents/3",
            source_updated_at: "2026-08-23T12:00:00Z",
            retrieved_at: "2026-08-23T12:01:00Z",
            freshness: "fresh",
            status: "Under Control",
            fire_centre: "Coastal Fire Centre",
            name: "Gamma Fire",
            geometry: { type: "Point", coordinates: [-123.5, 49.5] },
          }],
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
  await expect(page.locator("#conversation .assistant-message .answer-lead")).toHaveText(
    "Prepare water, food, and medication.",
  );
  await expect(page.getByText("Answer evidence and support")).toBeVisible();
  await expect(page.getByText("Reviewed sources")).toBeVisible();
  await expect(page.locator("mark")).toHaveText("Food & water");
  await expect(page.getByText("PreparedBC", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Analysis view" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "View official map context" })).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test("opens the employer explainer in flow without covering FireLens", async ({ page }) => {
  await page.setViewportSize({ width: 920, height: 800 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "How FireLens works", exact: true });
  await expect(page.getByText("How it works", { exact: true })).toBeVisible();
  const triggerBox = await trigger.boundingBox();
  expect(triggerBox?.width).toBeGreaterThanOrEqual(44);
  expect(triggerBox?.height).toBeGreaterThanOrEqual(44);
  await trigger.click();

  const explainer = page.getByRole("region", {
    name: "How FireLens works",
  });
  await expect(explainer).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  const geometry = await page.evaluate(() => {
    const panel = document.querySelector("#how-firelens-works")!;
    const workspace = document.querySelector("main")!;
    const panelRect = panel.getBoundingClientRect();
    const workspaceRect = workspace.getBoundingClientRect();
    return {
      position: getComputedStyle(panel).position,
      panelBottom: panelRect.bottom,
      workspaceTop: workspaceRect.top,
    };
  });
  expect(geometry.position).toBe("static");
  expect(geometry.workspaceTop).toBeGreaterThanOrEqual(geometry.panelBottom);

  const ask = page.getByLabel("Ask FireLens a question");
  await ask.fill("The workspace remains usable");
  await expect(ask).toHaveValue("The workspace remains usable");
  await page.keyboard.press("Escape");
  await expect(explainer).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("labels general background and exposes no evidence control", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Why can embers be dangerous?");
  await page.getByLabel("Send question").click();
  await expect(
    page.getByLabel("Question and answer").getByText("General knowledge", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(
    "General model knowledge · not checked against FireLens sources",
  )).toBeVisible();
  await expect(page.getByText("Answer evidence and support")).toHaveCount(0);
  await expect(page.getByText("Important limits")).toHaveCount(0);
  await expect(page.getByText("Source passage")).toHaveCount(0);
});

test("sends bounded conversation context and can clear it", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("What should I pack?");
  await page.getByLabel("Send question").click();
  await expect(page.getByLabel("Clear conversation history")).toContainText("New conversation");

  await page.getByLabel("Ask FireLens a question").fill("Why does that matter?");
  await page.getByLabel("Send question").click();
  await expect.poll(() => seenRequests.length).toBe(2);
  await expect(page.getByText("2 of 6 prior turns in context")).toBeVisible();
  expect(seenRequests[1]!.history).toEqual([
    { role: "user", content: "What should I pack?" },
    { role: "assistant", content: answer.answer },
  ]);

  await page.getByLabel("Clear conversation history").click();
  await expect(page.getByText("0 of 6 turns in context")).toHaveCount(0);
  await expect(page.getByText("No earlier turns in context")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ask about a fire, a B.C. place, or preparedness." })).toBeVisible();
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

test("fails closed for a rejected no-claim response", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Show rejected air quality");
  await page.getByLabel("Send question").click();
  const conversation = page.getByLabel("Question and answer");
  await expect(conversation.getByText("Support not established", { exact: true })).toBeVisible();
  await expect(conversation.getByText(
    "FireLens did not establish or validate support for this response.",
    { exact: true },
  )).toBeVisible();
  const status = conversation.getByRole("status", { name: "Answer status" });
  await expect(status).toContainText("Freshness: Freshness not established");
  await expect(status).toContainText(
    "Availability: This request did not complete with established sources.",
  );
  await expect(conversation.getByText("Grounded in reviewed official sources")).toHaveCount(0);
  await expect(conversation.getByRole("link", { name: "Current B.C. AQHI", exact: true })).toHaveAttribute(
    "href",
    "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
  );
});

test("keeps a live answer primary and opens its map on demand", async ({ page }, testInfo) => {
  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByLabel("Question and answer").getByText("Current official information: Test Fire is Out of Control.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Analysis view" })).toHaveCount(0);
  await page.getByRole("button", { name: "View official map context" }).click();
  await expect(page.getByText("Current BC wildfire information")).toBeVisible();
  const testFire = page
    .getByRole("list", { name: "Matching this question" })
    .getByRole("button", { name: /Test Fire Out of Control/ });
  await expect(testFire).toBeVisible();
  await expect(page.getByText(/Some official layers are unavailable: evacuation/)).toBeVisible();
  await expect(testFire).toHaveAccessibleName(/source updated/i);
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toBeVisible();
  const marker = page.locator(".live-map__record-geometry").first();
  await expect(marker).toBeVisible();
  if (testInfo.project.name === "desktop") {
    await marker.dispatchEvent("click");
    await expect(page.locator(".leaflet-popup").getByText("Test Fire", { exact: true })).toBeVisible();
  } else {
    await testFire.press("Enter");
    await expect(testFire.locator("..").locator("..")).toHaveClass(/live-list__selected/);
  }
  const limitations = page.getByLabel("Answer limitations");
  await limitations.getByText("Why does FireLens say this?").click();
  await expect(limitations.getByText("No matching record is not a safety determination.", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Official wildfire records map" })
      .getByText(/The map is not a safety determination/),
  ).toBeVisible();
  await expect(page.getByText("Answer evidence and support")).toHaveCount(0);
});

test("uses neutral live-summary copy and exposes category-only feedback", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Is there an active wildfire near me right now?");
  await page.getByLabel("Send question").click();

  const conversation = page.getByLabel("Question and answer");
  await expect(conversation.getByText("Official records returned", { exact: true })).toBeVisible();
  await expect(conversation.getByText(/BC Wildfire Service · source updated 2026-07-28T11:55:00Z/)).toBeVisible();
  await expect(conversation.getByText(/does not change the answer/i)).toHaveCount(1);
  const issueButton = conversation.getByRole("button", { name: "Report" });
  await expect(issueButton).toHaveAttribute("aria-expanded", "false");
  await issueButton.click();
  await expect(issueButton).toHaveAttribute("aria-expanded", "true");
  await expect(conversation.getByRole("button", { name: "Stale or wrong live data" })).toBeVisible();
});

test("closes an open map popup cleanly while repeatedly changing answer context", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Popup lifecycle requires the desktop marker interaction.");
  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByRole("button", { name: "View official map context" })).toBeVisible();

  for (let cycle = 0; cycle < 8; cycle += 1) {
    await page.getByRole("button", { name: "View official map context" }).click();
    const marker = page.locator(".live-map__record-geometry").first();
    await expect(marker).toBeVisible();
    await marker.dispatchEvent("click");
    await expect(page.locator(".leaflet-popup").getByText("Test Fire", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Evidence" }).click();
    await expect(page.getByText("Official map context", { exact: true })).toHaveCount(0);
  }

  expect(pageErrors.map((error) => error.stack ?? error.message)).toEqual([]);
});

test("shows street context with attributed OpenStreetMap tiles", async ({ page }) => {
  const osmTileRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("tile.openstreetmap.org")) osmTileRequests.push(request.url());
  });
  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByLabel("Question and answer").getByText("Current official information: Test Fire is Out of Control.")).toBeVisible();
  await page.getByRole("button", { name: "View official map context" }).click();
  await expect(page.getByRole("button", { name: /Test Fire Out of Control/ })).toBeVisible();
  await expect(page.getByText(/Tile requests go directly to OpenStreetMap/)).toBeVisible();
  await expect(page.getByRole("link", { name: "OpenStreetMap" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Government of BC provincial boundary" })).toBeVisible();
  expect(osmTileRequests.length).toBeGreaterThan(0);
});

test("shows stale and partial-layer state without hiding records", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Show stale official wildfire records");
  await page.getByLabel("Send question").click();
  await page.getByRole("button", { name: "View official map context" }).click();
  await expect(page.getByText("BC wildfire information — includes stale records")).toBeVisible();
  await expect(page.getByLabel("Question and answer").getByText(/Cached official information \(refresh failed\)/)).toBeVisible();
  await expect(page.getByText("Official cached records", { exact: true })).toHaveCount(3);
  const staleWarning = page.getByRole("status").filter({ hasText: "Cached official records; refresh failed" });
  await expect(staleWarning).toBeVisible();
  await expect(page.getByText("Current BC wildfire information")).toHaveCount(0);
  await expect(
    page.getByRole("list", { name: "Matching this question" })
      .getByRole("button", { name: /Cached Test Fire Out of Control/ }),
  ).toBeVisible();
  expect(await staleWarning.evaluate((warning) => Boolean(
    warning.compareDocumentPosition(document.querySelector(".live-list")!) & Node.DOCUMENT_POSITION_FOLLOWING,
  ))).toBe(true);
  const staleRecord = page.getByRole("list", { name: "Matching this question" });
  await staleRecord.getByText("Record details").click();
  await expect(staleRecord.getByText(/stale · BC Wildfire Service/)).toBeVisible();
  await expect(page.getByText(/Some official layers are unavailable: evacuation/)).toBeVisible();
});

test("keeps the workspace usable at a 320px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/");
  await expect(page.getByLabel("Ask FireLens a question")).toBeVisible();
  await expect(page.getByText("How it works", { exact: true })).toBeVisible();
  const employerControl = page.getByRole("button", { name: "How FireLens works", exact: true });
  const employerControlBox = await employerControl.boundingBox();
  expect(employerControlBox?.width).toBeGreaterThanOrEqual(44);
  expect(employerControlBox?.height).toBeGreaterThanOrEqual(44);
  await expect(page.getByLabel("Official wildfire records map")).toHaveCount(0);
  await page.getByRole("button", { name: "Explore live map" }).click();
  await expect(page.getByLabel("Official wildfire records map")).toBeVisible();
  const overflowX = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflowX).toBeLessThanOrEqual(0);
});

test("keeps primary controls reachable at a 640px 200-percent zoom proxy", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 400 });
  await page.goto("/");
  await expect(page.getByLabel("Ask FireLens a question")).toBeVisible();
  await expect(page.getByRole("link", { name: "Skip to conversation" })).toHaveAttribute("href", "#conversation");
  const overflowX = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflowX).toBeLessThanOrEqual(0);
});

test("keeps the assistant answer in view on a short mobile overlay", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("What belongs in a grab-and-go bag?");
  await page.getByLabel("Send question").click();
  const answer = page.locator("#conversation .assistant-message .answer-lead");
  await expect(answer).toHaveText("Prepare water, food, and medication.");
  await expect(answer).toBeInViewport();
  await expect(page.getByLabel("Answer limitations")).toBeInViewport();
});

test("places skip links first and limitations after the answer", async ({ page }) => {
  await page.goto("/");
  const skipConversation = page.getByRole("link", { name: "Skip to conversation" });
  await skipConversation.focus();
  await expect(skipConversation).toBeVisible();
  await skipConversation.press("Enter");
  await expect(page.locator("#conversation")).toBeInViewport();
  await page.getByLabel("Ask FireLens a question").fill("What belongs in a grab-and-go bag?");
  await page.getByLabel("Send question").click();
  const limitations = page.getByLabel("Answer limitations");
  await expect(limitations).toBeVisible();
  await expect(page.locator("#conversation .assistant-message .answer-lead")).toHaveText(
    "Prepare water, food, and medication.",
  );
  expect(await page.evaluate(() => {
    const warning = document.querySelector('[aria-label="Answer limitations"]');
    const answer = document.querySelector("#conversation .assistant-message .answer-lead");
    return Boolean(
      warning
      && answer
      && (warning.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_PRECEDING),
    );
  })).toBe(true);
});

test("opens an official source link with keyboard activation", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Is there an active wildfire near me right now?");
  await page.getByLabel("Send question").press("Enter");
  await page.getByRole("button", { name: "View official map context" }).click();
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

test("shows summary map and records for analytical live questions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Show wildfire distribution by status across B.C.");
  await page.getByLabel("Send question").click();
  await expect(page.getByRole("region", { name: "Analysis view" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis view" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Incident records by fire centre" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Summary", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Map", exact: true })).toHaveAttribute("aria-selected", "false");
  await expect(page.getByRole("tab", { name: "Records", exact: true })).toHaveAttribute("aria-selected", "false");
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "View official map context" })).toHaveCount(0);
  const overflowX = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflowX).toBeLessThanOrEqual(0);
});

test("opens analytical answers on Summary and resets the selected surface for a new answer", async ({ page }) => {
  await page.goto("/");
  const question = page.getByLabel("Ask FireLens a question");
  await question.fill("Map wildfire distribution by status across B.C.");
  await page.getByLabel("Send question").click();

  const map = page.getByRole("tab", { name: "Map", exact: true });
  const summary = page.getByRole("tab", { name: "Summary", exact: true });
  const records = page.getByRole("tab", { name: "Records", exact: true });
  await expect(map).toHaveAttribute("aria-selected", "false");
  await expect(summary).toHaveAttribute("aria-selected", "true");

  await map.click();
  await expect(map).toHaveAttribute("aria-selected", "true");
  await records.click();
  await expect(records).toHaveAttribute("aria-selected", "true");
  await page.getByText("Technical evidence", { exact: true }).click();
  await page.getByRole("button", { name: "Inspect answer evidence" }).click();
  await expect(records).toHaveAttribute("aria-selected", "true");

  await question.fill("Show a new distribution by status across B.C.");
  await page.getByLabel("Send question").click();
  await expect(summary).toHaveAttribute("aria-selected", "true");
  await expect(map).toHaveAttribute("aria-selected", "false");
});

test("offers retry for a transient provider outage", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("Simulate provider unavailable");
  await page.getByLabel("Send question").click();
  await expect(page.getByRole("status", { name: "We couldn't complete this question" })).toBeVisible();
  await expect(page.getByText("No wildfire status was shown or inferred.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry this question" })).toBeVisible();
});

test("respects reduced motion without hiding the answer", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByLabel("Ask FireLens a question").fill("What belongs in a grab-and-go bag?");
  await page.getByLabel("Send question").click();
  await expect(page.locator("#conversation .assistant-message .answer-lead")).toHaveText(
    "Prepare water, food, and medication.",
  );
  const transition = await page.locator("#conversation").evaluate((node) => getComputedStyle(node).transitionDuration);
  expect(transition === "0s" || transition === "").toBeTruthy();
});
