import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { App } from "../src/app/App";
import { TileFailureWarning } from "../src/features/near-me/OfficialBasemap";
import { MatchingRecordList } from "../src/features/near-me/LiveRecordLists";
import type { LiveResult } from "../src/shared/api/api";

const grounded = {
  status: "answer",
  response_mode: "grounded",
  trace_id: "trace-proof",
  answer: "Keep water and food in a grab-and-go bag.",
  claims: [
    {
      claim_id: "C1",
      text: "Keep water and food in a grab-and-go bag.",
      evidence_status: "verified_corpus",
      supports: [{ evidence_id: "E1", quote: "Food & water" }],
      trust: {
        source_provenance: "approved_static_corpus",
        source_authority: "PreparedBC",
        jurisdiction: "british_columbia",
        human_review_state: "human_verified_repair",
        extraction_repair_state: "human_verified_repair",
        critical_field_preservation: "preserved",
        semantic_support_state: "exact_quote",
        conflict_or_supersession: "none",
        freshness: "stable_guidance",
      },
    },
  ],
  evidence: [
    {
      evidence_id: "E1",
      title: "Wildfire Preparedness Guide",
      publisher: "PreparedBC",
      canonical_url: "https://example.test/guide.pdf",
      locator: "PDF page 5",
      temporal_class: "stable_guidance",
      review_provenance: "human_verified_repair",
      primary_text: "Grab-and-Go Bag: Food & water",
      context_text: "Grab-and-Go Bag: Food & water and emergency supplies.",
    },
  ],
  limitations: ["Stable guidance only."],
  supported_items: ["Keep water and food in a grab-and-go bag."],
  unknown_items: ["Stable guidance only."],
  proof_cards: [
    {
      claim_id: "C1",
      claim_text: "Keep water and food in a grab-and-go bag.",
      support_state: "source_linked_explanation",
      support_label: "Source-linked explanation",
      authority: "PreparedBC",
      exact_passage: "Food & water",
      source_title: "Wildfire Preparedness Guide",
      source_revision: "PDF page 5",
      review_state: "Human-verified source transcription",
      critical_fields_checked: "Critical fields checked and preserved",
      freshness: "Stable reviewed guidance",
      official_url: "https://example.test/guide.pdf",
    },
  ],
  validation: {
    accepted: true,
    schema_valid: true,
    citation_ids_valid: true,
    quotes_exact: true,
    policy_valid: true,
    errors: [],
  },
};

const record: LiveResult = {
  result_id: "incident:7",
  kind: "incident",
  authority: "BC Wildfire Service",
  source_url: "https://example.test/incidents/7",
  source_updated_at: "2026-08-13T19:00:00Z",
  retrieved_at: "2026-08-13T19:05:00Z",
  freshness: "fresh",
  status: "Out of Control",
  name: "Listed Fire",
  geometry_relation: "nearby",
  geometry: { type: "Point", coordinates: [-119.5, 49.89] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("proof-carrying answer surface", () => {
  it("shows a status banner, known/unknown checklist, and a proof card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(grounded), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What belongs in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByRole("status", { name: "Answer status" })).toHaveTextContent(
      "Grounded in reviewed official sources",
    );
    expect(screen.getByText(/exact supporting quotations/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Established from FireLens sources" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Not established" })).toBeInTheDocument();
    expect(screen.getAllByText("Stable guidance only.").length).toBeGreaterThan(0);
    expect(screen.getByText("Source-linked explanation")).toBeInTheDocument();
    expect(screen.getAllByText("Human-verified source transcription").length).toBeGreaterThan(0);
    expect(screen.getByText("Critical fields checked and preserved")).toBeInTheDocument();
    expect(screen.getAllByText("Food & water").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open official source" })[0]).toHaveAttribute(
      "href",
      "https://example.test/guide.pdf",
    );
  });

  it("keeps official records listed when map tiles fail", () => {
    const { rerender } = render(
      <>
        <TileFailureWarning failed={false} />
        <MatchingRecordList results={[record]} />
      </>,
    );
    expect(screen.queryByText(/Map tiles failed to load/)).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Matching this question" })).toHaveTextContent("Listed Fire");
    rerender(
      <>
        <TileFailureWarning failed />
        <MatchingRecordList results={[record]} />
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Official records remain listed below");
    expect(screen.getByRole("list", { name: "Matching this question" })).toHaveTextContent("Listed Fire");
  });
});
