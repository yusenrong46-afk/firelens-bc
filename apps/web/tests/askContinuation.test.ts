import { describe, expect, it } from "vitest";
import {
  looksLikeCommunityLabel,
  selectedResultIdForQuestion,
} from "../src/features/ask/askContinuation";

describe("selectedResultIdForQuestion", () => {
  it("sends an explicit override", () => {
    expect(selectedResultIdForQuestion("What is a firebreak?", undefined, "incident:7")).toBe(
      "incident:7",
    );
  });

  it("sends a stored id only for a selected-record follow-up", () => {
    expect(selectedResultIdForQuestion("How far is this fire from Kelowna?", "incident:7")).toBe(
      "incident:7",
    );
    expect(selectedResultIdForQuestion("What is a firebreak?", "incident:7")).toBeUndefined();
  });

  it("keeps the id for short elliptical attribute follow-ups", () => {
    expect(selectedResultIdForQuestion("status?", "incident:7")).toBe("incident:7");
    expect(selectedResultIdForQuestion("how large?", "incident:7")).toBe("incident:7");
    expect(selectedResultIdForQuestion("What is the source?", "incident:7")).toBe("incident:7");
    expect(selectedResultIdForQuestion("what's its size", "incident:7")).toBe("incident:7");
    expect(
      selectedResultIdForQuestion("Give me the answer first, then the evidence.", "incident:7"),
    ).toBe("incident:7");
  });

  it("does not hijack broad-subject questions with a stale selection", () => {
    expect(
      selectedResultIdForQuestion(
        "What's the status of fires across the province?",
        "incident:7",
      ),
    ).toBeUndefined();
    expect(
      selectedResultIdForQuestion("How many wildfires are burning in BC?", "incident:7"),
    ).toBeUndefined();
    expect(
      selectedResultIdForQuestion("Show evacuation orders near Kelowna", "incident:7"),
    ).toBeUndefined();
    expect(
      selectedResultIdForQuestion("What size fires count as large in BC?", "incident:7"),
    ).toBeUndefined();
  });
});

describe("looksLikeCommunityLabel", () => {
  it("accepts a short community name", () => {
    expect(looksLikeCommunityLabel("Kelowna")).toBe(true);
    expect(looksLikeCommunityLabel("Prince George")).toBe(true);
  });

  it("rejects a new question typed during a location prompt", () => {
    expect(looksLikeCommunityLabel("What belongs in a grab-and-go bag?")).toBe(false);
    expect(looksLikeCommunityLabel("How close is the wildfire perimeter near me today?")).toBe(
      false,
    );
  });
});
