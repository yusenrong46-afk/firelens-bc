import type { ProofCardView, StatusBannerView } from "./proofPresentation";

export function StatusBanner({
  banner,
}: {
  banner: StatusBannerView;
}) {
  const availability = banner.availability_label.toLowerCase();
  const availabilityWarning = availability.includes("unavailable")
    || availability.includes("did not complete")
    || availability.includes("not established");
  const freshness = banner.freshness_label.toLowerCase();
  const freshnessWarning = freshness.includes("stale") || freshness.includes("mixed");

  return (
    <div className="status-banner" role="status" aria-label="Answer status">
      <div className="status-banner__summary">
        <strong>{banner.headline}</strong>
        <p>{banner.detail}</p>
      </div>
      <div className="status-banner__metadata">
        <span className={freshnessWarning ? "status-banner__warning" : undefined}>
          <strong>Freshness:</strong> {banner.freshness_label}
        </span>
        {availabilityWarning && (
          <span className="status-banner__warning"><strong>Availability:</strong> {banner.availability_label}</span>
        )}
      </div>
      {banner.official_escalation_url && (
        <a href={banner.official_escalation_url} target="_blank" rel="noreferrer">
          {banner.official_escalation_title ?? "Open official source"}
        </a>
      )}
    </div>
  );
}

export function ProofCard({ card }: { card: ProofCardView }) {
  return (
    <article className="proof-card" aria-label={`Proof card for ${card.claim_text}`}>
      {(card.conflicts_or_unknowns ?? []).length > 0 && (
        <div className="proof-card__warnings" role="status">
          <strong>Warnings before details</strong>
          <ul>
            {(card.conflicts_or_unknowns ?? []).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
      <p className="proof-card__state">{card.support_label}</p>
      <h2>{card.claim_text}</h2>
      {card.exact_passage && (
        <blockquote>
          <strong>Exact passage</strong>
          <p>{card.exact_passage}</p>
        </blockquote>
      )}
      {card.official_url && (
        <a href={card.official_url} target="_blank" rel="noreferrer">Open official source</a>
      )}
      <details className="proof-card__technical">
        <summary>Technical binding details</summary>
        <dl>
          <div><dt>Support state</dt><dd>{card.support_state.replaceAll("_", " ")}</dd></div>
          <div><dt>Authority</dt><dd>{card.authority}</dd></div>
          <div><dt>Review state</dt><dd>{card.review_state}</dd></div>
          <div><dt>Critical fields</dt><dd>{card.critical_fields_checked}</dd></div>
          <div><dt>Freshness</dt><dd>{card.freshness}</dd></div>
          {card.source_title && <div><dt>Source</dt><dd>{card.source_title}</dd></div>}
          {card.source_revision && <div><dt>Revision / locator</dt><dd>{card.source_revision}</dd></div>}
        </dl>
      </details>
    </article>
  );
}
