import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AskStartPanel } from "../src/features/ask/AskStartPanel";

describe("AskStartPanel", () => {
  it("keeps the start surface concise with three question starters", async () => {
    const onAsk = vi.fn();
    const user = userEvent.setup();
    render(
      <AskStartPanel
        locationLabel="Kelowna, BC"
        onAsk={onAsk}
        onLocationChange={vi.fn()}
        onUseApproximateLocation={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Ask about a fire, a B.C. place, or preparedness." })).toBeInTheDocument();
    expect(screen.getByLabelText("BC community for a nearby lookup")).toBeInTheDocument();
    const starters = screen.getByRole("group", { name: "Start with an intent" });
    expect(screen.getAllByRole("button", { name: /\?/ })).toHaveLength(3);
    expect(starters).toHaveTextContent("Fires near this place?");
    expect(starters).toHaveTextContent("Wildfire distribution?");
    expect(starters).toHaveTextContent("What to pack?");

    await user.click(screen.getByRole("button", { name: "Fires near this place?" }));
    expect(onAsk).toHaveBeenCalledWith("What official fires are near Kelowna, BC?");
  });
});
