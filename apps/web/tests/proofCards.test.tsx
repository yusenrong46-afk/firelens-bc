import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { App } from "../src/app/App";
import { getStatusBanner } from "../src/features/ask/proofPresentation";
import { TileFailureWarning } from "../src/features/near-me/OfficialBasemap";
import { MatchingRecordList } from "../src/features/near-me/LiveRecordLists";
import type { AskResponse, LiveResult } from "../src/shared/api/api";

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
    expect(screen.getAllByText("Supported by an exact reviewed quotation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Human-verified source transcription").length).toBeGreaterThan(0);
    expect(screen.getByText("Critical fields checked and preserved")).toBeInTheDocument();
    expect(screen.getAllByText("Food & water").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open official source" })[0]).toHaveAttribute(
      "href",
      "https://example.test/guide.pdf",
    );
  });

  it("projects quote-only publication wording over an older strengthening banner", async () => {
    const quoteOnly = {
      ...grounded,
      status_banner: {
        headline: "Grounded in reviewed official sources",
        detail: "All content is a reviewed FireLens claim.",
        freshness_label: "Stable reviewed guidance",
        availability_label: "Sources required for this request were available.",
      },
      claims: grounded.claims.map((claim) => ({
        ...claim,
        publication: {
          kind: "official_quote_only",
          review_status: "extraction_only",
          renderer_id: "firelens.quote_only_renderer.v1",
          support_provenance: "exact_official_quote",
        },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        support_state: "structured_reviewed",
        support_label: "Reviewed structured claim",
        review_state: "Approved static corpus",
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(quoteOnly), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What does the source say?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Official wording from a source")).toBeInTheDocument();
    expect(screen.getByText(
      "FireLens is showing an exact source quotation. It has not been approved as a structured FireLens claim.",
    )).toBeInTheDocument();
    expect(screen.getAllByText("Exact source wording — not a structured FireLens claim").length).toBeGreaterThan(0);
    expect(screen.getByText("Source extraction only; no structured-claim review")).toBeInTheDocument();
    expect(screen.getAllByText("Stable source wording").length).toBeGreaterThan(0);
    expect(screen.getByText("Answer evidence and support")).toBeInTheDocument();
    expect(screen.queryByText("Reviewed structured claim")).not.toBeInTheDocument();
  });

  it("downgrades rejected validation to unknown even when older proof fields strengthen it", async () => {
    const rejected = {
      ...grounded,
      validation: { ...grounded.validation, accepted: false, errors: ["rejected"] },
      claims: grounded.claims.map((claim) => ({
        ...claim,
        publication: {
          kind: "structured_reviewed",
          typed_claim_id: "TC-1",
          review_status: "approved",
          source_revision_sha256: "a".repeat(64),
          renderer_id: "firelens.structured_renderer.v1",
          support_provenance: "typed_inventory",
        },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        support_state: "structured_reviewed",
        support_label: "Reviewed structured claim",
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(rejected), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Can this be trusted?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Support not established")).toBeInTheDocument();
    expect(screen.getAllByText("Not established from FireLens sources").length).toBeGreaterThan(0);
    expect(screen.queryByText("Reviewed structured claim")).not.toBeInTheDocument();
  });

  it("uses the frozen mixed wording for reviewed and quote-only claims", () => {
    const response = {
      ...grounded,
      claims: [
        {
          ...grounded.claims[0],
          publication: {
            kind: "structured_reviewed",
            typed_claim_id: "TC-1",
            review_status: "approved",
            source_revision_sha256: "a".repeat(64),
            renderer_id: "firelens.structured_renderer.v1",
            support_provenance: "typed_inventory",
          },
        },
        {
          ...grounded.claims[0],
          claim_id: "C2",
          publication: {
            kind: "official_quote_only",
            review_status: "extraction_only",
            renderer_id: "firelens.quote_only_renderer.v1",
            support_provenance: "exact_official_quote",
          },
        },
      ],
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toMatchObject({
      headline: "Reviewed claims plus source wording",
      detail: "Reviewed structured claims and extraction-only source wording are labelled separately.",
      freshness_label: "Stable guidance and source wording",
    });
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
