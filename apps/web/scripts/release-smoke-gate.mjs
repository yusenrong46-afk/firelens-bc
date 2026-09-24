/** Durable reservation controls for the finite map-first release campaign. */
import { open, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

export async function reserveSubmission({ directory, phase, id, commit, bankBytes, origin, approvedOrigin, prerequisite, last, reviewed }) {
  if (origin !== approvedOrigin || new URL(origin).protocol !== "https:" || !/^https:\/\/firelens[-a-z0-9.]*\.vercel\.app$/.test(origin)) throw Error("Unapproved destination");
  if (!/^[0-9a-f]{40}$/.test(commit) || !/^(preview|production|corrective)$/.test(phase) || !/^S(?:0[1-9]|10)(?:-C[1-4])?$/.test(id)) throw Error("Invalid campaign identity");
  if (prerequisite && (last !== prerequisite || reviewed?.[prerequisite]?.verdict !== "PASS")) throw Error("Actual reviewed prerequisite is unavailable");
  await mkdir(directory, { recursive: true });
  const receipt = { phase, id, commit, origin, bank_sha256: createHash("sha256").update(bankBytes).digest("hex"), state: "reserved", reserved_at: new Date().toISOString(), cost_status: "unknown", known_cost_usd: null, provider_attempt_details: "Not exposed by the remote response contract" };
  const identity = path.join(directory, `${phase}-${id}.json`);
  const handle = await open(identity, "wx");
  try { await handle.writeFile(JSON.stringify(receipt, null, 2)); await handle.sync(); } finally { await handle.close(); }
  // Fixed disjoint atomic slots enforce 10 preview + 10 production + 4 corrections
  // even across concurrent processes. Reservations and uncertain attempts are never reused.
  const slots = phase === "preview" ? [0, 10] : phase === "production" ? [10, 20] : [20, 24];
  for (let slot = slots[0]; slot < slots[1]; slot++) {
    let reservation;
    try { reservation = await open(path.join(directory, `slot-${slot}.json`), "wx"); }
    catch (error) { if (error.code === "EEXIST") continue; throw error; }
    try { await reservation.writeFile(JSON.stringify({ ...receipt, slot })); await reservation.sync(); }
    finally { await reservation.close(); }
    return { ...receipt, slot, receipt_path: identity };
  }
  await writeFile(identity, JSON.stringify({ ...receipt, state: "blocked_limit" }, null, 2));
  throw Error("Submission ceiling reached");
}

export async function assertReservedDispatch(receipt, { origin, commit, bankBytes, actualHistory, expectedHistory }) {
  const stored = JSON.parse(await readFile(receipt.receipt_path, "utf8"));
  if (stored.state !== "reserved" || stored.origin !== origin || stored.commit !== commit || stored.bank_sha256 !== createHash("sha256").update(bankBytes).digest("hex")) throw Error("Reservation identity mismatch or duplicate dispatch");
  if (JSON.stringify(actualHistory) !== JSON.stringify(expectedHistory)) throw Error("Browser history differs from the observed conversation");
  const claim = await open(`${receipt.receipt_path}.dispatch`, "wx");
  await claim.sync(); await claim.close();
  // Persist uncertainty before billable dispatch. An interrupted request is never retried.
  const file = await open(receipt.receipt_path, "r+");
  try { await file.truncate(0); await file.writeFile(JSON.stringify({ ...stored, state: "dispatch_started" }, null, 2)); await file.sync(); }
  finally { await file.close(); }
}
