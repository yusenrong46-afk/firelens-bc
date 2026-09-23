/** Navigation adapter for the Atlas answer-sheet UI; assertions stay in each suite. */
import { expect, type Page } from "@playwright/test";
import { localBrowserOrigin } from "./localBrowserOrigin";

export const localOrigin = localBrowserOrigin((globalThis as unknown as { process?: { env: Record<string, string | undefined> } }).process?.env.FIRELENS_E2E_BASE_URL) ?? "http://127.0.0.1:8766";

export async function openComposer(page: Page) {
  const input = page.locator('input[aria-label="Ask FireLens a question"]:visible');
  if (!await input.count()) await page.getByRole("button", { name: "Ask FireLens", exact: true }).click();
  await expect(input).toBeVisible();
  return input;
}

export async function goHome(page: Page) {
  // Submission can close the dialog between visibility inspection and click.
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "FireLens home", exact: true }).click();
  await expect(page.getByRole("main", { name: "Find wildfire information" })).toBeVisible();
}

export async function menuAction(page: Page, name: string) {
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  await page.getByRole("dialog", { name: "FireLens menu", exact: true }).getByRole("button", { name, exact: true }).click();
}

export async function openSources(page: Page) {
  const details = page.locator("#conversation details.sheet-sources");
  await expect(details).toBeVisible();
  if (!await details.evaluate(node => (node as HTMLDetailsElement).open)) {
    await details.locator(":scope > summary").click();
  }
}

export async function openMatchingRecords(page: Page) {
  const details = page.locator("#conversation details.sheet-records");
  await expect(details).toBeVisible();
  if (!await details.evaluate(node => (node as HTMLDetailsElement).open)) {
    await details.locator(":scope > summary").click();
  }
}

export async function openMapRecords(page: Page) {
  const map = page.getByRole("region", { name: "Official wildfire records map", exact: true });
  const mapTab = page.getByRole("tab", { name: "Map", exact: true });
  if (await mapTab.isVisible()) await mapTab.click();
  await expect(map).toBeVisible();
  const details = map.locator("details.atlas-live-records");
  if (await details.count() && !await details.evaluate(node => (node as HTMLDetailsElement).open)) {
    await details.locator(":scope > summary").click();
  }
  return map;
}

export async function openClaimDetails(page: Page) {
  await openSources(page);
  const details = page.locator("#conversation details.answer-details");
  await expect(details).toBeVisible();
  if (!await details.evaluate(node => (node as HTMLDetailsElement).open)) await details.locator(":scope > summary").click();
}
