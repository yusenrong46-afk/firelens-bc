import { defineConfig, devices } from "@playwright/test";

import { localBrowserOrigin } from "./tests/localBrowserOrigin";

const externalBaseURL = localBrowserOrigin(process.env.FIRELENS_E2E_BASE_URL);

export default defineConfig({
  testDir: "./tests/e2e-real",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: externalBaseURL ?? "http://127.0.0.1:8766",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: externalBaseURL ? undefined : {
    command: "npm run build && FIRELENS_RATE_LIMIT=1000 PYTHONPATH=../../src ../../.venv/bin/python -m uvicorn e2e_fixture_app:app --app-dir ../../tests --host 127.0.0.1 --port 8766 --log-level critical --no-access-log",
    url: "http://127.0.0.1:8766/api/v1/health/live",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
