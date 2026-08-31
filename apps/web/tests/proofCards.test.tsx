import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { App } from "../src/app/App";
import { getProofCards, getClaimSupportState, getStatusBanner, bindProofProfile, bindDistanceDerivation, CANONICAL_DISTANCE_DERIVATION, freshnessToken } from "../src/features/ask/proofPresentation";
import { StatusBanner } from "../src/features/ask/StatusBanner";
import { ResponseModeBadge } from "../src/features/ask/responseModeBadge";
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
      publication: {
        kind: "source_linked_explanation",
        review_status: "none",
        renderer_id: "firelens.grounded_generator.v1",
        support_provenance: "validated_generated_explanation",
        risk_tier: "C",
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
      truth_class: "model_summary",
      publication_state: "review",
      publication: {
        kind: "source_linked_explanation",
        review_status: "none",
        renderer_id: "firelens.grounded_generator.v1",
        support_provenance: "validated_generated_explanation",
        risk_tier: "C",
      },
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
  it("shows one status banner, one limitation, and the claim/source controls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(grounded), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What belongs in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByRole("status", { name: "Answer status" })).toHaveTextContent(
      "Source-linked explanation",
    );
    expect(screen.getByText(
      "This explanation links to source material but is not a reviewed structured FireLens claim.",
    )).toBeInTheDocument();
    expect(screen.queryByLabelText("What FireLens established")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Established from FireLens sources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Not established" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Stable guidance only.")).toHaveLength(1);
    const evidenceButton = screen.getByRole("button", { name: /Keep water and food in a grab-and-go bag\./ });
    expect(evidenceButton).toBeInTheDocument();
    await user.click(evidenceButton);
    expect(screen.getAllByText("Source-linked explanation").length).toBeGreaterThan(0);
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
    await user.click(screen.getByRole("button", { name: /Keep water and food in a grab-and-go bag\./ }));
    expect(screen.getAllByText("Source extraction only; no structured-claim review").length).toBeGreaterThan(0);
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
    await user.click(screen.getByRole("button", { name: /Keep water and food in a grab-and-go bag\./ }));
    const proofCard = screen.getByRole("article", {
      name: "Proof card for Keep water and food in a grab-and-go bag.",
    });
    expect(within(proofCard).getByText("Authority not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Review state not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Critical-field validation not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Freshness not established")).toBeInTheDocument();
    expect(within(proofCard).queryByText("Human-verified source transcription")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Critical fields checked and preserved")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Stable reviewed guidance")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Food & water")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Wildfire Preparedness Guide")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("PDF page 5")).not.toBeInTheDocument();
    expect(within(proofCard).queryByRole("link", { name: "Open official source" })).not.toBeInTheDocument();
    expect(screen.queryByText("Source passage")).not.toBeInTheDocument();
  });

  it("neutralizes proof metadata and claim evidence after a critical-field failure", async () => {
    const failedCritical = {
      ...grounded,
      claims: grounded.claims.map((claim) => ({
        ...claim,
        trust: { ...claim.trust, critical_field_preservation: "failed" },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        support_state: "structured_reviewed",
        support_label: "Reviewed structured claim",
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(failedCritical), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Did critical fields pass?");
    await user.click(screen.getByLabelText("Send question"));

    await user.click(await screen.findByRole("button", { name: /Keep water and food in a grab-and-go bag\./ }));

    const proofCard = await screen.findByRole("article", {
      name: "Proof card for Keep water and food in a grab-and-go bag.",
    });
    expect(within(proofCard).getByText("Not established from FireLens sources")).toBeInTheDocument();
    expect(within(proofCard).getByText("Authority not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Review state not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Critical-field validation not established")).toBeInTheDocument();
    expect(within(proofCard).getByText("Freshness not established")).toBeInTheDocument();
    expect(within(proofCard).queryByText("Human-verified source transcription")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Critical fields checked and preserved")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Stable reviewed guidance")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Food & water")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("Wildfire Preparedness Guide")).not.toBeInTheDocument();
    expect(within(proofCard).queryByText("PDF page 5")).not.toBeInTheDocument();
    expect(within(proofCard).queryByRole("link", { name: "Open official source" })).not.toBeInTheDocument();
    expect(screen.queryByText("Source passage")).not.toBeInTheDocument();
  });

  it("does not borrow a stale orphan card for a selected unknown claim", async () => {
    const orphaned = {
      ...grounded,
      claims: grounded.claims.map((claim) => ({
        ...claim,
        trust: { ...claim.trust, critical_field_preservation: "failed" },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        claim_id: "C2",
        claim_text: "Stale structured orphan",
        support_state: "structured_reviewed",
        support_label: "Reviewed structured claim",
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(orphaned), { status: 200 })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Can an orphan card be reused?");
    await user.click(screen.getByLabelText("Send question"));

    await user.click(await screen.findByRole("button", { name: /Keep water and food in a grab-and-go bag\./ }));
    expect(await screen.findByText("Content not established")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Proof card for Stale structured orphan" })).not.toBeInTheDocument();
    expect(screen.queryByText("Stale structured orphan")).not.toBeInTheDocument();
    expect(screen.queryByText("Human-verified source transcription")).not.toBeInTheDocument();
    expect(screen.queryByText("Critical fields checked and preserved")).not.toBeInTheDocument();
    expect(screen.queryByText("Stable reviewed guidance")).not.toBeInTheDocument();
    expect(screen.queryByText("Food & water")).not.toBeInTheDocument();
    expect(screen.queryByText("Wildfire Preparedness Guide")).not.toBeInTheDocument();
    expect(screen.queryByText("PDF page 5")).not.toBeInTheDocument();
    expect(screen.queryByText("Source passage")).not.toBeInTheDocument();
  });

  it("preserves a matching accepted live proof card", () => {
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-live-card",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [record],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Listed Fire",
        support_state: "live_record",
        support_label: "Official live record as published",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live feed as published",
        critical_fields_checked: "Not applicable — live record, not a reviewed claim",
        freshness: record.freshness,
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "verified",
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;

    expect(getProofCards(response)).toMatchObject([{
      claim_id: "incident:7",
      support_state: "live_record",
      authority: "BC Wildfire Service",
      exact_passage: "Out of Control",
      official_url: "https://example.test/incidents/7",
      truth_class: "source_fact",
      publication_state: "verified",
    }]);
  });

  it("does not keep API-elevated verified metadata on a model-summary card", () => {
    const response = {
      ...grounded,
      claims: grounded.claims.map((claim) => ({
        ...claim,
        publication: {
          kind: "source_linked_explanation",
          review_status: "extraction_only",
          renderer_id: "firelens.source_linked_renderer.v1",
          support_provenance: "source_linked",
        },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        support_state: "source_linked_explanation",
        truth_class: "source_fact",
        publication_state: "verified",
      })),
    } as unknown as AskResponse;

    expect(getProofCards(response)[0]).toMatchObject({
      support_state: "source_linked_explanation",
      truth_class: "model_summary",
      publication_state: "review",
    });
  });

  it("does not mark live records verified unless freshness is explicitly fresh", () => {
    expect(bindProofProfile("live_record")).toEqual({
      truth_class: "source_fact",
      publication_state: "review",
    });
    for (const freshness of [null, "Freshness not established", "banana", "stale", "", "stale.fresh", "Freshness.FRESH", "fresh.stale"]) {
      expect(bindProofProfile("live_record", { freshness })).toEqual({
        truth_class: "source_fact",
        publication_state: "review",
      });
      expect(bindProofProfile("official_live_typed", { freshness })).toEqual({
        truth_class: "source_fact",
        publication_state: "review",
      });
    }
    expect(freshnessToken("stale.fresh")).toBeNull();
    expect(freshnessToken("fresh")).toBe("fresh");
    expect(bindProofProfile("live_record", { freshness: "fresh" })).toEqual({
      truth_class: "source_fact",
      publication_state: "verified",
    });
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-unrecognized-freshness",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [{ ...record, freshness: "Freshness not established" }],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Listed Fire",
        support_state: "live_record",
        support_label: "Official live record as published",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live feed as published",
        critical_fields_checked: "Not applicable — live record, not a reviewed claim",
        freshness: "Freshness not established",
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "verified",
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;
    expect(getProofCards(response)[0]).toMatchObject({
      publication_state: "review",
      truth_class: "source_fact",
    });
  });

  it("binds distance derivation without rewriting unsupported units or CRS as supported", () => {
    const canonical = bindDistanceDerivation({
      truth_class: "source_fact",
      publication_state: "verified",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: CANONICAL_DISTANCE_DERIVATION.crs,
      coordinate_order: CANONICAL_DISTANCE_DERIVATION.coordinate_order,
      units: CANONICAL_DISTANCE_DERIVATION.units,
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      distance_km: 12.5,
      distance_basis: "incident_point",
    }, { freshness: "fresh" });
    expect(canonical).toMatchObject({
      truth_class: "deterministic_derivation",
      publication_state: "verified",
      units: "km",
      crs: "EPSG:4326",
      validation_status: "valid",
      input_freshness: "fresh",
    });
    if (canonical == null) {
      throw new Error("expected canonical derivation");
    }
    expect(bindDistanceDerivation({
      ...canonical,
      input_source_ids: ["incident:7"],
    }, { freshness: "fresh" })).toMatchObject({
      validation_status: "valid",
      publication_state: "review",
    });
    expect(bindDistanceDerivation(canonical, { freshness: "stale.fresh" })).toMatchObject({
      validation_status: "valid",
      publication_state: "review",
    });
    expect(bindDistanceDerivation({
      ...canonical,
      calculated_at: "2100-01-01T00:00:00+00:00",
    }, { freshness: "fresh" })).toMatchObject({
      validation_status: "invalid",
      publication_state: "rejected",
    });
    expect(bindDistanceDerivation(canonical, { freshness: "stale" })).toMatchObject({
      validation_status: "valid",
      publication_state: "review",
      input_freshness: "stale",
    });
    expect(bindDistanceDerivation(canonical, { freshness: "Freshness not established" })).toMatchObject({
      validation_status: "valid",
      publication_state: "review",
    });
    expect(bindDistanceDerivation({
      truth_class: "deterministic_derivation",
      publication_state: "verified",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: CANONICAL_DISTANCE_DERIVATION.crs,
      coordinate_order: CANONICAL_DISTANCE_DERIVATION.coordinate_order,
      units: CANONICAL_DISTANCE_DERIVATION.units,
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      distance_km: 12.5,
      distance_basis: "incident_point",
    })).toMatchObject({
      validation_status: "valid",
      publication_state: "review",
      input_freshness: "unknown",
    });
    const miles = bindDistanceDerivation({
      truth_class: "deterministic_derivation",
      publication_state: "verified",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: "EPSG:4326",
      coordinate_order: "longitude_latitude",
      units: "miles",
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      distance_km: 7.8,
      distance_basis: "incident_point",
    }, { freshness: "fresh" });
    expect(miles).toMatchObject({
      units: "miles",
      crs: "EPSG:4326",
      publication_state: "rejected",
      validation_status: "invalid",
      truth_class: "deterministic_derivation",
    });
    const projected = bindDistanceDerivation({
      truth_class: "deterministic_derivation",
      publication_state: "verified",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: "EPSG:3857",
      coordinate_order: "longitude_latitude",
      units: "km",
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      distance_km: 12.5,
      distance_basis: "incident_point",
    });
    expect(projected).toMatchObject({
      crs: "EPSG:3857",
      units: "km",
      publication_state: "rejected",
      validation_status: "invalid",
    });
  });

  it("does not keep a verified nested derivation when the live input is stale", () => {
    const elevated = {
      truth_class: "deterministic_derivation",
      publication_state: "verified",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: CANONICAL_DISTANCE_DERIVATION.crs,
      coordinate_order: CANONICAL_DISTANCE_DERIVATION.coordinate_order,
      units: CANONICAL_DISTANCE_DERIVATION.units,
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      input_freshness: "fresh",
      distance_km: 12.5,
      distance_basis: "incident_point",
    };
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-stale-derivation",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [{
        ...record,
        freshness: "stale",
        distance_km: 12.5,
        distance_basis: "incident_point",
        distance_derivation: elevated,
      }],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Distance 12.5 km geodesic to the official incident point.",
        support_state: "official_live_typed",
        support_label: "Official live record",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live record as published",
        critical_fields_checked: "Rendered from typed live fields",
        freshness: "stale",
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "review",
        derivation: elevated,
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;
    expect(getProofCards(response)[0]).toMatchObject({
      publication_state: "review",
      derivation: {
        validation_status: "valid",
        publication_state: "review",
        input_freshness: "stale",
      },
    });
    const fromLiveResults = {
      ...response,
      proof_cards: [],
    } as unknown as AskResponse;
    expect(getProofCards(fromLiveResults)[0]).toMatchObject({
      publication_state: "review",
      derivation: {
        validation_status: "valid",
        publication_state: "review",
        input_freshness: "stale",
      },
    });
  });

  it("does not keep distance-bearing wording that disagrees with the bound derivation", () => {
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-mismatched-distance-wording",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [record],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Distance 999.9 km geodesic to the official incident point.",
        support_state: "official_live_typed",
        support_label: "Official live record",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live record as published",
        critical_fields_checked: "Rendered from typed live fields",
        freshness: "fresh",
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "verified",
        derivation: {
          truth_class: "deterministic_derivation",
          publication_state: "verified",
          input_source_ids: ["incident:7", "place:49.90,-119.50"],
          algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
          crs: CANONICAL_DISTANCE_DERIVATION.crs,
          coordinate_order: CANONICAL_DISTANCE_DERIVATION.coordinate_order,
          units: CANONICAL_DISTANCE_DERIVATION.units,
          calculated_at: "2026-08-25T12:00:00+00:00",
          validation_status: "valid",
          input_freshness: "fresh",
          distance_km: 2.3,
          distance_basis: "incident_point",
        },
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;
    expect(getProofCards(response)[0]).toMatchObject({
      support_state: "unknown",
      publication_state: "rejected",
      derivation: null,
    });
  });

  it("rebinds a preserved live card to the current live result freshness", () => {
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-preserved-fresh-card",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [{ ...record, freshness: "stale", source_url: "https://example.test/incidents/stale" }],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Listed Fire",
        support_state: "live_record",
        support_label: "Official live record as published",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live feed as published",
        critical_fields_checked: "Not applicable — live record, not a reviewed claim",
        freshness: "fresh",
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "verified",
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;
    expect(getProofCards(response)[0]).toMatchObject({
      freshness: "stale",
      publication_state: "review",
      official_url: "https://example.test/incidents/stale",
    });
  });

  it("keeps a valid nested derivation verified only when the live input is fresh", () => {
    const bound = bindDistanceDerivation({
      truth_class: "deterministic_derivation",
      publication_state: "review",
      input_source_ids: ["incident:7", "place:49.90,-119.50"],
      algorithm: CANONICAL_DISTANCE_DERIVATION.algorithm,
      crs: CANONICAL_DISTANCE_DERIVATION.crs,
      coordinate_order: CANONICAL_DISTANCE_DERIVATION.coordinate_order,
      units: CANONICAL_DISTANCE_DERIVATION.units,
      calculated_at: "2026-08-25T12:00:00+00:00",
      validation_status: "valid",
      distance_km: 12.5,
      distance_basis: "incident_point",
    }, { freshness: "fresh" });
    expect(bound).toMatchObject({
      publication_state: "verified",
      input_freshness: "fresh",
    });
    const response = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-fresh-derivation",
      answer: "Listed Fire is Out of Control.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [record],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Distance 12.5 km geodesic to the official incident point.",
        support_state: "official_live_typed",
        support_label: "Official live record",
        authority: record.authority,
        exact_passage: record.status,
        source_title: "Listed Fire",
        source_revision: record.source_updated_at,
        review_state: "Official live record as published",
        critical_fields_checked: "Rendered from typed live fields",
        freshness: "fresh",
        official_url: record.source_url,
        truth_class: "source_fact",
        publication_state: "verified",
        derivation: bound,
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;
    expect(getProofCards(response)[0]).toMatchObject({
      publication_state: "verified",
      derivation: {
        validation_status: "valid",
        publication_state: "verified",
        input_freshness: "fresh",
      },
    });
  });

  it("forces a conservative banner for rejected no-claim responses", () => {
    const response = {
      status: "answer",
      response_mode: "scope_redirect",
      trace_id: "trace-rejected-no-claim",
      answer: "Use the official air-quality service for current observations.",
      claims: [],
      evidence: [],
      limitations: [],
      related_links: [{
        title: "Current B.C. AQHI",
        url: "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
        description: "Environment Canada current AQHI observations and forecasts.",
      }],
      validation: { accepted: false },
      status_banner: {
        headline: "Grounded in reviewed official sources",
        detail: "All content was validated against reviewed sources.",
        freshness_label: "Stable reviewed guidance",
        availability_label: "Sources required for this request were available.",
        official_escalation_title: "Broken older escalation",
        official_escalation_url: null,
      },
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toEqual({
      headline: "Support not established",
      detail: "FireLens did not establish or validate support for this response.",
      freshness_label: "Freshness not established",
      availability_label: "This request did not complete with established sources.",
      retrieval_completed_at: null,
      source_updated_at: null,
      official_escalation_title: "Current B.C. AQHI",
      official_escalation_url: "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
    });
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

  it("does not call an unbound follow-up outside FireLens live sources", () => {
    expect(getStatusBanner({
      status: "answer",
      response_mode: "scope_redirect",
      reason_code: "live_data_required",
      trace_id: "trace-unbound",
      answer: "Select a mapped official record or name a British Columbia community.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [],
      status_banner: {
        headline: "Outside FireLens live sources",
        detail: "Use the related official service for information FireLens does not ingest live.",
        freshness_label: "Freshness not applicable",
        availability_label: "Sources required for this request were available.",
      },
    } as unknown as AskResponse)).toMatchObject({
      headline: "Select an official record to continue",
      detail: "Click a fire on the map or name a British Columbia community, then ask again.",
    });
  });

  it("presents a reviewed-source handoff instead of a missing-live-data redirect", () => {
    const response = {
      status: "answer",
      response_mode: "scope_redirect",
      reason_code: "no_approved_evidence",
      trace_id: "trace-reviewed-source-handoff",
      answer: "PreparedBC has related wording, but no reviewed claim directly answers this request.",
      claims: [],
      evidence: [],
      limitations: [],
      related_links: [{
        title: "PreparedBC grab-and-go bag guidance",
        url: "https://example.test/preparedbc-bag",
      }],
      status_banner: {
        headline: "Outside FireLens live sources",
        detail: "Use the related official service for information FireLens does not ingest live.",
        freshness_label: "Freshness not applicable",
        availability_label: "Sources required for this request were available.",
      },
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toMatchObject({
      headline: "The reviewed source does not directly answer this",
      detail: "Open the source for its exact wording.",
    });
    render(<ResponseModeBadge mode="scope_redirect" reasonCode="no_approved_evidence" response={response} />);
    expect(screen.getByText("Reviewed source handoff")).toBeInTheDocument();
  });

  it("uses neutral coverage-limit wording when a reviewed-source handoff has no usable link", () => {
    const noLink = {
      response_mode: "scope_redirect",
      reason_code: "no_approved_evidence",
      related_links: [],
    } as unknown as AskResponse;
    const malformedLink = {
      response_mode: "scope_redirect",
      reason_code: "no_approved_evidence",
      related_links: [{ title: "PreparedBC guidance", url: "not a URL" }],
    } as unknown as AskResponse;

    const { rerender } = render(
      <ResponseModeBadge mode="scope_redirect" reasonCode="no_approved_evidence" response={noLink} />,
    );
    expect(screen.getByText("Coverage limit")).toBeInTheDocument();
    rerender(<ResponseModeBadge mode="scope_redirect" reasonCode="no_approved_evidence" response={malformedLink} />);
    expect(screen.getByText("Coverage limit")).toBeInTheDocument();
  });

  it("requires the canonical related link to be valid before calling it a reviewed-source handoff", () => {
    const response = {
      status: "answer",
      response_mode: "scope_redirect",
      reason_code: "no_approved_evidence",
      trace_id: "trace-broken-canonical-link",
      answer: "PreparedBC has related wording, but no reviewed claim directly answers this request.",
      claims: [],
      evidence: [],
      limitations: [],
      related_links: [
        { title: "PreparedBC guidance", url: "not a URL" },
        { title: "PreparedBC grab-and-go bag guidance", url: "https://example.test/preparedbc-bag" },
      ],
      status_banner: {
        headline: "Outside FireLens live sources",
        detail: "Use the related official service for information FireLens does not ingest live.",
        freshness_label: "Freshness not applicable",
        availability_label: "Sources required for this request were available.",
      },
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toMatchObject({
      headline: "Outside FireLens live sources",
      detail: "Use the related official service for information FireLens does not ingest live.",
      official_escalation_title: null,
      official_escalation_url: null,
    });
    render(<ResponseModeBadge mode="scope_redirect" reasonCode="no_approved_evidence" response={response} />);
    expect(screen.getByText("Coverage limit")).toBeInTheDocument();
  });

  it("retains the official-service redirect for missing live data", () => {
    const response = {
      status: "answer",
      response_mode: "scope_redirect",
      reason_code: "scope_redirect",
      trace_id: "trace-live-service",
      answer: "Use the official road service for current road conditions.",
      claims: [],
      evidence: [],
      limitations: [],
      related_links: [{ title: "DriveBC", url: "https://example.test/drivebc" }],
      status_banner: {
        headline: "Outside FireLens live sources",
        detail: "Use the related official service for information FireLens does not ingest live.",
        freshness_label: "Freshness not applicable",
        availability_label: "Sources required for this request were available.",
      },
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toMatchObject({
      headline: "Outside FireLens live sources",
      detail: "Use the related official service for information FireLens does not ingest live.",
    });
    render(<ResponseModeBadge mode="scope_redirect" reasonCode="scope_redirect" />);
    expect(screen.getByText("Related official service")).toBeInTheDocument();
  });

  it("does not call an unknown source identifier a reviewed-source handoff", () => {
    const response = {
      status: "answer",
      response_mode: "scope_redirect",
      reason_code: "no_approved_evidence",
      trace_id: "trace-unknown-source-id",
      answer: "FireLens could not find an admitted source with that identifier.",
      claims: [],
      evidence: [],
      limitations: [],
      related_links: [],
      status_banner: {
        headline: "Outside FireLens live sources",
        detail: "Use the related official service for information FireLens does not ingest live.",
        freshness_label: "Freshness not applicable",
        availability_label: "Sources required for this request were available.",
      },
    } as unknown as AskResponse;

    expect(getStatusBanner(response)).toMatchObject({
      headline: "Outside FireLens live sources",
      detail: "Use the related official service for information FireLens does not ingest live.",
    });
  });

  it("keeps official records available independently of the street basemap", () => {
    render(<MatchingRecordList results={[record]} />);
    expect(screen.getByRole("list", { name: "Matching this question" })).toHaveTextContent("Listed Fire");
  });

  it("shows fetch time instead of hiding it", () => {
    render(
      <StatusBanner
        banner={{
          headline: "No matching official records",
          detail: "No matching official wildfire records were returned.",
          freshness_label: "No matching records to classify as current or stale",
          availability_label: "Checked BC Wildfire Service incidents as of 2026-08-23T15:30:00+00:00.",
          retrieval_completed_at: "2026-08-23T15:30:00+00:00",
        }}
      />,
    );
    expect(screen.getByText(/Fetched:/)).toBeInTheDocument();
  });

  it("projects an unknown publication kind as unknown rather than a reviewed source fact", () => {
    const malformed = {
      ...grounded,
      claims: grounded.claims.map((claim) => ({
        ...claim,
        publication: {
          kind: "reviewed_official",
          review_status: "approved",
          renderer_id: "firelens.unknown_renderer.v1",
          support_provenance: "typed_inventory",
        },
      })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        support_state: "structured_reviewed",
        support_label: "Reviewed structured claim",
        truth_class: "source_fact",
        publication_state: "verified",
      })),
    } as unknown as AskResponse;
    const card = getProofCards(malformed)[0];
    const claim = malformed.claims![0]!;
    expect(getClaimSupportState(malformed, claim)).toBe("unknown");
    expect(card).toMatchObject({
      support_state: "unknown",
      publication_state: "rejected",
      truth_class: "unknown",
    });
    expect(card!.support_label).not.toBe("Reviewed structured claim");
    expect(card!.support_label).not.toBe("Supported by an exact reviewed quotation");
  });

  it("downgrades a proof card when its claim has no publication authority", () => {
    const malformed = {
      ...grounded,
      claims: grounded.claims.map(({ publication: _publication, ...claim }) => claim),
    } as unknown as AskResponse;

    expect(getProofCards(malformed)[0]).toMatchObject({
      support_state: "unknown",
      truth_class: "unknown",
      publication_state: "rejected",
    });
  });

  it("rebuilds rather than trusting a card whose publication authority is missing", () => {
    const malformed = {
      ...grounded,
      proof_cards: grounded.proof_cards.map(({ publication: _publication, ...card }) => ({
        ...card,
        authority: "Untrusted API authority",
        exact_passage: "Untrusted API wording",
      })),
    } as unknown as AskResponse;

    expect(getProofCards(malformed)[0]).toMatchObject({
      support_state: "source_linked_explanation",
      authority: "PreparedBC",
      exact_passage: "Food & water",
      publication: grounded.claims[0]!.publication,
    });
  });

  it("rebuilds from the claim when a same-kind card differs in authority identity", () => {
    const claimPublication = {
      kind: "structured_reviewed",
      typed_claim_id: "TC-identity",
      review_status: "approved",
      source_revision_sha256: "a".repeat(64),
      source_span_sha256: "b".repeat(64),
      renderer_id: "firelens.structured_renderer.v1",
      support_provenance: "typed_inventory",
      risk_tier: "A",
    };
    const malformed = {
      ...grounded,
      claims: grounded.claims.map((claim) => ({ ...claim, publication: claimPublication })),
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        publication: {
          ...claimPublication,
          source_revision_sha256: "c".repeat(64),
          review_status: "pending_review",
          renderer_id: "firelens.wrong_renderer.v1",
        },
        authority: "Untrusted API authority",
        exact_passage: "Untrusted API wording",
      })),
    } as unknown as AskResponse;

    expect(getProofCards(malformed)[0]).toMatchObject({
      support_state: "structured_reviewed",
      authority: "PreparedBC",
      exact_passage: "Food & water",
      publication: claimPublication,
    });
  });

  it("does not accept an unknown proof-card publication kind", () => {
    const malformed = {
      ...grounded,
      proof_cards: grounded.proof_cards.map((card) => ({
        ...card,
        publication: {
          ...card.publication,
          kind: "unrecognised_publication_kind",
        },
        authority: "Untrusted API authority",
      })),
    } as unknown as AskResponse;

    expect(getProofCards(malformed)[0]).toMatchObject({
      support_state: "source_linked_explanation",
      authority: "PreparedBC",
      publication: grounded.claims[0]!.publication,
    });
  });

  it("rebinds a live card with a mismatched live identity only from its matching live result", () => {
    const livePublication = {
      kind: "official_live_typed",
      typed_live_fact_id: record.result_id,
      review_status: "official_live_record",
      source_revision_sha256: null,
      source_span_sha256: null,
      renderer_id: "firelens.live_typed_renderer.v1",
      support_provenance: "typed_official_live_fact",
      risk_tier: "B",
    };
    const malformed = {
      status: "answer",
      response_mode: "live",
      trace_id: "trace-live-identity-mismatch",
      answer: "Listed Fire is Out of Control.",
      claims: [{
        claim_id: record.result_id,
        text: "Listed Fire",
        evidence_status: "official_live",
        supports: [],
        publication: livePublication,
      }],
      evidence: [],
      limitations: [],
      live_results: [record],
      proof_cards: [{
        claim_id: record.result_id,
        claim_text: "Untrusted live card",
        support_state: "official_live_typed",
        support_label: "Official live record",
        authority: "Untrusted API authority",
        exact_passage: "Untrusted API wording",
        source_title: "Untrusted title",
        source_revision: "Untrusted revision",
        review_state: "Untrusted review",
        critical_fields_checked: "Untrusted validation",
        freshness: "fresh",
        official_url: "https://untrusted.example.test",
        publication: { ...livePublication, typed_live_fact_id: "incident:wrong" },
      }],
      validation: { accepted: true },
    } as unknown as AskResponse;

    expect(getProofCards(malformed)[0]).toMatchObject({
      claim_id: record.result_id,
      claim_text: "Listed Fire",
      authority: record.authority,
      exact_passage: record.status,
      official_url: record.source_url,
      publication: livePublication,
    });
  });
});
