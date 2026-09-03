import { defineConfig, devices } from "@playwright/test";

/**
 * Product Reality Gate.
 *
 * Runs the critical user journeys against a *running* FireLens (local,
 * preview, or production) instead of fixtures. Point it at a deployment with
 * FIRELENS_REALITY_URL. Real official data is used, so assertions describe
 * product behaviour (records appear, sources are visible, Home works, no
 * missing assets), never specific fire names or counts.
 */
export default defineConfig({
  testDir: "./tests/reality",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [["line"], ["json", { outputFile: process.env.FIRELENS_REALITY_REPORT ?? "test-results/reality-gate.json" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.FIRELENS_REALITY_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
