import { defineConfig, devices } from "@playwright/test";

import { localBrowserOrigin } from "./tests/localBrowserOrigin";

const externalBaseURL = localBrowserOrigin(process.env.FIRELENS_E2E_BASE_URL);

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: externalBaseURL ?? "http://127.0.0.1:4174" },
  webServer: externalBaseURL ? undefined : {
    command: "npm run dev -- --host 127.0.0.1 --port 4174",
    port: 4174,
    reuseExistingServer: false,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
