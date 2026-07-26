import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { App } from "../src/App";

const answer = {
  status: "answer",
  trace_id: "trace-123",
  answer: "Keep water and food in a grab-and-go bag.",
  claims: [
    {
      claim_id: "C1",
      text: "Keep water and food in a grab-and-go bag.",
      supports: [{ evidence_id: "E1", quote: "Food & water" }],
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
      primary_text: "Grab-and-Go Bag: Food & water",
      context_text: "Grab-and-Go Bag: Food & water and emergency supplies.",
    },
  ],
  limitations: ["Stable guidance only."],
  validation: {
    accepted: true,
    schema_valid: true,
    citation_ids_valid: true,
    quotes_exact: true,
    policy_valid: true,
    errors: [],
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FireLens Source Lens", () => {
  it("renders a verified answer and its local evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "What goes in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Cited claims in this answer")).toBeInTheDocument();
    expect(screen.getAllByText("Keep water and food in a grab-and-go bag.").length).toBeGreaterThan(1);
    expect(screen.getByText("Food & water").tagName).toBe("MARK");
    expect(screen.getByText("PreparedBC")).toBeInTheDocument();
  });

  it("renders a typed abstention without evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "abstention",
        trace_id: "trace-live",
        answer: "This question requires current official information.",
        claims: [],
        evidence: [],
        limitations: ["Static guidance cannot establish current status."],
        reason_code: "live_data_required",
      }), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "Is a fire active near me right now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens did not generate guidance")).toBeInTheDocument();
    expect(screen.getByText(/live_data_required/)).toBeInTheDocument();
    expect(screen.queryByText("Cited claims in this answer")).not.toBeInTheDocument();
  });

  it("offers retry only for a retryable provider failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        trace_id: "trace-error",
        error_kind: "rate_limit",
        message: "The required OpenRouter service is unavailable.",
        retryable: true,
      }), { status: 503 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "How should I prepare for wildfire?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByRole("button", { name: "Retry this question" })).toBeInTheDocument();
  });

  it("has no automated accessibility violations in the idle state", async () => {
    const { container } = render(<App />);
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });

  it("has no automated accessibility violations in the evidence state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("Cited claims in this answer");
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });
});
