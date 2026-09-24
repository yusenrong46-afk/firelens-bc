import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { reserveSubmission, assertReservedDispatch } from "../scripts/release-smoke-gate.mjs";
const origin = "https://firelens-fixture.vercel.app";
const bankBytes = Buffer.from("frozen bank");
async function setup() { return { directory: await mkdtemp(path.join(tmpdir(), "firelens-smoke-gate-")), phase: "preview", id: "S01", commit: "a".repeat(40), bankBytes, origin, approvedOrigin: origin, last: null, reviewed: {} }; }
test("concurrent duplicate reservation admits one and restart cannot reuse it", async () => {
  const options = await setup();
  const results = await Promise.allSettled(Array.from({ length: 8 }, () => reserveSubmission(options)));
  assert.equal(results.filter(r => r.status === "fulfilled").length, 1);
  await assert.rejects(reserveSubmission(options), /EEXIST/);
});
test("all 24 atomic slots remain bounded across concurrent phases", async () => {
  const options = await setup();
  const results = await Promise.allSettled(["preview", "production"].flatMap(phase => Array.from({ length: 10 }, (_, i) => reserveSubmission({ ...options, phase, id: `S${String(i + 1).padStart(2, "0")}` }))).concat(Array.from({ length: 5 }, (_, i) => reserveSubmission({ ...options, phase: "corrective", id: `S${String(i + 1).padStart(2, "0")}` }))));
  assert.equal(results.filter(r => r.status === "fulfilled").length, 24);
  assert.equal((await readdir(options.directory)).filter(f => f.startsWith("slot-")).length, 24);
});
test("failed prerequisite and unapproved origin consume no slot", async () => {
  const options = await setup();
  await assert.rejects(reserveSubmission({ ...options, prerequisite: "S01", last: "S01", reviewed: { S01: { verdict: "CONFIRMED FAIL" } } }), /prerequisite/);
  await assert.rejects(reserveSubmission({ ...options, origin: "https://elsewhere.example" }), /destination/);
  assert.equal((await readdir(options.directory)).length, 0);
});
test("unknown prices/costs never block; actual history and candidate binding do", async () => {
  const options = await setup();
  const receipt = await reserveSubmission(options);
  const binding = { origin, commit: options.commit, bankBytes, actualHistory: [], expectedHistory: [] };
  await assert.rejects(assertReservedDispatch(receipt, { ...binding, actualHistory: [{ role: "user", content: "invented" }] }), /history/);
  await assert.rejects(assertReservedDispatch(receipt, { ...binding, commit: "b".repeat(40) }), /identity/);
  await assertReservedDispatch(receipt, binding);
  await assert.rejects(assertReservedDispatch(receipt, binding), /duplicate/);
  const stored = JSON.parse(await readFile(receipt.receipt_path));
  assert.equal(stored.state, "dispatch_started");
  assert.equal(stored.cost_status, "unknown");
  assert.equal(stored.known_cost_usd, null);
  assert.ok(!JSON.stringify(stored).includes("invented"));
});
