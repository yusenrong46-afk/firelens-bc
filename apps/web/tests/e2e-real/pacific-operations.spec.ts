import { expect, test } from "@playwright/test";
import axe from "axe-core";

test.beforeEach(async ({ context }) => {
  await context.route("**/*", async (route) => {
    if (route.request().url().startsWith("http://127.0.0.1:8766/")) await route.continue();
    else await route.abort("blockedbyclient");
  });
});

const viewports = [
  [1536, 1024], [1440, 900], [1366, 768], [1024, 768],
  [768, 1024], [390, 844], [320, 844],
];
for (const width of [1024, 1280, 1440]) {
  test(`empty and active partial explanations remain readable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    for (const [state, question] of [["empty", "Are there current wildfires near Emptytown?"], ["partial", "Show fires and evacuation orders near Outage Ridge"]]) {
      const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/ask"));
      await page.getByLabel("Ask FireLens a question").fill(question!);
      await page.getByLabel("Ask FireLens a question").press("Enter");
      const response = await (await pending).json();
      if (state === "partial") expect(response.unavailable_layers).toContain("evacuation");
      else expect(response.live_results).toEqual([]);
      const summary = page.locator(state === "empty" ? ".status-banner__summary" : ".assistant-message .answer-lead").last();
      await expect(summary).toBeVisible();
      if (state === "partial") await expect(summary).toContainText(/evacuation.*unavailable/i);
      expect((await summary.boundingBox())!.width).toBeGreaterThan(200);
      await page.screenshot({ path: info.outputPath(`${state}.png`), fullPage: true });
    }
  });
}
for (const [width, height] of viewports) {
  test(`Pacific Operations at ${width}x${height}`, async ({ page }, info) => {
    await page.setViewportSize({ width: width!, height: height! });
    const errors: string[] = [];
    const failedAssets: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.url().includes("/assets/") && response.status() >= 400) failedAssets.push(response.url());
    });
    await page.goto("/");
    const composer = page.getByLabel("Ask FireLens a question");
    await expect(composer).toHaveCount(1);
    await expect(composer).toBeVisible();
    await page.screenshot({ path: info.outputPath("idle.png"), fullPage: true });
    const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/ask"));
    await composer.fill("What wildfires are near Kelowna?");
    await composer.press("Enter");
    const answer = await (await pending).json();
    expect(answer.live_results.length).toBeGreaterThan(1);
    await expect(page.getByRole("region", { name: "Live answer summary" })).toBeVisible();
    await page.getByRole("button", { name: /View all matching records on the map/ }).click();
    await expect(page.locator(".leaflet-container").first()).toBeVisible();
    if (width! < 1024) {
      // Near the document end, the rail cannot align to y=0. Its map must
      // nevertheless be fully within the viewport after explicit navigation.
      await expect(page.locator(".leaflet-container").first()).toBeInViewport({ ratio: 1 });
      await expect(page.locator(".pc-map-rail")).toBeFocused();
    }
    const second = page.locator(".live-answer-secondary button").first();
    await second.click();
    await expect(second).toHaveClass(/is-selected/);
    const source = page.getByRole("complementary", { name: "Official sources" });
    await expect(source).toContainText("For Bear Creek Fire");
    await expect(source).toContainText("Source updated");
    await expect(source).toContainText("FireLens fetched");
    await expect(source.getByRole("link", { name: "BC Wildfire Service", exact: true })).toHaveAttribute("href", answer.live_results[1].source_url);
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("nearby.png"), fullPage: true });
    if (width === 1536 || width === 390) {
      await page.evaluate(axe.source);
      const violations = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: () => Promise<{ violations: { id: string; nodes: { target: string[] }[] }[] }> } }).axe;
        return (await axe.run()).violations.map(({ id, nodes }) => ({ id, targets: nodes.map((node) => node.target) }));
      });
      expect(violations).toEqual([]);
    }
    expect(errors).toEqual([]);
    expect(failedAssets).toEqual([]);
  });
}
