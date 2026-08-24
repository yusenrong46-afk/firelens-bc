import type { ProofCardView, StatusBannerView } from "./proofPresentation";

function formatClock(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-CA", { timeZone: "America/Vancouver" });
}

export function StatusBanner({
  banner,
}: {
  banner: StatusBannerView;
}) {
  const retrieved = formatClock(banner.retrieval_completed_at);
  const updated = formatClock(banner.source_updated_at);
  const availabilityWarning = banner.availability_label.toLowerCase().includes("unavailable");
  const freshness = banner.freshness_label.toLowerCase();
  const freshnessWarning = freshness.includes("stale") || freshness.includes("mixed");

  return (
    <div className="status-banner" role="status" aria-label="Answer status">
      <strong>{banner.headline}</strong>
      <p>{banner.detail}</p>
      <p>
        <span className={freshnessWarning ? "status-banner__warning" : undefined}>
          Freshness: {banner.freshness_label}
        </span>
        {" · "}
        <span className={availabilityWarning ? "status-banner__warning" : undefined}>
          Availability: {banner.availability_label}
        </span>
      </p>
      {(updated || retrieved) && (
        <p>
          {updated && <span>Official source time {updated}</span>}
          {updated && retrieved && " · "}
          {retrieved && <span>Retrieval time {retrieved}</span>}
        </p>
      )}
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
      <dl>
        <div><dt>Support state</dt><dd>{card.support_state.replaceAll("_", " ")}</dd></div>
        <div><dt>Authority</dt><dd>{card.authority}</dd></div>
        <div><dt>Review state</dt><dd>{card.review_state}</dd></div>
        <div><dt>Critical fields</dt><dd>{card.critical_fields_checked}</dd></div>
        <div><dt>Freshness</dt><dd>{card.freshness}</dd></div>
        {card.source_title && <div><dt>Source</dt><dd>{card.source_title}</dd></div>}
        {card.source_revision && <div><dt>Revision / locator</dt><dd>{card.source_revision}</dd></div>}
      </dl>
      {card.exact_passage && (
        <blockquote>
          <strong>Exact passage</strong>
          <p>{card.exact_passage}</p>
        </blockquote>
      )}
      {card.official_url && (
        <a href={card.official_url} target="_blank" rel="noreferrer">Open official source</a>
      )}
    </article>
  );
}
