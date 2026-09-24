/** Versioned current-interface lane; preserve the historical configuration. */
import { defineConfig } from "@playwright/test";
import historical from "./playwright.config";

export default defineConfig({
  ...historical,
  testDir: "./tests/e2e-product-v2",
});
