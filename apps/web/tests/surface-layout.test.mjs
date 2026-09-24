import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "@playwright/test";
import { inspectLayoutAndCss } from "../scripts/qualify-frontend-surface.mjs";

// Exercise the real Chromium visibility model: closed <details> descendants can
// retain computed styles/boxes, but must not be treated as visible typography.
test("layout checks exclude closed disclosures and still reject visible small or clipped text", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<style>body,summary {font:16px sans-serif}.small {font-size:11px}.clipped {width:4px;height:4px;overflow:hidden}</style>
      <p class="small">visible small control</p><p class="clipped">visible clipped control</p>
      <details><summary>Open evidence</summary><p class="small">hidden small evidence</p><p class="clipped">hidden clipped evidence</p></details>`);
    const thresholds = { minimum_interactive_target_css_px: 24, minimum_body_text_css_px: 16, minimum_secondary_text_css_px: 12 };
    const closed = await inspectLayoutAndCss(page, thresholds);
    assert.deepEqual(closed.undersized_text_elements.map(item => item.text), ["visible small control"]);
    assert.deepEqual(closed.clipped_text_elements.map(item => item.text), ["visible clipped control"]);
    await page.locator("summary").click();
    const opened = await inspectLayoutAndCss(page, thresholds);
    assert.deepEqual(opened.undersized_text_elements.map(item => item.text), ["visible small control", "hidden small evidence"]);
    assert.deepEqual(opened.clipped_text_elements.map(item => item.text), ["visible clipped control", "hidden clipped evidence"]);
  } finally { await browser.close(); }
});
