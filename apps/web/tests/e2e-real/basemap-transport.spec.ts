import { expect, test } from "@playwright/test";
import { localOrigin, openMapRecords } from "../browserNavigation";

const tileUrl = /^https:\/\/(?:[abc]\.)?tile\.openstreetmap\.org\//;
const tileImage = '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#edf2e8"/></svg>';
const instant = "2026-08-24T15:02:00Z";

for (const mode of ["success", "403", "network failure"] as const) {
  test(`basemap ${mode}: origin-only referrer and usable official records`, async ({ page, context }) => {
    const tiles: { url: string; headers: Record<string, string> }[] = [];
    const asks: string[] = [];
    await page.clock.setFixedTime(new Date(instant));
    page.on("request", request => { if (request.url().endsWith("/api/v1/ask")) asks.push(request.url()); });
    await context.route("**/*", async route => {
      const request = route.request();
      if (request.url().startsWith(`${localOrigin}/`)) return route.continue();
      if (!tileUrl.test(request.url())) return route.abort("blockedbyclient");
      tiles.push({ url: request.url(), headers: await request.allHeaders() });
      if (mode === "network failure") return route.abort("failed");
      if (mode === "403") return route.fulfill({ status: 403, contentType: "text/plain", body: "Access blocked: fixture" });
      return route.fulfill({ status: 200, contentType: "image/svg+xml", body: tileImage });
    });
    await page.route("**/api/v1/live/map*", route => route.fulfill({ json: {
      generated_at: instant, aggregate_freshness: "fresh", limitations: [],
      results: [{ result_id: "incident:tile-control", kind: "incident", authority: "BC Wildfire Service",
        source_url: "https://wildfiresituation.nrs.gov.bc.ca/", source_updated_at: instant, retrieved_at: instant,
        freshness: "fresh", name: "Tile control fire", status: "Under Control",
        geometry: { type: "Point", coordinates: [-119.43, 49.91] } }],
      layer_statuses: ["incident", "perimeter", "evacuation"].map(kind => ({ kind, available: true,
        freshness: "fresh", retrieved_at: instant, source_updated_at: instant, matching_result_count: kind === "incident" ? 1 : 0 })),
    } }));
    const document = await page.goto("/?question=private-canary&lat=49.123456&lon=-123.654321#private-fragment");
    expect(document?.headers()["referrer-policy"]).toBe("no-referrer");
    await expect(page.getByRole("region", { name: "Official wildfire records map" })).toBeVisible();
    await expect.poll(() => tiles.length).toBeGreaterThan(0);
    for (const tile of tiles) {
      expect(tile.headers.referer).toBe(`${localOrigin}/`);
      expect(new URL(tile.url).hostname).toBe("tile.openstreetmap.org");
      expect(JSON.stringify(tile.headers)).not.toMatch(/private-canary|49\.123456|123\.654321|private-fragment/);
    }
    const map = await openMapRecords(page);
    const record = map.getByRole("button", { name: /^Tile control fire Under Control/ });
    await expect(record).toBeVisible();
    await record.click();
    await expect(record.locator("xpath=ancestor::li[1]")).toHaveClass(/live-list__selected/);
    await expect(map.locator('.live-map__record-geometry[data-result-id="incident:tile-control"]')).toBeVisible();
    const warning = map.getByText(/Street-map tiles failed to load/);
    if (mode === "success") {
      await expect(map.locator(".leaflet-tile-loaded").first()).toBeVisible();
      await expect(warning).toHaveCount(0);
    } else await expect(warning).toBeVisible();
    expect(asks).toHaveLength(0);
  });
}
