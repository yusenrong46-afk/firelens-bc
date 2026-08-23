import { useState, type ReactNode } from "react";
import {
  ArrowSquareOut,
  CaretDown,
  CaretUp,
} from "@phosphor-icons/react";
import type { AskResponse, LiveResult } from "../../shared/api/api";
import type { SupportState } from "../ask/proofPresentation";
import type { Evidence, Support } from "../ask/responseModel";

type RelatedLink = NonNullable<AskResponse["related_links"]>[number];

export function mapResultLinkText(item: LiveResult): string {
  const fallback = item.name || item.incident_number || "Official wildfire record";
  return /(?:featureserver|mapserver|arcgis)/i.test(item.source_url)
    ? `GIS dataset — ${fallback}`
    : fallback;
}

function HighlightedPassage({ text, quote }: { text: string; quote: string }) {
  const start = text.indexOf(quote);
  if (start < 0) return <p>{text}</p>;
  return (
    <p>
      {text.slice(0, start)}
      <mark>{quote}</mark>
      {text.slice(start + quote.length)}
    </p>
  );
}

export function SourcePanel({
  evidence,
  support,
  index,
  initiallyOpen,
  supportState,
}: {
  evidence: Evidence;
  support: Support;
  index: number;
  initiallyOpen: boolean;
  supportState: SupportState;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const quoteOnly = supportState === "official_quote_only";
  return (
    <article className="source-panel">
      <div className="source-panel__head">
        <button type="button" className="source-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="source-number">{index + 1}</span>
          <span className="source-name">
            <strong>{evidence.title}</strong>
            <small>{evidence.locator || (quoteOnly ? "Exact source passage" : "Reviewed source passage")}</small>
          </span>
        </button>
        <span className="stable-chip">{quoteOnly ? "Stable source wording" : "Stable guidance"}</span>
        <a href={evidence.canonical_url} target="_blank" rel="noreferrer">
          View source <ArrowSquareOut size={15} />
        </a>
        <button
          type="button"
          className="caret-button"
          onClick={() => setOpen(!open)}
          aria-label={open ? `Collapse source ${index + 1}` : `Expand source ${index + 1}`}
        >
          {open ? <CaretUp /> : <CaretDown />}
        </button>
      </div>
      {open && (
        <div className="source-panel__body">
          <aside className="source-details">
            <dl>
              <div><dt>Publisher</dt><dd>{evidence.publisher}</dd></div>
              <div><dt>Document</dt><dd>{evidence.title}</dd></div>
              <div><dt>Locator</dt><dd>{evidence.locator || "Source passage"}</dd></div>
              <div><dt>Guidance type</dt><dd>{quoteOnly ? "Source extraction only" : "Stable preparedness guidance"}</dd></div>
              {evidence.review_provenance === "human_verified_repair" && (
                <div><dt>Text review</dt><dd>Human-verified source transcription</dd></div>
              )}
            </dl>
            <div className="canonical">
              <strong>Canonical source</strong>
              <a href={evidence.canonical_url} target="_blank" rel="noreferrer">
                Open official page <ArrowSquareOut size={13} />
              </a>
            </div>
          </aside>
          <div className="passage">
            <h2>Source passage</h2>
            <HighlightedPassage text={evidence.context_text} quote={support.quote} />
          </div>
        </div>
      )}
    </article>
  );
}

export function EvidencePlaceholder({
  icon,
  title,
  children,
  links = [],
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  links?: RelatedLink[] | undefined;
}) {
  return (
    <div className="evidence-placeholder">
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{children}</p>
      {links.length > 0 && (
        <div className="related-service-links evidence-placeholder__links" aria-label="Related official sources for this boundary">
          {links.map((item) => (
            <a
              key={item.url}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${item.title} from the answer context`}
            >
              <span><strong>{item.title}</strong><small>{item.description}</small></span>
              <ArrowSquareOut size={18} aria-hidden="true" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
