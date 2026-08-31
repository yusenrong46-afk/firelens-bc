import { describe, expect, it } from "vitest";
import { announcementForState } from "../src/features/ask/conversationAnnouncements";

describe("conversation accessibility announcements", () => {
  it("keeps loading, completion, failure, and recovery announcements atomic", () => {
    expect(announcementForState("loading", "idle")).toBe("FireLens is working on your question.");
    expect(announcementForState("answer", "loading")).toBe("FireLens response ready.");
    expect(announcementForState("unavailable", "loading")).toBe("FireLens is temporarily unavailable.");
    expect(announcementForState("error", "loading")).toMatch(/could not complete/i);
    expect(announcementForState("answer", "error")).toMatch(/recovered/i);
  });
});
