import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e-real",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:8766",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run build && PYTHONPATH=../../src ../../.venv/bin/python -m uvicorn e2e_fixture_app:app --app-dir ../../tests --host 127.0.0.1 --port 8766 --log-level critical --no-access-log",
    url: "http://127.0.0.1:8766/api/v1/health/live",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
