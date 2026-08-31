import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeedbackControls } from "../src/features/feedback/FeedbackControls";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FeedbackControls", () => {
  it("discloses the payload and sends a selected category in one action", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<FeedbackControls traceId="trace-feedback" />);

    const issueButton = screen.getByRole("button", { name: "Report" });
    expect(screen.getByText(/does not change the answer/i)).toBeInTheDocument();
    expect(issueButton).toHaveAttribute("aria-expanded", "false");
    await user.click(issueButton);
    expect(issueButton).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Stale or wrong live data" }));

    expect(await screen.findByText("Feedback received")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/feedback", expect.objectContaining({
      body: JSON.stringify({ trace_id: "trace-feedback", category: "stale_or_wrong_live_data" }),
    }));
  });

  it("resets the prior response state when the trace changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { rerender } = render(<FeedbackControls traceId="trace-one" />);

    await user.click(screen.getByRole("button", { name: "Helpful" }));
    expect(await screen.findByText("Feedback received")).toBeInTheDocument();
    rerender(<FeedbackControls traceId="trace-two" />);

    expect(await screen.findByRole("button", { name: "Helpful" })).toBeInTheDocument();
    expect(screen.queryByText("Feedback received")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Report" })).toHaveAttribute("aria-expanded", "false");
  });
});
