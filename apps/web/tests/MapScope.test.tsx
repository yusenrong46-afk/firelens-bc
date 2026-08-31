import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MapScope } from "../src/features/near-me/MapScope";

afterEach(cleanup);

describe("map result scope truth", () => {
  it("states that an empty official result is not an all-clear", () => {
    render(<MapScope displayedCount={0} displayedMatchingCount={0} matchingCount={0} resultCount={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("No official map records were returned");
    expect(screen.getByRole("status")).toHaveTextContent("not an all-clear");
  });

  it("distinguishes province context from records matching the question", () => {
    render(<MapScope displayedCount={4} displayedMatchingCount={0} matchingCount={0} resultCount={4} />);
    expect(screen.getByText(/No records were marked as matching this question/)).toHaveTextContent(
      "The map shows 4 official records returned for B.C.",
    );
  });

  it("reports matching, province, and filter scopes separately", () => {
    render(<MapScope displayedCount={3} displayedMatchingCount={1} matchingCount={2} resultCount={5} />);
    const scope = screen.getByText(/1 matching record is shown/);
    expect(scope).toHaveTextContent("2 records were returned for this question before filtering");
    expect(scope).toHaveTextContent("2 other official records are also shown for B.C.");
    expect(scope).toHaveTextContent("Filters change only what is shown");
  });

  it("does not say unrelated records are shown after filters hide them", () => {
    render(<MapScope displayedCount={1} displayedMatchingCount={1} matchingCount={2} resultCount={5} />);

    const scope = screen.getByText(/1 matching record is shown/);
    expect(scope).toHaveTextContent("3 other official records are hidden by current filters");
    expect(scope).not.toHaveTextContent("are also shown");
  });

  it("distinguishes hidden matching records from unrelated records that remain displayed", () => {
    render(<MapScope displayedCount={2} displayedMatchingCount={0} matchingCount={1} resultCount={3} />);

    const scope = screen.getByText(/current filters hide every matching record/);
    expect(scope).toHaveTextContent("2 other official records are also shown for B.C.");
  });
});
