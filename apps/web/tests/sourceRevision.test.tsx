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
