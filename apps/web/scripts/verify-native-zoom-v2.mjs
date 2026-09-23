#!/usr/bin/env node
/** Versioned product UI native Chromium zoom; historical zoom driver preserved. */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { chromium } from "@playwright/test";
import { loadProtocol, installDeterministicRoutes, driveState } from "./qualify-frontend-surface.mjs";

const [baseUrl, label, outputDirectory] = process.argv.slice(2);
if (!baseUrl || !["before", "after"].includes(label) || !outputDirectory || !["127.0.0.1", "localhost"].includes(new URL(baseUrl).hostname)) {
  throw new Error("Usage: node scripts/verify-native-zoom.mjs <loopback URL> <before|after> <output directory>");
}
await mkdir(outputDirectory, { recursive: true });
const extension = await mkdtemp(path.join(tmpdir(), "firelens-native-zoom-"));
await writeFile(path.join(extension, "manifest.json"), JSON.stringify({ manifest_version: 3, name: "Local native zoom verification", version: "1.0", permissions: ["tabs"], background: { service_worker: "worker.js" } }));
await writeFile(path.join(extension, "worker.js"), "chrome.runtime.onInstalled.addListener(() => {});\n");
const protocol = await loadProtocol(path.resolve("../../data/evaluation/frontend_surface.v2.yaml"));
const rows = [];
let context;
try {
  context = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, baseURL: baseUrl, locale: protocol.execution_environment.locale, timezoneId: protocol.execution_environment.timezone_id, reducedMotion: "reduce", viewport: { width: 1440, height: 1000 }, args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`] });
  const worker = context.serviceWorkers()[0] ?? await context.waitForEvent("serviceworker");
  for (const id of ["grounded", "live"]) {
    const page = await context.newPage();
    const routes = await installDeterministicRoutes(page);
    try {
      await page.goto(baseUrl);
      await worker.evaluate(async (url) => {
        const tabs = await chrome.tabs.query({ url: `${url}/*` });
        await chrome.tabs.setZoom(tabs.at(-1).id, 1);
      }, baseUrl.replace(/\/$/, ""));
      await driveState(page, protocol.states.find(state => state.id === id), protocol);
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const observed = await page.evaluate(() => ({ inner_width: innerWidth, device_pixel_ratio: devicePixelRatio, overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth), css_zoom: getComputedStyle(document.documentElement).zoom }));
        assert.equal(observed.inner_width, width);
        assert.equal(observed.overflow, 0);
        const screenshot = path.join(outputDirectory, `${label}--${id}--${width}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        rows.push({ state_id: id, label, native_browser_zoom: 1, browser_viewport: { width, height: 1000 }, observed, screenshot, passed: true });
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      const zoom = await worker.evaluate(async (url) => {
        const tabs = await chrome.tabs.query({ url: `${url}/*` });
        const tab = tabs.at(-1);
        await chrome.tabs.setZoom(tab.id, 2);
        return chrome.tabs.getZoom(tab.id);
      }, baseUrl.replace(/\/$/, ""));
      assert.equal(zoom, 2);
      await driveState(page, protocol.states.find(state => state.id === id), protocol);
      await page.evaluate(() => window.scrollTo(0, 0));
      const observed = await page.evaluate(() => ({ inner_width: innerWidth, device_pixel_ratio: devicePixelRatio, overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth), css_zoom: getComputedStyle(document.documentElement).zoom }));
      assert.equal(observed.inner_width, 720);
      assert.equal(observed.device_pixel_ratio, 2);
      assert.equal(observed.css_zoom, "1");
      assert.equal(observed.overflow, 0);
      const screenshot = path.join(outputDirectory, `${label}--${id}--native-200.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      rows.push({ state_id: id, label, native_browser_zoom: zoom, browser_viewport: { width: 1440, height: 1000 }, observed, screenshot, passed: true });
    } catch (error) {
      const screenshot = path.join(outputDirectory, `${label}--${id}--native-200-failure.png`);
      await page.screenshot({ path: screenshot, fullPage: true }).catch(() => {});
      rows.push({ state_id: id, label, passed: false, screenshot, error: String(error?.stack ?? error) });
    } finally { routes.releaseLoading(); await page.close(); }
  }
} finally {
  await context?.close();
  await rm(extension, { recursive: true, force: true });
}
const report = { scope: "Offline 1440/390/320px and native Chromium 200% zoom rehearsal; not surface qualification", fixture_clock: "2026-08-06T12:00:00Z", protocol_id: protocol.protocol_id, base_url: baseUrl, label, rows, passed: rows.length === 8 && rows.every(row => row.passed) };
await writeFile(path.join(outputDirectory, `${label}--native-200.json`), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;
