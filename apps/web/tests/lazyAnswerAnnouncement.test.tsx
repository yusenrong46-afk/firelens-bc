import { fireEvent, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../src/app/App";
import { wrapAppFetch } from "./fetchStub";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("announces an immediately returned answer without a separate answer-view download", async () => {
  vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockResolvedValue(new Response(JSON.stringify({
    status: "answer", response_mode: "grounded", trace_id: "fast-answer-before-view",
    answer: "Prepare water, food, and medication.", claims: [], evidence: [], limitations: [],
  }), { status: 200 }))));
  const user = userEvent.setup();
  render(<App />); fireEvent.click(screen.getByRole("button", { name: "Ask FireLens" }));
  await user.type(screen.getByLabelText("Ask FireLens a question"), "What should I pack?");
  await user.click(screen.getByLabelText("Send question"));
  expect(await screen.findByText("Prepare water, food, and medication.")).toBeVisible();
  expect(await screen.findByText("FireLens response ready.")).toHaveAttribute("aria-live", "polite");
  expect(screen.queryByText("Loading answer view…")).not.toBeInTheDocument();
});
