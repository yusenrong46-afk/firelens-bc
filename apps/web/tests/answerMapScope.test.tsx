import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LiveResult } from "../src/shared/api/api";
import { AnswerMapScope, answerMapScope } from "../src/features/near-me/AnswerMapScope";
import { MatchingRecordList } from "../src/features/near-me/LiveRecordLists";
import fixture from "./fixtures/v8-selected-followup.json";

const answer = fixture.response.live_results as LiveResult[];
const lookup = fixture.lookup_ids.map((result_id) => ({ ...answer[0]!, result_id }));

describe("answer records versus retained lookup", () => {
  it("keeps the captured one-record follow-up distinct from its ten-record lookup", () => {
    const before = JSON.stringify({ answer, lookup });
    render(<AnswerMapScope answer={answer} lookup={lookup} displayed={lookup} />);
    expect(screen.getByText(/1 of 1 records from this answer shown/)).toBeTruthy();
    expect(screen.getByText(/10 records retained from the lookup shown/)).toBeTruthy();
    expect(JSON.stringify({ answer, lookup })).toBe(before);
  });
  it("does not imply a hidden answer record is currently displayed", () => {
    const filtered = lookup.filter((record) => record.result_id !== answer[0]!.result_id);
    expect(answerMapScope(answer, lookup, filtered)).toEqual({ shown: 0, total: 1, retained: true, lookupCount: 9 });
  });
  it("does not relabel a refreshed province-only record as an answer record", () => {
    const province = { ...answer[0]!, result_id: "incident:province-only" };
    expect(answerMapScope(answer, lookup, [...lookup, province]).shown).toBe(1);
  });
  it("keeps an unchanged lookup identified with its answer", () => {
    expect(answerMapScope(lookup, lookup, lookup).retained).toBe(false);
  });
  it("labels retained lists without reordering their IDs or changing selection", () => {
    render(<MatchingRecordList label="Records retained from the lookup" results={lookup} selectedResultId={answer[0]!.result_id} />);
    const list = screen.getByRole("list", { name: "Records retained from the lookup" });
    expect([...list.querySelectorAll("button[data-result-id]")].map((node) => node.getAttribute("data-result-id"))).toEqual(fixture.lookup_ids);
    expect(list.querySelector('button[aria-pressed="true"]')?.getAttribute("data-result-id")).toBe(answer[0]!.result_id);
  });
});
