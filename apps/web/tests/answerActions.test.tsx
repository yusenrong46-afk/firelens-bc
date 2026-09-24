import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnswerActions } from "../src/features/ask/AnswerActions";
import { explainAnswer, formatAnswerForCopy } from "../src/features/ask/answerActionPresentation";
import { ResponseModeBadge } from "../src/features/ask/responseModeBadge";
import type { AskResponse, LiveResult } from "../src/shared/api/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function guidance(overrides: Partial<AskResponse> = {}): AskResponse {
  return {
    status: "answer",
    response_mode: "grounded",
    presentation_shell: "chat",
    provenance_class: "reviewed_guidance",
    trace_id: "private-trace-123",
    answer: "Keep food and water in your kit.",
    claims: [{
      claim_id: "C1",
      text: "Keep food and water in your kit.",
      evidence_status: "verified_corpus",
      supports: [{ evidence_id: "E1", quote: "Food and water" }],
      publication: {
        kind: "source_linked_explanation",
        review_status: "source_linked",
        renderer_id: "firelens.explanation_renderer.v1",
        support_provenance: "validated_grounded_explanation",
      },
    }],
    evidence: [{
      evidence_id: "E1",
      publisher: "PreparedBC",
      title: "Wildfire Preparedness Guide",
      canonical_url: "https://www2.gov.bc.ca/preparedbc/guide.pdf",
      locator: "PDF page 5",
      temporal_class: "stable_guidance",
      review_provenance: "native_text",
      primary_text: "Food and water",
      context_text: "A grab-and-go bag includes food and water.",
      document_sha256: "a".repeat(64),
    }],
    limitations: ["Coverage is limited to the cited guidance.", "Not a safety determination."],
    ...overrides,
  };
}

function liveRecord(): LiveResult {
  return {
    result_id: "incident:1",
    authority: "BC Wildfire Service",
    kind: "incident",
    name: "Test Fire",
    fire_of_note: false,
    freshness: "stale",
    geometry: { type: "Point", coordinates: [-119.496, 49.887] },
    geometry_relation: "unknown",
    retrieved_at: "2026-09-15T18:00:00Z",
    source_updated_at: "2026-09-14T17:00:00Z",
    source_url: "https://wildfiresituation.nrs.gov.bc.ca/map",
    status: "Out of Control",
  };
}

describe("answer action public metadata", () => {
  it("retains authority and safety limitations even when compact presentation groups them as notes", () => {
    const limitations = [
      "This uses official records and is not a safety assessment.",
      "General background is not verified against the FireLens corpus.",
      "Static corpus cannot establish current status.",
    ];
    const response = guidance({ limitations });
    expect(explainAnswer(response).limitations).toEqual(limitations);
    const copied = formatAnswerForCopy(response, response.answer!);
    for (const limitation of limitations) expect(copied).toContain(limitation);
  });
  it.each(["grounded", "partial"] as const)("keeps a %s quote-only answer distinct from reviewed guidance", (mode) => {
    const response = guidance({ response_mode: mode });
    response.claims = response.claims!.map((claim) => ({ ...claim,
      publication: { ...claim.publication!, kind: "official_quote_only" },
    }));
    render(<ResponseModeBadge mode={mode} response={response} />);
    expect(screen.getByText("Exact wording from an official source")).toBeVisible();
    expect(screen.queryByText(/reviewed guidance/)).not.toBeInTheDocument();
  });

  it("uses a public generic label for an unnamed record without copying its internal ID", () => {
    const record = { ...liveRecord(), name: null, incident_number: null, result_id: "private:record:123" };
    const response = guidance({ response_mode: "live", provenance_class: "official_live", claims: [], evidence: [], live_results: [record] });
    const copied = formatAnswerForCopy(response, "One record was returned.");
    expect(copied).toContain("Official incident record");
    expect(copied).not.toContain(record.result_id);
    expect(JSON.stringify(explainAnswer(response).sources)).not.toContain(record.result_id);
  });

  it("copies displayed answer, material limits and linked sources without request or location metadata", () => {
    const response = {
      ...guidance({ resolved_location: { latitude: 49.887, longitude: -119.496 } }),
      question: "Private question from my address",
      history: [{ role: "user", content: "Private previous conversation" }],
    };
    const copied = formatAnswerForCopy(response, "Displayed answer near Kelowna.");
    expect(copied).toContain("Displayed answer near Kelowna.");
    expect(copied).toContain("Coverage is limited to the cited guidance.");
    expect(copied).toContain("PreparedBC — Wildfire Preparedness Guide");
    expect(copied).toContain("https://www2.gov.bc.ca/preparedbc/guide.pdf");
    expect(copied).toContain("Source-linked explanation");
    for (const excluded of ["Private question", "Private previous", "49.887", "-119.496", "private-trace-123", "a".repeat(64)]) {
      expect(copied).not.toContain(excluded);
    }
    expect(copied).not.toContain("Keep food and water in your kit.");
  });

  it("preserves mixed answer sections and their distinct authorities", () => {
    const response = guidance({ response_mode: "mixed", provenance_class: "mixed", answer_sections: [
      { kind: "current_records", heading: "Official records", text: "One incident record was returned." },
      { kind: "general_background", heading: "Background", text: "This explanation is not checked against official sources." },
    ] });
    const copied = formatAnswerForCopy(response, "Unused combined prose");
    expect(copied).toContain("Official current records\nOfficial records\nOne incident record was returned.");
    expect(copied).toContain("General background\nBackground\nThis explanation is not checked against official sources.");
    expect(copied).not.toContain("Unused combined prose");
  });

  it("copies exact quote-only claim text, including the expanded wording, instead of mismatched answer prose", () => {
    const response = guidance();
    const firstClaim = response.claims![0]!;
    const quotes = ["Call 9-1-1 in an emergency.", "Follow instructions from local authorities.", "Keep your emergency contacts with you."];
    response.claims = quotes.map((text, index) => ({
      ...firstClaim, claim_id: `quote-${index}`, text,
      publication: { ...firstClaim.publication!, kind: "official_quote_only" },
    }));
    response.answer = "Different generated prose that the quote-only view does not show.";
    const copied = formatAnswerForCopy(response, response.answer);
    for (const quote of quotes) expect(copied).toContain(quote);
    expect(copied).not.toContain(response.answer);
  });

  it("retains separate document revisions with the same publisher, title and URL in Why sources", async () => {
    const user = userEvent.setup();
    const response = guidance();
    response.evidence!.push({ ...response.evidence![0]!, evidence_id: "E2", document_sha256: "b".repeat(64) });
    response.claims![0]!.supports!.push({ evidence_id: "E2", quote: "Food and water" });
    const explanation = explainAnswer(response);
    expect(explanation.sources).toHaveLength(2);
    expect(explanation.sources.map((source) => source.revision)).toEqual(["a".repeat(64), "b".repeat(64)]);
    render(<AnswerActions response={response} displayedText="Answer" />);
    await user.click(screen.getByRole("button", { name: "Why this answer?" }));
    expect(screen.getAllByRole("link", { name: /Wildfire Preparedness Guide/ })).toHaveLength(2);
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
  });

  it("retains stale, partial and unavailable distinctions and supplied source timestamps", () => {
    const response = guidance({
      response_mode: "live", provenance_class: "official_live", claims: [], evidence: [],
      live_results: [liveRecord()], requested_layers: ["incident", "evacuation"],
      partial_layers: ["incident"], unavailable_layers: ["evacuation"],
      aggregate_freshness: "stale", roster_total: 3,
    });
    const copied = formatAnswerForCopy(response, "A cached record was returned.");
    expect(copied).toContain("Cached official records");
    expect(copied).toContain("Partial coverage: fires. Missing records are not an all-clear.");
    expect(copied).toContain("Unavailable records: evacuations. These layers cannot be counted as empty.");
    expect(copied).toContain("1 returned official record; 3 records in the reported matching roster.");
    expect(copied).toContain("Checked by FireLens: 2026-09-15T18:00:00Z");
    expect(copied).toContain("Source updated: 2026-09-14T17:00:00Z");
    expect(copied).not.toContain("49.887");
  });

  it("never invents timestamps or marks absent checks as passed", () => {
    const explanation = explainAnswer(guidance());
    expect(explanation.checks).toBeNull();
    expect(explanation.checkedAt).toBeUndefined();
    expect(explanation.updatedAt).toBeUndefined();
    const partialReport = guidance({ validation: {
      accepted: true, citation_ids_valid: true, quotes_exact: true,
      policy_valid: true, schema_valid: true,
    } as NonNullable<AskResponse["validation"]> });
    expect(explainAnswer(partialReport).checks).toContainEqual({ label: "Claim support", result: "Not supplied" });
  });

  it("does not elevate source-linked or rejected support with a mismatched raw proof card", () => {
    const response = guidance({ proof_cards: [{
      claim_id: "C1", claim_text: "Fabricated claim", support_state: "structured_reviewed",
      support_label: "Independently reviewed and approved", authority: "Invented publisher",
      critical_fields_checked: "All checks passed", review_state: "Approved",
      freshness: "fresh", publication_state: "verified", truth_class: "source_fact",
      official_url: "https://example.test/invented",
    }] });
    const explanation = explainAnswer(response);
    expect(explanation.supportLabels).toEqual(["Explanation linked to a source"]);
    expect(JSON.stringify(explanation)).not.toContain("Invented publisher");
    expect(JSON.stringify(explanation)).not.toContain("Independently reviewed");
    const rejected = explainAnswer(guidance({ validation: {
      accepted: false, citation_ids_valid: false, quotes_exact: false,
      policy_valid: false, schema_valid: true, claim_support_valid: false,
    } }));
    expect(rejected.sources).toEqual([]);
    expect(rejected.answerTypes).toEqual(["Not confirmed by FireLens sources"]);
    expect(rejected.checks).toContainEqual({ label: "Response acceptance", result: "Failed" });
  });

  it("does not expose attached source claims as support for general background", () => {
    const explanation = explainAnswer(guidance({ response_mode: "background", provenance_class: "general_knowledge" }));
    expect(explanation.sources).toEqual([]);
    expect(explanation.supportLabels).toEqual([]);
    expect(explanation.canInspectEvidence).toBe(false);
    expect(explanation.answerTypes).toEqual(["General knowledge — not checked against FireLens sources"]);
  });
});

describe("AnswerActions", () => {
  it("copies on click without making a request", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<AnswerActions response={guidance()} displayedText="Answer for Kelowna." />);
    expect(writeText).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith(expect.stringContaining("Answer for Kelowna."));
    expect(screen.getByRole("status")).toHaveTextContent("Answer, limits and sources copied.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("provides selected manual-copy text when clipboard access fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("Permission denied"));
    render(<AnswerActions response={guidance()} displayedText="Answer for manual copy." />);
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    const textarea = await screen.findByRole("textbox", { name: "Copy this answer manually" });
    expect(textarea).toHaveFocus();
    expect(textarea).toHaveAttribute("readonly");
    const field = textarea as HTMLTextAreaElement;
    expect(field.selectionStart).toBe(0);
    expect(field.selectionEnd).toBe(field.value.length);
    await user.click(screen.getByRole("button", { name: "Select answer text" }));
    expect(textarea).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("Automatic copy is unavailable");
  });

  it("offers manual copying when the browser has no clipboard API", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("navigator", { clipboard: undefined });
    render(<AnswerActions response={guidance()} displayedText="Answer without clipboard support." />);
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    const field = await screen.findByRole("textbox", { name: "Copy this answer manually" }) as HTMLTextAreaElement;
    expect(field.value).toContain("Answer without clipboard support.");
  });

  it("explains missing validation honestly and restores focus when closed with Escape", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    render(<AnswerActions response={guidance()} displayedText="Answer" onOpenEvidence={inspect} />);
    const trigger = screen.getByRole("button", { name: "Why this answer?" });
    await user.click(trigger);
    const explanation = screen.getByRole("region", { name: "Why this answer" });
    expect(within(explanation).getByText("Check details were not supplied with this response.")).toBeInTheDocument();
    expect(explanation).toHaveTextContent("Coverage metadata was not supplied.");
    expect(explanation).toHaveTextContent("Location and distance metadata were not supplied.");
    expect(explanation).toHaveTextContent("Response checked: Not supplied");
    expect(within(explanation).queryByText("Passed", { exact: true })).not.toBeInTheDocument();
    expect(explanation).not.toHaveTextContent(/queried|query plan|execution trace/i);
    const inspectButton = within(explanation).getByRole("button", { name: "Inspect evidence" });
    await user.click(inspectButton);
    expect(inspect).toHaveBeenCalledOnce();
    fireEvent.keyDown(inspectButton, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Why this answer" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("does not mark a new response copied after an earlier clipboard promise finishes", async () => {
    const user = userEvent.setup();
    let finishCopy: (() => void) | undefined;
    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(() => new Promise<void>((resolve) => { finishCopy = resolve; }));
    const { rerender } = render(<AnswerActions response={guidance()} displayedText="First answer" />);
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    rerender(<AnswerActions response={guidance({ trace_id: "next-trace" })} displayedText="Next answer" />);
    finishCopy?.();
    expect(await screen.findByRole("button", { name: "Copy answer" })).toBeEnabled();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});
