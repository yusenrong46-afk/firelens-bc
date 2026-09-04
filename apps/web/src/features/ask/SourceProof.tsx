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
  const seen = new Set<string>();
  const items: SourceProofItem[] = [];
  for (const item of shown) {
    const key = `${item.canonical_url}::${item.title}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({
      key,
      publisher: item.publisher,
      title: item.title,
      url: item.canonical_url,
      excerpt: trimExcerpt(quotesByEvidence.get(item.evidence_id) ?? item.primary_text),
      freshness: item.temporal_class === "stable_guidance"
        ? "Reviewed guidance; does not change day to day"
        : "Reviewed source",
    });
    if (items.length === 4) break;
  }
  return items;
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
  const [primary, ...rest] = items;
  if (!primary) return null;
  return (
    <section className="source-proof" aria-label="Source of this information">
      <h2>Source of this information</h2>
      <article className="source-proof__primary">
        <p className="source-proof__publisher">{primary.publisher}</p>
        <p className="source-proof__title">{primary.title}</p>
        <span className="source-proof__badge">Official source</span>
        {showExcerpts && <blockquote>{primary.excerpt}</blockquote>}
        <p className="source-proof__freshness">{primary.freshness}</p>
        <a href={primary.url} target="_blank" rel="noreferrer">
          Open official source <ArrowSquareOut size={14} aria-hidden="true" />
        </a>
      </article>
      {rest.length > 0 && (
        <details className="source-proof__more">
          <summary>{rest.length} more source{rest.length === 1 ? "" : "s"}</summary>
          <ol>
            {rest.map((item) => (
              <li key={item.key}>
                <p className="source-proof__origin">
                  <strong>{item.publisher}</strong>
                  <span aria-hidden="true"> · </span>
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title} <ArrowSquareOut size={14} aria-hidden="true" />
                  </a>
                </p>
                {showExcerpts && <blockquote>{item.excerpt}</blockquote>}
                <p className="source-proof__freshness">{item.freshness}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
      {onInspectEvidence && (
        <button type="button" className="source-proof__inspect" onClick={onInspectEvidence}>
          Inspect evidence
        </button>
      )}
    </section>
  );
}
