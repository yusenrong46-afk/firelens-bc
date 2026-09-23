import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { reviewedSources, SourceProof } from "../src/features/ask/SourceProof";
import type { AskResponse } from "../src/shared/api/api";

afterEach(cleanup);
const evidence = {
  evidence_id: "E1", title: "Preparedness guide", publisher: "PreparedBC",
  canonical_url: "https://example.test/guide.pdf", locator: "page:5",
  temporal_class: "stable_guidance" as const, review_provenance: "native_text" as const,
  primary_text: "Example source passage.", context_text: "Example source passage.",
  document_sha256: "a".repeat(64),
};
function response(rows: typeof evidence[]): AskResponse {
  return { evidence: rows, claims: [], validation: { accepted: true } } as unknown as AskResponse;
}
test("one URL retains two revisions while duplicate passages share a source entry", () => {
  const result = response([evidence, { ...evidence, evidence_id: "E2", locator: "page:6" }, { ...evidence, evidence_id: "E3", document_sha256: "b".repeat(64) }]);
  const sources = reviewedSources(result);
  expect(sources).toHaveLength(2);
  expect(sources.map((item) => item.revision)).toEqual(["a".repeat(64), "b".repeat(64)]);
  render(<SourceProof response={result} />);
  expect(screen.getByText("1 more source")).toBeInTheDocument();
  expect(screen.getAllByText(/publisher link may show a newer edition/)).toHaveLength(2);
  expect(screen.queryByText(/does not change day to day/)).not.toBeInTheDocument();
});
test("missing source identity is disclosed without an invented revision", () => {
  const { document_sha256: _, ...withoutRevision } = evidence;
  render(<SourceProof response={{ evidence: [withoutRevision], claims: [] } as unknown as AskResponse} />);
  expect(screen.getByText("Document revision not supplied")).toBeInTheDocument();
});

test("one document exposes every passage and distinct known locator without URL rewriting", () => {
  const result = response([evidence, { ...evidence, evidence_id: "E2", locator: "page:6", primary_text: "Second complete passage." }]);
  render(<SourceProof response={result} />);
  expect(screen.getByText(/2 passages · page:5 · page:6/)).toBeInTheDocument();
  expect(screen.getByText("Second complete passage.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open official source/ })).toHaveAttribute("href", evidence.canonical_url);
});

test("all source documents and their later passages remain accessible", () => {
  const rows = [0, 1, 2, 3, 4].map((index) => ({ ...evidence, evidence_id: `E${index}`, canonical_url: `https://example.test/${index}.pdf` }));
  rows.push({ ...rows[0]!, evidence_id: "E9", locator: "page:9" });
  render(<SourceProof response={response(rows)} />);
  expect(screen.getByText(/2 passages · page:5 · page:9/)).toBeInTheDocument();
  expect(screen.getByText("4 more sources")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Open official source/, hidden: true })).toHaveLength(5);
});

test("unsupported and uncited evidence does not enter a cited document's passages", () => {
  const result = { ...response([evidence, { ...evidence, evidence_id: "E2", locator: "page:6" }, { ...evidence, evidence_id: "E3", locator: "page:7" }]),
    claims: [
      { claim_id: "C1", text: "Supported", publication: { kind: "source_linked_explanation" }, supports: [{ evidence_id: "E1", quote: "Example" }] },
      { claim_id: "C2", text: "Unsupported", supports: [{ evidence_id: "E2" }] },
    ],
    proof_cards: [{ claim_id: "C1", support_state: "source_linked_explanation" }, { claim_id: "C2", support_state: "unknown" }],
  } as unknown as AskResponse;
  expect(reviewedSources(result)[0]?.passages.map((item) => item.evidenceId)).toEqual(["E1"]);
  expect(reviewedSources({ ...result, validation: { accepted: false } } as AskResponse)).toEqual([]);
});

test("partial guidance retains two supported passages and exposes missing location honestly", () => {
  const result = { ...response([evidence, { ...evidence, evidence_id: "E2", locator: undefined } as unknown as typeof evidence]),
    response_mode: "mixed", limitations: ["Only part of this request has reviewed support."],
    claims: [
      { claim_id: "C1", text: "First aspect", publication: { kind: "source_linked_explanation" }, supports: [{ evidence_id: "E1" }] },
      { claim_id: "C2", text: "Second aspect", publication: { kind: "official_quote_only" }, supports: [{ evidence_id: "E2" }] },
      { claim_id: "C3", text: "Unresolved aspect", publication: { kind: "abstention" }, supports: [] },
    ],
  } as unknown as AskResponse;
  expect(reviewedSources(result)).toHaveLength(1);
  expect(reviewedSources(result)[0]?.passages.map((item) => item.evidenceId)).toEqual(["E1", "E2"]);
  render(<SourceProof response={result} />);
  expect(screen.getByText("Location not supplied")).toBeInTheDocument();
  expect(screen.getByText("Passage identifiers: E1, E2")).toBeInTheDocument();
  expect(screen.getByText(/2 passages · page:5 —/)).toBeInTheDocument();
});
