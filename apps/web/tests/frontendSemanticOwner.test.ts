import { describe, expect, it } from "vitest";
import app from "../src/app/App.tsx?raw";
import workspace from "../src/app/workspacePresentation.ts?raw";
import answerBody from "../src/features/ask/AnswerBody.tsx?raw";

describe("frontend semantic owner", () => {
  it("does not reintroduce a free-text analytical intent regex", () => {
    expect(app).not.toMatch(/ANALYTICAL_QUERY/);
    expect(app + workspace).not.toMatch(/distribution\|distributed\|by\\s\+\(\?:status/);
    expect(workspace).not.toMatch(/\\b\(\?:map\|mapped\|where\|location/);
  });

  it("does not read a non-existent publication.source_title", () => {
    expect(answerBody).not.toMatch(/publication\?\.source_title/);
  });
});
