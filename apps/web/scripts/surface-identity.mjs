/** Read-only campaign guard: a browser run must observe one source and asset build. */
import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createServer } from "node:net";

const digest = value => createHash("sha256").update(value).digest("hex");
async function fileInventory(root, relative = "") {
  const files = {};
  for (const entry of await readdir(path.join(root, relative), { withFileTypes: true })) {
    const name = path.posix.join(relative, entry.name);
    if (entry.isDirectory()) Object.assign(files, await fileInventory(root, name));
    else if (entry.isFile()) files[name] = digest(await readFile(path.join(root, name)));
  }
  return Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b)));
}
export async function captureSurfaceIdentity(repositoryRoot, clientRoot) {
  const git = (...args) => execFileSync("git", args, { cwd: repositoryRoot, encoding: "utf8" }).trim();
  const untracked = {};
  for (const name of git("ls-files", "--others", "--exclude-standard").split("\n").filter(Boolean)) {
    untracked[name] = digest(await readFile(path.join(repositoryRoot, name)));
  }
  return {
    commit: git("rev-parse", "HEAD"),
    tree: git("rev-parse", "HEAD^{tree}"),
    status: git("status", "--porcelain", "--untracked-files=all"),
    tracked_diff_sha256: digest(git("diff", "--binary", "HEAD")),
    untracked,
    assets: await fileInventory(clientRoot),
  };
}
export function assertSurfaceIdentityUnchanged(before, after) {
  if (JSON.stringify(before) !== JSON.stringify(after)) {
    throw new Error("Frontend surface candidate or built assets changed during qualification");
  }
  return true;
}

/** Never attach qualification to an unrelated preview already using the port. */
export async function assertPreviewPortAvailable(baseUrl) {
  const url = new URL(baseUrl);
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", error => reject(new Error(`Frontend surface preview port is unavailable at ${baseUrl}: ${error.code}`)));
    probe.listen({ host: url.hostname, port: Number(url.port || 80), exclusive: true }, () => probe.close(error => error ? reject(error) : resolve()));
  });
}
