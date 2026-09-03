import { describe, expect, it } from "vitest";
import {
  looksLikeCommunityLabel,
  selectedResultIdForQuestion,
} from "../src/features/ask/askContinuation";

describe("selectedResultIdForQuestion", () => {
  const liveResults = [
    { result_id: "incident:first" },
    { result_id: "incident:second" },
    { result_id: "incident:third" },
  ];

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

  it("leaves positions in the list to the server, which reads the roster it is sent", () => {
    expect(selectedResultIdForQuestion("Tell me more about the second one.", undefined, undefined, liveResults)).toBeUndefined();
    expect(selectedResultIdForQuestion("Tell me more about number 3.", undefined, undefined, liveResults)).toBeUndefined();
    expect(selectedResultIdForQuestion("Tell me more about the fourth one.", undefined, undefined, liveResults)).toBeUndefined();
  });

  it("binds an exact visible incident name and prefers its incident over a perimeter", () => {
    const results = [
      { result_id: "perimeter:bald", kind: "perimeter", name: "Bald Range", incident_number: null },
      { result_id: "incident:bald", kind: "incident", name: "Bald Range", incident_number: "K12345" },
    ];
    expect(selectedResultIdForQuestion("Where is Bald Range?", undefined, undefined, results)).toBe(
      "incident:bald",
    );
    expect(selectedResultIdForQuestion("Where's Bald Range?", undefined, undefined, results)).toBe(
      "incident:bald",
    );
    expect(selectedResultIdForQuestion("Where’s Bald Range?", undefined, undefined, results)).toBe(
      "incident:bald",
    );
    expect(selectedResultIdForQuestion("Where is K12345?", undefined, undefined, results)).toBe(
      "incident:bald",
    );
  });

  it("fails closed for fuzzy, substring, and ambiguous visible identities", () => {
    const results = [
      { result_id: "incident:bald", kind: "incident", name: "Bald Range", incident_number: null },
      { result_id: "incident:bald-2", kind: "incident", name: "Bald Range", incident_number: null },
    ];
    expect(selectedResultIdForQuestion("Where is Bald?", undefined, undefined, results)).toBeUndefined();
    expect(selectedResultIdForQuestion("Where is Bald Range Fire?", undefined, undefined, results)).toBeUndefined();
    expect(selectedResultIdForQuestion("Where are fires across B.C.?", "incident:bald", undefined, results)).toBeUndefined();
    expect(selectedResultIdForQuestion("Where is Bald Range?", undefined, undefined, results)).toBeUndefined();
  });

  it("fails closed for ambiguous singular questions without a selection", () => {
    expect(selectedResultIdForQuestion("How large is it?", undefined, undefined, liveResults)).toBeUndefined();
  });

  it("retains the server-selected id for a later deictic follow-up", () => {
    expect(selectedResultIdForQuestion("How far is that one from Kamloops?", "incident:second", undefined, liveResults)).toBe("incident:second");
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
