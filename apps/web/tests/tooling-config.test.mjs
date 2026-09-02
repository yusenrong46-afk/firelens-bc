import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const packageJson = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const playwrightConfig = await readFile(
  new URL("../playwright.config.ts", import.meta.url),
  "utf8",
);
const realPlaywrightConfig = await readFile(
  new URL("../playwright.real.config.ts", import.meta.url),
  "utf8",
);
const makefile = await readFile(new URL("../../../Makefile", import.meta.url), "utf8");

test("Playwright refuses to reuse an unrelated server on the test port", () => {
  assert.match(playwrightConfig, /reuseExistingServer:\s*false/);
});

test("the real-stack harness has a dedicated test rate budget", async () => {
  const runtimeConfig = await readFile(
    new URL("../../../src/firelens/config.py", import.meta.url),
    "utf8",
  );
  assert.match(realPlaywrightConfig, /FIRELENS_RATE_LIMIT=1000/);
  assert.match(runtimeConfig, /anonymous_rate_limit: int = Field\(default=30,/);
});

test("local setup installs the browser required by the end-to-end suite", () => {
  assert.equal(packageJson.scripts["setup:browsers"], "playwright install chromium");
  const setupRecipe = makefile.match(/^setup:\n((?:\t.*\n)+)/m)?.[1] ?? "";
  assert.match(setupRecipe, /npm --prefix \$\(FRONTEND\) run setup:browsers/);
});

test("the standalone Sites test rebuilds dist before inspecting it", () => {
  assert.match(packageJson.scripts["test:sites"], /^npm run build && /);
});

test("production build typechecks the OpenAPI frontend types before bundling", () => {
  assert.equal(packageJson.scripts.typecheck, "tsc --noEmit");
  assert.match(packageJson.scripts.build, /^npm run typecheck && /);
});

test("quote-only answers do not read a non-existent publication.source_title", async () => {
  const answerBody = await readFile(
    new URL("../src/features/ask/AnswerBody.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(answerBody, /publication\?\.source_title/);
  assert.match(answerBody, /proof_cards\?\.\[0\]\?\.source_title/);
});

test("warnings, provenance, and fetch time stay visible in CSS", async () => {
  const css = await readFile(new URL("../src/app/styles.css", import.meta.url), "utf8");
  assert.doesNotMatch(css, /\.status-banner__retrieved\s*\{[^}]*display:\s*none/);
  assert.match(css, /\.live-map__warning\s*\{/);
  assert.match(css, /\.live-map__legend\s*\{/);
  const mobile = css.split("@media (max-width: 620px)")[1] ?? "";
  assert.doesNotMatch(mobile, /live-map__warning[^}]*display:\s*none/);
  assert.doesNotMatch(mobile, /status-banner__retrieved[^}]*display:\s*none/);
});

test("frontend derivation constants match the Python geodesic binding", async () => {
  const python = await readFile(
    new URL("../../../src/firelens/live_contracts.py", import.meta.url),
    "utf8",
  );
  const frontend = await readFile(
    new URL("../src/features/ask/proofPresentation.ts", import.meta.url),
    "utf8",
  );
  assert.match(python, /GEODESIC_CRS = "EPSG:4326"/);
  assert.match(python, /COORDINATE_ORDER = "longitude_latitude"/);
  assert.match(python, /DISTANCE_UNIT = "km"/);
  assert.match(python, /pyproj\.Geod\.inv WGS84 after shapely nearest_points/);
  assert.match(frontend, /crs: "EPSG:4326"/);
  assert.match(frontend, /coordinate_order: "longitude_latitude"/);
  assert.match(frontend, /units: "km"/);
  assert.match(frontend, /pyproj\.Geod\.inv WGS84 after shapely nearest_points/);
  assert.doesNotMatch(frontend, /units:\s*"miles"/);
  assert.doesNotMatch(frontend, /crs:\s*"EPSG:3857"/);
});
