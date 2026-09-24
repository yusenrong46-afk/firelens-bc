import { cleanup, render, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AnswerBody } from "../src/features/ask/AnswerBody";
import { readableAnswer } from "../src/features/ask/readableAnswer";
import { formatAnswerForCopy } from "../src/features/ask/answerActionPresentation";
import type { AskResponse } from "../src/shared/api/api";
import communicationResponse from "./fixtures/v8-communication-bullets.json";
import storedResponse from "./fixtures/bag-readability.json";

const response = storedResponse as AskResponse;
afterEach(cleanup);

it("renders all eleven supplied items and separates the household note without altering the response", () => {
  const before = JSON.stringify(response);
  const { container } = render(<AnswerBody response={response} assistantText="" />);
  const answer = container.querySelector(".answer-markdown") as HTMLElement;
  const items = within(answer).getAllByRole("listitem");
  expect(items).toHaveLength(11);
  expect(items[0]).toHaveTextContent("Bottled water and ready-to-eat food");
  expect(items[3]).toHaveTextContent("hand-crank flashlight");
  expect(items[10]).toHaveTextContent(/^Whistle$/);
  expect(within(answer).getByText(/Start with our basic list/).tagName).toBe("P");
  expect(answer.textContent).toContain("people with disabilities");
  expect(JSON.stringify(response)).toBe(before);
  const words = (text: string) => text.replace(/(?:^|\s)[¢•-]\s+/gm, " ")
    .replace(/([A-Za-z])-\s+/g, "$1-").replace(/\s+/g, " ").trim();
  expect(words(readableAnswer(response.answer!, response.claims))).toBe(words(response.answer!));
  const copy = formatAnswerForCopy(response, response.answer!);
  expect(copy.match(/^- /gm)).toHaveLength(11);
  expect(copy).toContain("\n\n Start with our basic list");
  expect(copy).toContain("Important limits");
  expect(copy).toContain("Sources");
});

it("also formats the supplied guidance section without changing live facts", () => {
  const live = "A fire is 5.5 km away. This is not a safety assessment.";
  const mixed = { ...response, answer_sections: [
    { kind: "current_records", heading: "Current records", text: live },
    { kind: "reviewed_guidance", heading: "Preparedness", text: response.answer! },
  ] } as AskResponse;
  const { container } = render(<AnswerBody response={mixed} assistantText="" />);
  expect(container.querySelectorAll(".answer-markdown li")).toHaveLength(11);
  expect(container.textContent).toContain(live);
});

it("leaves currency, ordinary prose, missing claim matches, and existing Markdown alone", () => {
  for (const text of ["Coins cost 50¢ each; keep 25¢ coins.", "- Water\n- Food", "No supplied guidance."]) {
    expect(readableAnswer(text, response.claims)).toBe(text);
  }
  expect(readableAnswer(response.answer!, [])).toBe(response.answer);
  const background = (response.claims ?? []).map(claim => ({ ...claim, publication: { ...claim.publication!, kind: "general_background" as const } }));
  expect(readableAnswer(response.answer!, background)).toBe(response.answer);
});

it("normalizes quote line wraps and removes only a corroborated leading page folio", () => {
  const text = "3\nOnly a licensed gas\ncontractor can restore service.";
  const claim = { ...response.claims![1]!, text,
    publication: { ...response.claims![1]!.publication!, kind: "official_quote_only" as const },
    supports: [{ evidence_id: "page-three", quote: text }],
  };
  const source = { ...response.evidence![0]!, evidence_id: "page-three", locator: "page:3", primary_text: text };
  const snapshot = JSON.stringify({ claim, source });
  expect(readableAnswer(text, [claim], [source])).toBe("Only a licensed gas contractor can restore service.");
  expect(readableAnswer(text, [claim], [{ ...source, locator: "page:4" }])).toContain("3");
  expect(JSON.stringify({ claim, source })).toBe(snapshot);
});


it("renders the fourth communication bullet even when its retained passage has one marker", () => {
  const recorded = communicationResponse as AskResponse;
  const before = JSON.stringify(recorded);
  const { container } = render(<AnswerBody response={recorded} assistantText="" />);
  const items = container.querySelectorAll(".quote-distinction__excerpt li");
  expect(items).toHaveLength(4);
  expect(items[3]?.textContent).toContain("virtual meeting place");
  expect(items[3]?.textContent?.replace(/\s+/g, " ")).toContain("closed Facebook or WhatsApp group");
  expect(container.textContent).toContain("Data-based services are less likely");
  expect(JSON.stringify(recorded)).toBe(before);
  expect(formatAnswerForCopy(recorded, recorded.answer!).match(/^- /gm)).toHaveLength(4);
});
