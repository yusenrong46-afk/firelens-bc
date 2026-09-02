import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AskStartPanel } from "../src/features/ask/AskStartPanel";
import catalogue from "../../../data/capabilities/guided_questions.v1.json";
import { wrapAppFetch } from "./fetchStub";

// The API adds the integrity envelope around this real 24-question registry.
const loadedCatalogue = { ...catalogue, catalogue_sha256: "0".repeat(64) };

function response() {
  return new Response(JSON.stringify(loadedCatalogue), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function renderPanel({ locationLabel = "Kelowna, BC", onSelectQuestion = vi.fn() } = {}) {
  return render(
    <AskStartPanel
      locationLabel={locationLabel}
      onSelectQuestion={onSelectQuestion}
      onLocationChange={vi.fn()}
      onUseApproximateLocation={vi.fn()}
    />,
  );
}

describe("AskStartPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", wrapAppFetch(() => response()));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("keeps free text primary and fills a selected guided question without submitting", async () => {
    const onSelectQuestion = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onSelectQuestion });

    expect(screen.getByRole("heading", { name: "Ask about a fire, a B.C. place, or preparedness." })).toBeInTheDocument();
    expect(screen.getByLabelText("BC community for a nearby lookup")).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: /Browse guided questions/ });
    await user.click(trigger);
    const panel = await screen.findByRole("region", { name: "Guided questions" });
    expect(within(panel).getAllByRole("listitem")).toHaveLength(24);
    expect(trigger).toHaveAccessibleName("Browse guided questions · 24");
    await user.click(screen.getByRole("button", { name: /Nearby wildfire records/ }));

    expect(onSelectQuestion).toHaveBeenCalledTimes(1);
    expect(onSelectQuestion).toHaveBeenCalledWith("What official wildfire records are near Kelowna, BC?");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("guided-questions"))).toBe(true);
    expect(screen.getByRole("status")).toHaveTextContent("Filled composer with: What official wildfire records are near Kelowna, BC?");
  });

  it("aborts a pending request and retries from a fresh request after reopening", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      if (fetchMock.mock.calls.length === 2) queueMicrotask(() => resolve(response()));
    }));
    vi.stubGlobal("fetch", wrapAppFetch(fetchMock));
    renderPanel();

    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Close guided questions" }));
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit | undefined)?.signal?.aborted).toBe(true);

    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("button", { name: /Listed wildfires/ })).toBeInTheDocument();
  });

  it("keeps the free-text/place controls available when the catalogue fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockRejectedValue(new Error("offline"))));
    renderPanel();

    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    expect(await screen.findByRole("status", { name: "Guided questions status" })).toHaveTextContent(/temporarily unavailable/i);
    expect(screen.getByRole("button", { name: "Retry guided questions" })).toBeInTheDocument();
    expect(screen.getByLabelText("BC community for a nearby lookup")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry guided questions" })).toHaveFocus());
  });

  it("searches and filters the semantic question list", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));

    const search = screen.getByRole("searchbox", { name: "Search guided questions" });
    await user.type(search, "bag");
    expect(screen.getByRole("button", { name: /Grab-and-go bag/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Listed wildfires/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.selectOptions(screen.getByRole("combobox", { name: "Filter guided questions by category" }), "current_bc_records");
    expect(screen.getByRole("heading", { name: "Current B.C. records" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Prepare" })).not.toBeInTheDocument();
  });

  it("Escape closes the disclosure and restores focus to its trigger", async () => {
    const user = userEvent.setup();
    renderPanel();
    const trigger = screen.getByRole("button", { name: /Browse guided questions/ });
    await user.click(trigger);
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "Search guided questions" })).toHaveFocus());
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Guided questions" })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("does not fabricate a place when filling a location template", async () => {
    const onSelectQuestion = vi.fn();
    const user = userEvent.setup();
    renderPanel({ locationLabel: "", onSelectQuestion });
    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    await user.click(screen.getByRole("button", { name: /Nearby wildfire records/ }));
    expect(onSelectQuestion).toHaveBeenCalledWith("What official wildfire records are near {place}?");
  });

  it("rejects malformed loaded catalogues instead of presenting a non-canonical count", async () => {
    const user = userEvent.setup();
    const malformed = {
      ...catalogue,
      categories: catalogue.categories.map((category, index) => index === 0
        ? { ...category, questions: category.questions.slice(0, -1) }
        : category),
    };
    vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockResolvedValue(new Response(JSON.stringify(malformed), { status: 200 }))));
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    expect(await screen.findByRole("status", { name: "Guided questions status" })).toHaveTextContent(/temporarily unavailable/i);
    expect(screen.queryByRole("button", { name: /Listed wildfires/ })).not.toBeInTheDocument();
  });

  it("retries a failed catalogue and restores the searchable list", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(response());
    vi.stubGlobal("fetch", wrapAppFetch(fetchMock));
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Browse guided questions/ }));
    await screen.findByRole("button", { name: "Retry guided questions" });
    await user.click(screen.getByRole("button", { name: "Retry guided questions" }));
    expect(await screen.findByRole("button", { name: /Listed wildfires/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
