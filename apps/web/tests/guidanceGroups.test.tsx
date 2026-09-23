import { cleanup, render, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AnswerBody } from "../src/features/ask/AnswerBody";
import { formatAnswerForCopy } from "../src/features/ask/answerActionPresentation";
import { guidanceGroups } from "../src/features/ask/guidanceGroups";
import { readableAnswer } from "../src/features/ask/readableAnswer";
import type { AskResponse } from "../src/shared/api/api";
import partners from "./fixtures/remaining-partners.json";
import compact from "./fixtures/remaining-compact.json";
afterEach(cleanup);

it.each([[partners, 2], [compact, 3]] as const)("labels every retained claim once, in both the UI and Copy", (fixture, count) => {
  const response = fixture as AskResponse;
  const before = JSON.stringify(response);
  const groups = guidanceGroups(response);
  expect(groups).toHaveLength(count);
  expect(groups.flatMap(g => g.claims.map(c => c.claim_id)).sort()).toEqual(response.claims!.map(c => c.claim_id).sort());
  const {container} = render(<AnswerBody response={response} assistantText="" />);
  const list = within(container).getByRole("list", { name: "Source descriptions by topic" });
  expect(list.children).toHaveLength(count);
  const copy = formatAnswerForCopy(response, response.answer!);
  for (const group of groups) {
    expect(within(list).getByRole("heading", {name: group.heading})).toBeVisible();
    expect(copy).toContain(group.heading);
    for (const claim of group.claims) expect(copy).toContain(readableAnswer(claim.text, response.claims, response.evidence));
  }
  expect(JSON.stringify(response)).toBe(before);
});

it("does not claim a comparison when one side, a source binding, or a matching revision is missing", () => {
  const r = partners as AskResponse;
  expect(guidanceGroups({...r, claims: r.claims!.slice(0,1)})).toEqual([]);
  expect(guidanceGroups({...r, evidence: []})).toEqual([]);
  expect(guidanceGroups({...r, evidence: r.evidence!.map((e,i) => i ? {...e, document_sha256: "b".repeat(64)} : e)})).toEqual([]);
});

it("retains all sprinkler conditions and distinguishes structured guidance from quotations", () => {
  const r = compact as AskResponse;
  const copy = formatAnswerForCopy(r,r.answer!);
  for (const phrase of ["uninsurable water", "If you have installed", "DO NOT", "Structure Protection Specialists", "Follow official evacuation alerts and orders", "local authority", "first responders"]) expect(copy).toContain(phrase);
  expect(copy).toContain("Reviewed guidance:");
  expect(copy).toContain("Exact source wording:");
});
