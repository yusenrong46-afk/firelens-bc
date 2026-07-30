import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { App } from "../src/App";

const answer = {
  status: "answer",
  response_mode: "grounded",
  trace_id: "trace-123",
  answer: "Keep water and food in a grab-and-go bag.",
  suggested_questions: ["How often should I review my emergency plan?"],
  claims: [
    {
      claim_id: "C1",
      text: "Keep water and food in a grab-and-go bag.",
      evidence_status: "verified_corpus",
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
      review_provenance: "human_verified_repair",
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
  it("shows capability suggestions before the first question", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "What belongs in a grab-and-go bag?" })).toBeInTheDocument();
    expect(screen.getByText("0 of 6 turns in context")).toBeInTheDocument();
  });

  it("renders a capability response with API suggestions and no evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "capability",
        trace_id: "trace-capability",
        answer: "I can help you explore reviewed wildfire preparedness guidance.",
        suggested_questions: ["How should I prepare a household emergency plan?"],
        claims: [],
        evidence: [],
        limitations: [],
      }), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "What can you help me with?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens topics")).toBeInTheDocument();
    expect(screen.getByText("Explore the FireLens collection")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How should I prepare a household emergency plan?" })).toBeInTheDocument();
    expect(screen.queryByText("Retrieved passage")).not.toBeInTheDocument();
  });

  it("renders a verified answer and its local evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "What goes in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Sources supporting this answer")).toBeInTheDocument();
    expect(screen.getByText("Reviewed sources")).toBeInTheDocument();
    expect(screen.getAllByText("Keep water and food in a grab-and-go bag.").length).toBeGreaterThan(1);
    expect(screen.getByText("Food & water").tagName).toBe("MARK");
    expect(screen.getByText("PreparedBC")).toBeInTheDocument();
    expect(screen.getByText("Human-verified source transcription")).toBeInTheDocument();
  });

  it("renders labelled background without an evidence interaction", async () => {
    const backgroundClaim = "Embers can travel ahead of a wildfire front.";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "background",
        trace_id: "trace-background",
        answer: backgroundClaim,
        suggested_questions: [],
        claims: [{
          claim_id: "C1",
          text: backgroundClaim,
          evidence_status: "general_background",
          supports: [],
        }],
        evidence: [],
        limitations: ["General background — not verified against the FireLens corpus."],
      }), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "Why can embers be dangerous?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("General background")).toBeInTheDocument();
    expect(screen.getByText("General background — no corpus evidence attached")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: backgroundClaim })).not.toBeInTheDocument();
    expect(screen.queryByText("Retrieved passage")).not.toBeInTheDocument();
  });

  it("renders a typed abstention without evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "abstention",
        response_mode: "abstention",
        trace_id: "trace-live",
        answer: "This question requires current official information.",
        suggested_questions: [],
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
    expect(screen.getByText("Official current information required")).toBeInTheDocument();
    expect(screen.getByText(/live_data_required/)).toBeInTheDocument();
    expect(screen.queryByText("Sources supporting this answer")).not.toBeInTheDocument();
  });

  it("renders official live records in the map panel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-live-map",
        answer: "Current official information: Test Fire is Out of Control.",
        claims: [],
        evidence: [],
        limitations: ["No matching record is not a safety determination."],
        live_results: [{
          result_id: "incident:7",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/7",
          source_updated_at: "2026-07-28T11:55:00Z",
          retrieved_at: "2026-07-28T12:00:00Z",
          freshness: "fresh",
          status: "Out of Control",
          name: "Test Fire",
          geometry_relation: "nearby",
          geometry: { type: "Point", coordinates: [-123.5, 49.5] },
        }],
        unavailable_layers: ["evacuation"],
      }), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask a preparedness question"), "Is there an active wildfire now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Current BC wildfire information")).toBeInTheDocument();
    expect(screen.getAllByText("Official live records").length).toBeGreaterThan(0);
    expect(screen.getByText("Test Fire")).toBeInTheDocument();
    expect(screen.getByText(/Some official layers are unavailable: evacuation/)).toBeInTheDocument();
    expect(screen.getByText(/Source updated/)).toBeInTheDocument();
    expect(screen.getByText(/Retrieved/)).toBeInTheDocument();
  });

  it("sends completed turns with a follow-up question", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask a preparedness question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
    await user.type(screen.getByLabelText("Ask a preparedness question"), "Why does that matter?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const firstPayload = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    const secondPayload = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
    expect(firstPayload.history).toEqual([]);
    expect(secondPayload.history).toEqual([
      { role: "user", content: "What should I pack?" },
      { role: "assistant", content: answer.answer },
    ]);
  });

  it("uses the server-bounded assistant history representation", async () => {
    const longAnswer = "A".repeat(7_000);
    const boundedHistory = `${"A".repeat(5_997)}...`;
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({
        ...answer,
        answer: longAnswer,
        history_text: boundedHistory,
      }), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask a preparedness question"), "Question one");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
    await user.type(screen.getByLabelText("Ask a preparedness question"), "Question two");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const secondPayload = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    expect(secondPayload.history[1]).toEqual({
      role: "assistant",
      content: boundedHistory,
    });
  });

  it("bounds request history at six turns", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    for (const question of ["Question one", "Question two", "Question three", "Question four"]) {
      await user.type(screen.getByLabelText("Ask a preparedness question"), question);
      await user.click(screen.getByLabelText("Send question"));
      await screen.findByText(question);
      await waitFor(() => expect(screen.getByLabelText("Ask a preparedness question")).not.toBeDisabled());
    }

    const fourthPayload = JSON.parse(String(fetchMock.mock.calls[3][1]?.body));
    expect(fourthPayload.history).toHaveLength(6);
    expect(fourthPayload.history[0]).toEqual({ role: "user", content: "Question one" });
    expect(fourthPayload.history[5]).toEqual({ role: "assistant", content: answer.answer });
  });

  it("clears local context before the next request", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask a preparedness question"), "First question");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
    await user.click(screen.getByLabelText("Clear conversation history"));
    expect(screen.getByText("0 of 6 turns in context")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask a preparedness question"), "Fresh question");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const payload = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
    expect(payload.history).toEqual([]);
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
    await screen.findByText("Sources supporting this answer");
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });
});
