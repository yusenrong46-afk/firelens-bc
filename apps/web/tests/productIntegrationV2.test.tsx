import { fireEvent, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { App } from "../src/app/App";
import type { FireLensSession } from "../src/features/ask/useFireLensSession";
import type { AskResponse } from "../src/shared/api/api";
import { wrapAppFetch, jsonResponse } from "./fetchStub";

vi.mock("../src/features/near-me/AtlasLiveMap", () => ({ default: ({ session }: { session: FireLensSession }) => {
  const [filter, setFilter] = useState("All layers");
  return <section id="official-map" aria-label="Official wildfire records map"><button onClick={() => setFilter("Fires only")}>{filter}</button><button onClick={() => session.setSelectedLiveResultId("incident:outside")}>Select other map record</button></section>;
} }));
const guidance: AskResponse = { status: "answer", response_mode: "grounded", provenance_class: "reviewed_guidance", presentation_shell: "chat", trace_id: "guidance-v2", answer: "Retained official guidance.", claims: [], evidence: [], limitations: ["Conditions remain visible."], live_results: [], suggested_questions: [] };
const record = { result_id: "incident:one", kind: "incident" as const, authority: "BC Wildfire Service", source_url: "https://example.test/answer-observation", retrieved_at: "2026-09-20T10:00:00Z", source_updated_at: "2026-09-20T09:00:00Z", status: "Being Held", geometry_relation: "nearby" as const, freshness: "fresh" as const, geometry: { type: "Point" as const, coordinates: [-119.5, 49.9] }, fire_of_note: false };
const spatial: AskResponse = { ...guidance, response_mode: "live", presentation_shell: "spatial", trace_id: "spatial-v2", live_results: [record] };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function setup(response: AskResponse) {
  const fetch = wrapAppFetch(vi.fn((url) => Promise.resolve(jsonResponse(String(url).includes("/ask") ? response : { results: [{ ...record, source_url: "https://example.test/refreshed-observation", retrieved_at: "2026-09-20T11:00:00Z" }], unavailable_layers: [], layer_statuses: [] }))));
  vi.stubGlobal("fetch", fetch); render(<App />); fireEvent.click(screen.getByRole("button", { name: "Ask FireLens" })); return { user: userEvent.setup(), fetch };
}
async function ask(user: ReturnType<typeof userEvent.setup>) { await user.type(screen.getByLabelText("Ask FireLens a question"), "A source question"); await user.click(screen.getByLabelText("Send question")); await screen.findByText(guidance.answer!); }

describe("task-led product integration v2", () => {
  it("keeps partial-answer warnings visible even with an official-handoff reason", async () => {
    const response: AskResponse = {
      ...guidance,
      response_mode: "partial",
      reason_code: "high_risk_claim_not_structured",
      limitations: ["Not supported by selected evidence: an outcome guarantee"],
    };
    const { user, fetch } = setup(response);
    await ask(user);
    expect(screen.getByRole("complementary", { name: "Answer limitations" })).toBeVisible();
    expect(screen.getByText(response.limitations![0]!)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Why this answer?" }));
    expect(screen.getAllByText(response.limitations![0]!).some((node) => node.closest("aside[aria-label='Answer limitations']"))).toBe(true);
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/ask"))).toHaveLength(1);
  });
  it("loads Home map once and hides it for a guidance answer", async () => {
    const { user, fetch } = setup(guidance);
    await waitFor(() => expect(fetch.mock.calls.filter(([url]) => String(url).includes("/live/map"))).toHaveLength(1));
    await ask(user);
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/live/map"))).toHaveLength(1);
    expect(screen.getByText("Conditions remain visible.")).toBeVisible();
  });

  it("retains the same map component and filters through expand and return", async () => {
    const { user } = setup(spatial); await ask(user);
    const map = await screen.findByRole("region", { name: "Official wildfire records map" });
    await user.click(screen.getByText("1 matching records"));
    const mapAction = screen.getByRole("button", { name: /^(Show these on the map|View map —)/ });
    expect(mapAction).toHaveAttribute("aria-controls", "map-context");
    expect(document.getElementById(mapAction.getAttribute("aria-controls")!)).toHaveAttribute("aria-label", "Map");
    await user.click(screen.getByRole("button", { name: "All layers" }));
    await user.click(screen.getByRole("button", { name: "Expand map" }));
    expect(screen.getByRole("region", { name: "Official wildfire records map" })).toBe(map);
    expect(screen.queryByRole("link", { name: "Skip to conversation" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to official map" })).toHaveAttribute("href", "#official-map");
    await user.click(screen.getByRole("button", { name: "Back to answer" }));
    expect(screen.getByRole("region", { name: "Official wildfire records map" })).toBe(map);
    expect(screen.getByRole("button", { name: "Fires only" })).toBeVisible();
  });
  it("Back to map preserves answer, map filters, and actual follow-up history", async () => {
    const { user, fetch } = setup(spatial); await ask(user);
    await user.click(screen.getByRole("button", { name: "All layers" }));
    await user.click(screen.getByRole("button", { name: "Back to map" }));
    expect(screen.getByRole("button", { name: "Fires only" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Back to answer" }));
    expect(screen.getByText(guidance.answer!)).toBeVisible();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Explain that source");
    await user.click(screen.getByLabelText("Send question"));
    const calls = fetch.mock.calls.filter(([url]) => String(url).includes("/ask"));
    await waitFor(() => expect(calls).toHaveLength(2));
    const body = JSON.parse(String(calls[1]![1]?.body));
    expect(body.history[0].content).toBe("A source question");
    expect(body.history[1].content).toContain(guidance.answer!);
  });
  it("opens source evidence in a dialog without replacing the answer snapshot", async () => {
    const { user, fetch } = setup(spatial); await ask(user);
    await user.click(await screen.findByRole("button", { name: "Select other map record" }));
    await user.click(screen.getByRole("button", { name: "Why this answer?" }));
    await user.click(screen.getByRole("button", { name: "Inspect evidence" }));
    expect(screen.getByRole("dialog", { name: "Inspect answer evidence" })).toBeVisible();
    expect(screen.getByText(/selected map record is outside this answer/)).toBeVisible();
    const sources = screen.getByRole("complementary", { name: "Official sources" });
    expect(sources.querySelector('a[href="https://example.test/answer-observation"]')).not.toBeNull();
    expect(sources.querySelector('a[href="https://example.test/refreshed-observation"]')).toBeNull();
    await user.click(screen.getByRole("button", { name: "Close answer context" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Inspect evidence" })).toHaveFocus());
    expect(screen.getByText(guidance.answer!)).toBeVisible();
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/ask"))).toHaveLength(1);
  });
});
