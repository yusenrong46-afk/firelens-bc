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
  await page.route("**/api/v1/ask", async (route) => {
    const request = route.request().postDataJSON() as AskRequest;
    seenRequests.push(request);
    const question = request.question;
    if (question.includes("active wildfire")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "abstention",
          response_mode: "abstention",
          trace_id: "live-trace",
          answer: "This question requires current official information.",
          suggested_questions: [],
          claims: [],
          evidence: [],
          limitations: ["Static guidance cannot establish current status."],
          reason_code: "live_data_required",
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
  await page.getByLabel("Ask a preparedness question").fill("What belongs in a grab-and-go bag?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("Cited claims in this answer")).toBeVisible();
  await expect(page.getByText("Verified from FireLens sources")).toBeVisible();
  await expect(page.locator("mark")).toHaveText("Food & water");
  await expect(page.getByText("PreparedBC")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test("labels general background and exposes no evidence control", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask a preparedness question").fill("Why can embers be dangerous?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("General background", { exact: true })).toBeVisible();
  await expect(page.getByText("General background — no corpus evidence attached")).toBeVisible();
  await expect(page.getByText("Retrieved passage")).toHaveCount(0);
});

test("sends bounded conversation context and can clear it", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask a preparedness question").fill("What should I pack?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("2 of 6 turns in context")).toBeVisible();

  await page.getByLabel("Ask a preparedness question").fill("Why does that matter?");
  await page.getByLabel("Send question").click();
  await expect.poll(() => seenRequests.length).toBe(2);
  expect(seenRequests[1].history).toEqual([
    { role: "user", content: "What should I pack?" },
    { role: "assistant", content: answer.answer },
  ]);

  await page.getByLabel("Clear conversation history").click();
  await expect(page.getByText("0 of 6 turns in context")).toBeVisible();
  await page.getByLabel("Ask a preparedness question").fill("Fresh question");
  await page.getByLabel("Send question").click();
  await expect.poll(() => seenRequests.length).toBe(3);
  expect(seenRequests[2].history).toEqual([]);
});

test("redirects a completely tangent request", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask a preparedness question").fill("Can you debug JavaScript for me?");
  await page.getByLabel("Send question").click();
  await expect(page.getByText("Outside FireLens scope", { exact: true })).toBeVisible();
  await expect(page.getByText("Outside the FireLens collection", { exact: true })).toBeVisible();
});

test("shows a current-status abstention through keyboard submission", async ({ page }) => {
  await page.goto("/");
  const question = page.getByLabel("Ask a preparedness question");
  await question.fill("Is there an active wildfire near me right now?");
  await question.press("Enter");
  await expect(page.getByText("FireLens did not generate guidance")).toBeVisible();
  await expect(page.getByText("Reason: live_data_required")).toBeVisible();
  await expect(page.getByText("Cited claims in this answer")).toHaveCount(0);
});

test("offers retry for a transient provider outage", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask a preparedness question").fill("Simulate provider unavailable");
  await page.getByLabel("Send question").click();
  await expect(page.getByRole("button", { name: "Retry this question" })).toBeVisible();
});
