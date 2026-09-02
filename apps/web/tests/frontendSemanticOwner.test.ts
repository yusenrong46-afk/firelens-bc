import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "../src");

describe("frontend semantic owner", () => {
  it("does not reintroduce a free-text analytical intent regex", () => {
    const app = readFileSync(resolve(SRC, "app/App.tsx"), "utf8");
    const workspace = readFileSync(resolve(SRC, "app/workspacePresentation.ts"), "utf8");
    expect(app).not.toMatch(/ANALYTICAL_QUERY/);
    expect(app + workspace).not.toMatch(/distribution\|distributed\|by\\s\+\(\?:status/);
    expect(workspace).not.toMatch(/\\b\(\?:map\|mapped\|where\|location/);
  });
});
