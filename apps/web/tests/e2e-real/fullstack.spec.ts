import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const LOCAL_ORIGIN = "http://127.0.0.1:8766";

async function localOnly(context: BrowserContext, page: Page): Promise<string[]> {
  const attemptedExternal: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(LOCAL_ORIGIN)) attemptedExternal.push(request.url());
  });
  await context.route("**/*", async (route) => {
    if (route.request().url().startsWith(LOCAL_ORIGIN)) {
      await route.continue();
      return;
    }
    await route.abort("blockedbyclient");
  });
  return attemptedExternal;
}

async function ask(page: Page, question: string): Promise<void> {
  const input = page.getByLabel("Ask FireLens a question");
  await input.fill(question);
  await input.press("Enter");
}

test("real serializer fails closed when a public claim has no publication authority", async ({
  context,
  page,
  request,
}) => {
  const attemptedExternal = await localOnly(context, page);
  const response = await request.post(`${LOCAL_ORIGIN}/api/v1/ask`, {
    data: {
      question: "What can FireLens do? malformed publication fixture",
      history: [],
      context: {},
    },
  });
  expect(response.status()).toBe(500);

  await page.goto("/");
  await ask(page, "What can FireLens do? malformed publication fixture");
  await expect(
    page.getByRole("alert", {
      name: "We couldn't complete this question",
    }),
  ).toBeVisible();
  await expect(page.getByText("Grounded in reviewed official sources")).toHaveCount(0);
  await expect(page.getByText("Reviewed structured claim")).toHaveCount(0);
  expect(attemptedExternal).toEqual([]);
});

test("answers the named Mountain Fire question first and leaves map context closed", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(page, "Where is Mountain Fire near Kelowna?");
  const answer = page.locator("#conversation .assistant-message .answer-lead");
  await expect(answer).toContainText("Mountain Fire");
  await expect(answer).toContainText("Out of Control");
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Analysis view" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "View official map context" })).toBeVisible();
  expect(attemptedExternal).toEqual([]);
});

test("uses the real API response to render an Okanagan distribution analysis", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(page, "Show the current wildfire distribution by status across the Okanagan.");
  const analysis = page.getByRole("region", { name: "Analysis view" });
  await expect(analysis).toBeVisible();
  await expect(analysis.getByRole("heading", { name: "Current official records, summarized" })).toBeVisible();
  await expect(analysis.getByLabel("Wildfires by status")).toContainText("Out of Control");
  await expect(analysis.getByLabel("Wildfires by status")).toContainText("Being Held");
  await expect(analysis.getByLabel("Wildfires by status")).toContainText("Under Control");
  await expect(page.getByRole("region", { name: "Official wildfire records map" })).toHaveCount(0);
  expect(attemptedExternal).toEqual([]);
});

test("keeps current records and reviewed evacuation-alert meaning in separate trust lanes", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(
    page,
    "What current fires are near Kelowna, and what does an evacuation alert mean?",
  );
  const conversation = page.getByLabel("Question and answer");
  await expect(conversation.getByText("Current official records", { exact: true })).toBeVisible();
  await expect(conversation.getByText("Reviewed preparedness guidance", { exact: true })).toBeVisible();
  const currentRecords = conversation
    .locator(".answer-section")
    .filter({ hasText: "Current official records" })
    .first();
  await expect(currentRecords).toBeVisible();
  await expect(currentRecords).not.toContainText(
    "If you are under an evacuation alert, be ready to leave on short notice.",
  );
  await expect(conversation.getByText(
    "If you are under an evacuation alert, be ready to leave on short notice.",
    { exact: true },
  ).first()).toBeVisible();
  await expect(page.getByText("Reviewed structured claim", { exact: true }).first()).toBeVisible();
  await expect(conversation.getByText("Official current records", { exact: true })).toBeVisible();
  expect(attemptedExternal).toEqual([]);
});

test("an empty official result is explicit and never rendered as an all-clear", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(page, "Are there current wildfires near Emptytown?");
  const conversation = page.getByLabel("Question and answer");
  await expect(conversation).toContainText("No matching official");
  await expect(conversation).toContainText(/not (?:an )?all-clear|does not mean the area is safe/i);
  await expect(conversation.getByText(/safe to return|safe here|all clear/i)).toHaveCount(0);
  expect(attemptedExternal).toEqual([]);
});

test("names an unavailable evacuation layer while preserving an available incident", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(
    page,
    "Show the current wildfire distribution by status and evacuation orders near Outage Ridge.",
  );
  const conversation = page.getByLabel("Question and answer");
  const analysis = page.getByRole("region", { name: "Analysis view" });
  await expect(analysis).toBeVisible();
  await analysis.getByRole("button", { name: "Records", exact: true }).click();
  await expect(analysis.getByText("Mountain Fire", { exact: true })).toBeVisible();
  await expect(page.getByText(/Some official layers are unavailable: evacuation/)).toBeVisible();
  await expect(conversation).toContainText(/not an all-clear/i);
  expect(attemptedExternal).toEqual([]);
});

test("preserves exact structured-claim authority on the proof card", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  await ask(page, "What does an evacuation alert mean?");
  await page.getByRole("button", {
    name: /Review technical evidence for If you are under an evacuation alert/,
  }).click();
  const proof = page.getByRole("article", {
    name: "Proof card for If you are under an evacuation alert, be ready to leave on short notice.",
  });
  await expect(proof).toBeVisible();
  await expect(proof).toContainText("Reviewed structured claim");
  await expect(proof.getByText("Technical binding details")).toBeVisible();
  await proof.getByText("Technical binding details").click();
  await expect(proof).toContainText("structured reviewed");
  await expect(proof).toContainText("approved_static");
  expect(attemptedExternal).toEqual([]);
});

test("keeps a real-stack answer usable on a narrow mobile viewport", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await ask(page, "Where is Mountain Fire near Kelowna?");
  const answer = page.locator("#conversation .assistant-message .answer-lead");
  await expect(answer).toContainText("Mountain Fire");
  await expect(answer).toBeInViewport();
  const overflowX = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflowX).toBeLessThanOrEqual(0);
  expect(attemptedExternal).toEqual([]);
});

test("supports keyboard submission and skip-link navigation against the real stack", async ({
  context,
  page,
}) => {
  const attemptedExternal = await localOnly(context, page);
  await page.goto("/");
  const skip = page.getByRole("link", { name: "Skip to conversation" });
  await skip.focus();
  await expect(skip).toBeVisible();
  await skip.press("Enter");
  await expect(page.locator("#conversation")).toBeInViewport();
  await ask(page, "What does an evacuation alert mean?");
  await expect(page.locator("#conversation .assistant-message .answer-lead")).toContainText(
    "be ready to leave on short notice",
  );
  expect(attemptedExternal).toEqual([]);
});
