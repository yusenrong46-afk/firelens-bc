import assert from "node:assert/strict";
import test from "node:test";
import { assertSurfaceIdentityUnchanged } from "../scripts/surface-identity.mjs";
const identity = { commit: "one", tree: "tree", status: "", tracked_diff_sha256: "clean", untracked: {}, assets: { "index.html": "index", "assets/map.js": "map" } };
test("surface guard accepts the same candidate and every asset", () => {
  assert.equal(assertSurfaceIdentityUnchanged(identity, structuredClone(identity)), true);
});
for (const field of ["commit", "tree", "status", "tracked_diff_sha256", "untracked", "assets"]) {
  test(`surface guard rejects a changed ${field} even when index and manifest are unchanged`, () => {
    const changed = { ...structuredClone(identity), [field]: "changed" };
    assert.throws(() => assertSurfaceIdentityUnchanged(identity, changed), /changed during qualification/);
  });
}

test("asset inventory detects a lazy chunk mutation while index remains byte-identical", async () => {
  const { mkdtemp, mkdir, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { execFileSync } = await import("node:child_process");
  const { captureSurfaceIdentity } = await import("../scripts/surface-identity.mjs");
  const root = await mkdtemp(join(tmpdir(), "firelens-identity-control-"));
  try {
    const git = (...args) => execFileSync("git", args, { cwd: root, stdio: "pipe" });
    git("init", "--quiet");
    await writeFile(join(root, ".gitignore"), "dist/\n");
    git("add", ".gitignore");
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "--quiet", "-m", "fixture");
    await mkdir(join(root, "dist/assets"), { recursive: true });
    await writeFile(join(root, "dist/index.html"), "same index");
    await writeFile(join(root, "dist/assets/map.js"), "first lazy chunk");
    const before = await captureSurfaceIdentity(root, join(root, "dist"));
    await writeFile(join(root, "dist/assets/map.js"), "changed lazy chunk");
    const after = await captureSurfaceIdentity(root, join(root, "dist"));
    assert.equal(before.status, after.status);
    assert.equal(before.assets["index.html"], after.assets["index.html"]);
    assert.throws(() => assertSurfaceIdentityUnchanged(before, after), /changed during qualification/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("an occupied preview port is rejected instead of qualifying an existing server", async () => {
  const { createServer } = await import("node:net");
  const { assertPreviewPortAvailable } = await import("../scripts/surface-identity.mjs");
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  try { await assert.rejects(assertPreviewPortAvailable(url), /port is unavailable.*EADDRINUSE/); }
  finally { await new Promise(resolve => server.close(resolve)); }
  await assertPreviewPortAvailable(url);
});
