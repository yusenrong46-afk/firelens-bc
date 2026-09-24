import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AnswerBody } from "../src/features/ask/AnswerBody";
import { formatAnswerForCopy } from "../src/features/ask/answerActionPresentation";
import { readableAnswer } from "../src/features/ask/readableAnswer";
import recorded from "./fixtures/v8-firewood-comparison.json";
import type { AskResponse } from "../src/shared/api/api";
afterEach(cleanup);
it("keeps a third essential quotation visible without opening source disclosures", () => {
  const r = response();
  const text = "Young children have sensitive lungs and may need to decrease their activities during smoky periods, especially when outdoors.";
  r.claims!.push({ ...r.claims![0]!, claim_id: "C3", text, supports: [{ evidence_id: "E3", quote: text }] });
  r.evidence!.push({ ...r.evidence![0]!, evidence_id: "E3", primary_text: text });
  const { container } = render(<AnswerBody response={r} assistantText="" />);
  const answerQuote = within(container.querySelector(".quote-distinction") as HTMLElement).getByText(text);
  expect(answerQuote).toBeVisible();
  expect(answerQuote.closest("details")).toBeNull();
});
function response(): AskResponse {
  return { status: "answer", response_mode: "grounded", trace_id: "attribution", presentation_shell: "chat", provenance_class: "reviewed_guidance", answer: "Two definitions.", limitations: [],
    claims: [
      { claim_id: "C1", text: "Stages describe operational progress.", evidence_status: "verified_corpus", supports: [{evidence_id: "E1", quote: "Stages describe operational progress."}], publication: {kind: "official_quote_only", renderer_id: "firelens.quote_only_renderer.v1", review_status: "extraction_only", support_provenance: "exact_official_quote"} },
      { claim_id: "C2", text: "Rank describes observed fire behaviour.", evidence_status: "verified_corpus", supports: [{evidence_id: "E2", quote: "Rank describes observed fire behaviour."}], publication: {kind: "official_quote_only", renderer_id: "firelens.quote_only_renderer.v1", review_status: "extraction_only", support_provenance: "exact_official_quote"} },
    ], evidence: [
      {evidence_id: "E1", title: "Stages of control", publisher: "BCWS", canonical_url: "https://example.test/stages", document_sha256: "a".repeat(64), locator: "section:stages", primary_text: "Stages describe operational progress.", context_text: "", temporal_class: "stable_guidance", review_provenance: "native_text"},
      {evidence_id: "E2", title: "Wildfire rank", publisher: "BCWS", canonical_url: "https://example.test/rank", document_sha256: "b".repeat(64), locator: "section:rank", primary_text: "Rank describes observed fire behaviour.", context_text: "", temporal_class: "stable_guidance", review_provenance: "native_text"},
    ],
  } as AskResponse;
}
it("binds each visible quotation to its actual document, not the first response source", () => {
  render(<AnswerBody response={response()} assistantText="" />);
  const quote=screen.getAllByText("Rank describes observed fire behaviour.").find((node) => node.closest(".quote-distinction"))!.closest("blockquote")!;
  expect(within(quote.parentElement!).getByText(/Source: Wildfire rank/)).toBeVisible();
  expect(within(quote.parentElement!).queryByText(/Source: Stages of control/)).not.toBeInTheDocument();
});
it("retains distinct revision bindings even for the same source title and URL", () => {
  const r=response();r.evidence![1]={...r.evidence![1]!,title:r.evidence![0]!.title,canonical_url:r.evidence![0]!.canonical_url};
  const {container}=render(<AnswerBody response={r} assistantText="" />);
  expect(container.querySelectorAll('[data-source-revision="'+"a".repeat(64)+'"]')).toHaveLength(1);
  expect(container.querySelectorAll('[data-source-revision="'+"b".repeat(64)+'"]')).toHaveLength(1);
});
it("does not attribute an unsupported quotation to an unrelated attached document", () => {
  const r=response();r.claims![1]!.supports=[{evidence_id:"missing",quote:r.claims![1]!.text}];
  render(<AnswerBody response={r} assistantText="" />);
  const quote=screen.getAllByText("Rank describes observed fire behaviour.").find((node) => node.closest(".quote-distinction"))!.closest("blockquote")!;
  expect(within(quote.parentElement!).getByText("Source attribution unavailable")).toBeVisible();
});

it("copies each passage with its document and supplied locator", () => {
  const r = response();
  const copy = formatAnswerForCopy(r, r.answer!);
  expect(copy).toContain("“Stages describe operational progress.”\nSource: Stages of control · section:stages");
  expect(copy).toContain("“Rank describes observed fire behaviour.”\nSource: Wildfire rank · section:rank");
});
it("copies the recorded firewood comparison with the original passage bindings", () => {
  const r = recorded as AskResponse;
  const copy = formatAnswerForCopy(r, r.answer!);
  for (const claim of r.claims!) {
    const source = r.evidence!.find(item => item.evidence_id === claim.supports?.[0]?.evidence_id)!;
    const displayed = readableAnswer(claim.text.trim(), r.claims, r.evidence);
    expect(copy).toContain(`“${displayed}”\nSource: ${source.title} · ${source.locator}`);
  }
});
it("keeps same-URL revisions distinct in Copy without leaking internal hashes", () => {
  const r=response(); r.evidence![1]={...r.evidence![1]!,title:r.evidence![0]!.title,canonical_url:r.evidence![0]!.canonical_url};
  const copy=formatAnswerForCopy(r,r.answer!);
  expect(copy).toContain("Retained revision 1"); expect(copy).toContain("Retained revision 2");
  expect(copy).not.toContain("a".repeat(64)); expect(copy).not.toContain("b".repeat(64));
});
it("does not repair a broken copied citation with an unrelated document", () => {
  const r=response(); r.claims![1]!.supports=[{evidence_id:"missing",quote:r.claims![1]!.text}];
  expect(formatAnswerForCopy(r,r.answer!)).toContain("“Rank describes observed fire behaviour.”\nSource attribution unavailable");
});
