import { ArrowSquareOut } from "@phosphor-icons/react";
import type { AskResponse } from "../../shared/api/api";
import { getClaimSupportState } from "./proofPresentation";
import type { Claim } from "./responseModel";

const CITABLE_STATES = new Set([
  "supported",
  "structured_reviewed",
  "official_quote_only",
  "source_linked_explanation",
  "conflict",
]);

const EXCERPT_LIMIT = 260;

export type SourceProofItem = {
  key: string;
  publisher: string;
  title: string;
  url: string;
  excerpt: string;
  freshness: string;
  revision?: string | undefined;
  locator?: string | undefined;
  passages: { evidenceId: string; locator: string | undefined; text: string }[];
};

function trimExcerpt(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= EXCERPT_LIMIT) return clean;
  const cut = clean.slice(0, EXCERPT_LIMIT);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), EXCERPT_LIMIT - 40))}…`;
}

/**
 * The reviewed sources behind an answer, one entry per document. The excerpt
 * is the exact quoted passage that supports a claim when there is one, else
 * the passage FireLens read.
 */
export function reviewedSources(response: AskResponse | undefined): SourceProofItem[] {
  const evidence = response?.evidence ?? [];
  if (!response || evidence.length === 0 || response.validation?.accepted === false) return [];
  const claims = (response.claims ?? []) as Claim[];
  const quotesByEvidence = new Map<string, string>();
  const citedIds = new Set<string>();
  for (const claim of claims) {
    if (!CITABLE_STATES.has(getClaimSupportState(response, claim))) continue;
    for (const support of claim.supports ?? []) {
      citedIds.add(support.evidence_id);
      if (support.quote && !quotesByEvidence.has(support.evidence_id)) {
        quotesByEvidence.set(support.evidence_id, support.quote);
      }
    }
  }
  if (claims.length > 0 && citedIds.size === 0) return [];
  const cited = evidence.filter((item) => citedIds.has(item.evidence_id));
  const shown = cited.length > 0 ? cited : evidence;
  const byDocument = new Map<string, SourceProofItem>();
  const items: SourceProofItem[] = [];
  for (const item of shown) {
    const key = `${item.canonical_url}::${item.document_sha256 ?? "unknown"}`;
    const passage = { evidenceId: item.evidence_id, locator: item.locator ?? undefined, text: item.primary_text };
    const existing = byDocument.get(key);
    if (existing) {
      if (!existing.passages.some((entry) => entry.evidenceId === item.evidence_id)) existing.passages.push(passage);
      continue;
    }
    const source: SourceProofItem = {
      key,
      publisher: item.publisher,
      title: item.title,
      url: item.canonical_url,
      excerpt: trimExcerpt(quotesByEvidence.get(item.evidence_id) ?? item.primary_text),
      freshness: "Preparedness reference; publisher may revise this document",
      revision: item.document_sha256 ?? undefined,
      locator: item.locator ?? undefined,
      passages: [passage],
    };
    byDocument.set(key, source);
    items.push(source);
  }
  return items;
}

/** The same passage bindings drive visible quotations and their copied text. */
export function sourcesForQuote(response: AskResponse, quote: string) {
  const evidence = response.evidence ?? [];
  const claims = (response.claims ?? []).filter((claim) => claim.text.trim() === quote.trim());
  const ids = new Set(claims.flatMap((claim) => (claim.supports ?? []).map((support) => support.evidence_id)));
  const bound = evidence.filter((item) => ids.has(item.evidence_id));
  // Only legacy single-source answers without IDs may use the attached source.
  // Missing references and multiple sources never inherit the first document.
  return bound.length || ids.size || evidence.length !== 1 ? bound : evidence;
}

export function SourceProof({
  response,
  showExcerpts = true,
  onInspectEvidence,
}: {
  response: AskResponse | undefined;
  showExcerpts?: boolean;
  onInspectEvidence?: (() => void) | undefined;
}) {
  const items = reviewedSources(response);
  if (items.length === 0) return null;
  return (
    <section className="source-proof" aria-label="Source of this information">
      <h2>{items.length === 1 ? "Source" : `${items.length} sources`}</h2>
      <SourceDocument item={items[0]!} showExcerpts={showExcerpts} />
      {items.length > 1 && <details className="source-proof__more"><summary>{items.length - 1} more source{items.length === 2 ? "" : "s"}</summary>
        {items.slice(1).map((item) => <SourceDocument key={item.key} item={item} showExcerpts={showExcerpts} />)}
      </details>}
      {onInspectEvidence && <button type="button" className="source-proof__inspect" onClick={onInspectEvidence}>Inspect evidence</button>}
    </section>
  );
}

function SourceDocument({ item, showExcerpts }: { item: SourceProofItem; showExcerpts: boolean }) {
  return <article className="source-proof__primary">
        <p className="source-proof__publisher">{item.publisher}</p>
        <p className="source-proof__title">{item.title}</p>
        {showExcerpts && <blockquote>{item.excerpt}</blockquote>}
        <SourceRevision item={item} />
        <a href={item.url} target="_blank" rel="noreferrer">
          Open official source <ArrowSquareOut size={14} aria-hidden="true" />
        </a>
      </article>;
}

function SourceRevision({ item }: { item: SourceProofItem }) {
  return <details className="source-proof__more">
    <summary>{item.passages.length} passage{item.passages.length === 1 ? "" : "s"} · {Array.from(new Set(item.passages.map((passage) => passage.locator).filter(Boolean))).join(" · ") || "Location not supplied"} — supporting text</summary>
    <ol>{item.passages.map((passage) => <li key={passage.evidenceId}>
      <p>{passage.locator ?? "Location not supplied"}</p>
      <blockquote>{passage.text}</blockquote>
    </li>)}</ol>
    <details className="source-proof__technical"><summary>Technical provenance</summary>
    <p>Passage identifiers: {item.passages.map((passage) => passage.evidenceId).join(", ")}</p>
    <p>{item.revision ? <>Document SHA-256: <code style={{ overflowWrap: "anywhere" }}>{item.revision}</code></> : "Document revision not supplied"}</p>
    <p>The publisher link may show a newer edition than the passage cited here.</p>
    </details>
  </details>;
}
