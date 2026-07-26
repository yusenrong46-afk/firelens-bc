import { expect, test } from "@playwright/test";

const answer = {
  status: "answer",
  trace_id: "e2e-trace",
  answer: "Prepare water, food, and medication.",
  claims: [{
    claim_id: "C1",
    text: "Prepare water, food, and medication.",
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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/ask", async (route) => {
    const question = route.request().postDataJSON().question as string;
    if (question.includes("active wildfire")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "abstention",
          trace_id: "live-trace",
          answer: "This question requires current official information.",
          claims: [],
          evidence: [],
          limitations: ["Static guidance cannot establish current status."],
          reason_code: "live_data_required",
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
  await expect(page.locator("mark")).toHaveText("Food & water");
  await expect(page.getByText("PreparedBC")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
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
