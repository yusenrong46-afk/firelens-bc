import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";
import { deriveContextChips } from "../src/app/ContextChips";
import type { AskResponse } from "../src/shared/api/api";
import { wrapAppFetch } from "./fetchStub";

vi.mock("../src/features/near-me/LiveMap", () => ({ LiveMap: () => <div>Offline map</div> }));
vi.mock("../src/features/near-me/AtlasLiveMap", () => ({ default: () => <div>Offline map</div> }));

const spatial: AskResponse = {
  status: "answer", response_mode: "mixed", presentation_shell: "spatial",
  trace_id: "spatial-evidence-fixture", provenance_class: "mixed", answer: "A listed record and a source passage are attached.",
  claims: [{ claim_id: "C1", text: "Pack food and water.", evidence_status: "verified_corpus",
    supports: [{ evidence_id: "E1", quote: "Food & water" }],
    publication: { kind: "source_linked_explanation", review_status: "source_linked", renderer_id: "firelens.explanation_renderer.v1", support_provenance: "validated_grounded_explanation" } }],
  evidence: [{ evidence_id: "E1", title: "Preparedness fixture", publisher: "PreparedBC", canonical_url: "https://example.test/guide.pdf", primary_text: "Food & water", context_text: "Food & water", review_provenance: "native_text", temporal_class: "stable_guidance", locator: "Page 5" }],
  live_results: [{ result_id: "incident:fixture", kind: "incident", authority: "BC Wildfire Service", source_url: "https://example.test/fire", retrieved_at: "2026-09-15T12:00:00Z", source_updated_at: "2026-09-15T11:00:00Z", status: "Being Held", geometry_relation: "nearby", freshness: "fresh", geometry: { type: "Point", coordinates: [-119.5, 49.9] }, fire_of_note: false }],
  limitations: [], suggested_questions: [], validation: { accepted: true, schema_valid: true, citation_ids_valid: true, quotes_exact: true, policy_valid: true, claim_support_valid: true, errors: [] },
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("product experience protected regressions", () => {
  it("opens evidence on a spatial answer and restores focus", async () => {
    vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockImplementation((url) => Promise.resolve(new Response(JSON.stringify(String(url).includes("/ask") ? spatial : { results: [], unavailable_layers: [] }), { status: 200 })))));
    const user = userEvent.setup(); render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show nearby records and preparedness");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText(spatial.answer!);
    await user.click(screen.getByText("More detail on each statement"));
    const trigger = screen.getByRole("button", { name: /Review technical evidence for/ });
    await user.click(trigger);
    expect(screen.getByRole("complementary", { name: "Source for this statement" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close answer context" }));
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each(["fresh", "stale"] as const)("does not label evacuation-only %s records as current fires", (freshness) => {
    const response = { ...spatial, response_mode: "live" as const, aggregate_freshness: freshness, live_results: [{ ...spatial.live_results![0]!, kind: "evacuation" as const, freshness }] };
    const chips = deriveContextChips({ response });
    expect(chips.map((chip) => chip.label)).not.toContain("Current fires");
    expect(chips.find((chip) => chip.id === "scope-current")?.label).toBe("Evacuation records");
  });
});


describe("Home task flows", () => {
  function setup(response: AskResponse = spatial) {
    const requests: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockImplementation((url, init) => {
      if (String(url).includes("/ask")) requests.push(JSON.parse(init.body));
      return Promise.resolve(new Response(JSON.stringify(String(url).includes("/ask") ? response : { results: [], unavailable_layers: [] }), { status: 200 }));
    })));
    render(<App />);
    return { user: userEvent.setup(), requests };
  }

  it("starts with a composer and prepares a question without submitting", async () => {
    const { user, requests } = setup();
    expect(screen.getAllByLabelText("Ask FireLens a question")).toHaveLength(1);
    expect(screen.queryByLabelText("BC community for a nearby lookup")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Ask FireLens a question" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(within(screen.getByRole("dialog", { name: "FireLens menu" })).getByRole("button", { name: "Preparedness" }));
    expect(screen.getByLabelText("Ask FireLens a question")).toHaveValue("What belongs in a wildfire grab-and-go bag?");
    await waitFor(() => expect(screen.getByLabelText("Ask FireLens a question")).toHaveFocus());
    expect(requests).toHaveLength(0);
  });

  it("submits the canonical nearby layers question once", async () => {
    const { user, requests } = setup();
    await user.click(screen.getByRole("button", { name: "Near me" }));
    const submit = screen.getByRole("button", { name: "Check my area" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("BC community for a nearby lookup"), "Kelowna");
    await user.click(submit);
    await screen.findByText(spatial.answer!);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ question: "Show the incident, perimeter, and evacuation records near Kelowna.", location: { label: "Kelowna", radius_km: 50 } });
    expect(screen.getAllByLabelText("Ask FireLens a question")).toHaveLength(1);
  });

  it("keeps a draft when expanding and returning from the B.C. map", async () => {
    const { user, requests } = setup();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "A draft question");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(screen.getByRole("button", { name: "Explore B.C. records" }));
    expect(screen.queryByRole("textbox", { name: "Ask FireLens a question" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to Home" }));
    expect(screen.getByLabelText("Ask FireLens a question")).toHaveValue("A draft question");
    expect(requests).toHaveLength(0);
  });
  it.each(["grounded", "background", "analysis"] as const)("global Map opens and returns from a %s answer", async (mode) => {
    const response: AskResponse = { ...spatial, response_mode: mode === "analysis" ? "live" : mode, presentation_shell: mode === "analysis" ? "analysis" : "chat", claims: [], evidence: [], live_results: mode === "analysis" ? [spatial.live_results![0]!, { ...spatial.live_results![0]!, result_id: "incident:second" }] : [] };
    const { user, requests } = setup(response);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "A test question");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText(response.answer!);
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(screen.getByRole("button", { name: "Explore B.C. records" }));
    expect(await screen.findByText("Offline map")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to answer" }));
    expect(screen.getByLabelText("Ask FireLens a question")).toBeVisible();
    expect(requests).toHaveLength(1);
  });

});
