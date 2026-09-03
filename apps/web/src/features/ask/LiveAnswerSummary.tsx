import { ArrowRight, CaretRight } from "@phosphor-icons/react";
import type { AskResponse, LiveResult } from "../../shared/api/api";
import { BCWS_MAP_URL } from "../../shared/officialLinks";
import {
  formatTimestamp,
  resultDisplayName,
  resultStatus,
} from "../near-me/liveResultPresentation";

function latestStamp(results: LiveResult[]): string | undefined {
  return results
    .map((item) => item.source_updated_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
}

function provenance(results: LiveResult[]): string {
  const authorities = [...new Set(results.map((item) => item.authority.trim()).filter(Boolean))];
  if (authorities.length === 0) return "Official source not named";
  if (authorities.length === 1) return authorities[0]!;
  if (authorities.length === 2) return authorities.join(" and ");
  return `${authorities.slice(0, 2).join(", ")}, and other official authorities`;
}

function relativeMinutes(iso: string | undefined): string | undefined {
  if (!iso) return undefined;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return undefined;
  const minutes = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 60_000));
  if (minutes < 1) return "Updated just now";
  if (minutes === 1) return "Updated 1 minute ago";
  if (minutes < 60) return `Updated ${minutes} minutes ago`;
  return `Updated ${formatTimestamp(iso)}`;
}

function statusTone(status: string): "ooc" | "held" | "uc" | "out" | "unknown" {
  const normalized = status.toLowerCase();
  if (normalized.includes("out of control")) return "ooc";
  if (normalized.includes("being held") || normalized.includes("held")) return "held";
  if (normalized.includes("under control")) return "uc";
  if (normalized === "out" || normalized.includes("extinguished")) return "out";
  return "unknown";
}

function StatusPill({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <span className={`status-pill status-pill--${tone}`}>
      <span className="response-announcement">Status</span>
      {status}
    </span>
  );
}

function sampledResults(response: AskResponse): LiveResult[] {
  const results = response.live_results ?? [];
  const sampleIds = response.sample_record_ids ?? [];
  if (sampleIds.length === 0) return results;
  return sampleIds
    .map((resultId) => results.find((item) => item.result_id === resultId))
    .filter((item): item is LiveResult => item != null);
}

export function LiveAnswerSummary({
  onSelectResult,
  onOpenMap,
  placeName,
  radiusKm,
  response,
  selectedResultId,
}: {
  onSelectResult?: ((resultId: string) => void) | undefined;
  onOpenMap?: (() => void) | undefined;
  placeName?: string | undefined;
  radiusKm?: number | undefined;
  response: AskResponse;
  selectedResultId?: string | undefined;
}) {
  const results = response.live_results ?? [];
  if (results.length === 0) return null;
  const freshnessWarning = response.aggregate_freshness === "stale"
    || response.aggregate_freshness === "mixed";
  const sampled = sampledResults(response);
  const lead = sampled[0] ?? results[0]!;
  const secondary = sampled.slice(1, 4);
  const rosterTotal = response.roster_total ?? results.length;
  const stamp = latestStamp(results);
  const updateLabel = relativeMinutes(stamp);
  const place = placeName?.trim();
  const radius = typeof radiusKm === "number" ? Math.round(radiusKm) : undefined;

  const headline = place && radius != null
    ? `${rosterTotal} active wildfire${rosterTotal === 1 ? "" : "s"} found within ${radius} km of ${place}`
    : place
      ? `${rosterTotal} active wildfire${rosterTotal === 1 ? "" : "s"} found near ${place}`
      : rosterTotal === 1
        ? "1 official record found"
        : `${rosterTotal} official records found`;

  return (
    <div className="live-answer-summary" role="region" aria-label="Live answer summary">
      <header className="live-answer-summary__header">
        <h2 className="live-answer-summary__headline">{headline}</h2>
        <p className="live-answer-summary__subline">
          {provenance(results)}
          {updateLabel ? ` · ${updateLabel}` : " · update time not published"}
        </p>
        {freshnessWarning && (
          <p className="live-answer-summary__fresh-warning" role="status">
            Official data may be delayed or partially cached. Confirm with the source.
          </p>
        )}
      </header>

      <article
        className={`live-answer-lead${selectedResultId === lead.result_id ? " live-answer-lead--selected" : ""}`}
      >
        <button type="button" onClick={() => onSelectResult?.(lead.result_id)}>
          <div className="live-answer-lead__top">
            <div>
              <strong>{resultDisplayName(lead)}</strong>
              {(lead.incident_number || lead.result_id) && (
                <small className="live-answer-lead__id">
                  {lead.incident_number?.trim() || lead.result_id}
                </small>
              )}
              <p className="live-answer-lead__where">
                {lead.distance_km != null
                  ? `${lead.distance_km.toFixed(1)} km away`
                  : lead.fire_centre
                    ? lead.fire_centre
                    : "Location as published by the official source"}
              </p>
            </div>
            <StatusPill status={resultStatus(lead)} />
          </div>
          <dl className="live-answer-metrics">
            {lead.size_hectares != null && (
              <div>
                <dt>Size</dt>
                <dd>{lead.size_hectares} ha</dd>
              </div>
            )}
            {lead.distance_km != null && (
              <div>
                <dt>Distance</dt>
                <dd>{lead.distance_km.toFixed(1)} km</dd>
              </div>
            )}
            {lead.source_updated_at && (
              <div>
                <dt>Updated</dt>
                <dd>{formatTimestamp(lead.source_updated_at)}</dd>
              </div>
            )}
          </dl>
        </button>
      </article>

      {secondary.length > 0 && (
        <ul className="live-answer-secondary" aria-label="Additional matching records">
          {secondary.map((result) => (
            <li key={result.result_id}>
              <button
                type="button"
                className={selectedResultId === result.result_id ? "is-selected" : undefined}
                onClick={() => onSelectResult?.(result.result_id)}
              >
                <span className="live-answer-secondary__name">
                  <strong>{resultDisplayName(result)}</strong>
                  <small>
                    <StatusPill status={resultStatus(result)} />
                    {result.size_hectares != null ? ` · ${result.size_hectares} ha` : ""}
                    {result.distance_km != null ? ` · ${result.distance_km.toFixed(1)} km` : ""}
                    {result.source_updated_at ? ` · ${formatTimestamp(result.source_updated_at)}` : ""}
                  </small>
                </span>
                <CaretRight size={18} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="live-answer-summary__footer">
        {onOpenMap ? (
          <button type="button" className="live-answer-map-link" onClick={onOpenMap}>
            {rosterTotal > sampled.length
              ? `View all ${rosterTotal} matching records`
              : "View all fires on the map"}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        ) : (
          <a className="live-answer-map-link" href={BCWS_MAP_URL} target="_blank" rel="noreferrer">
            View all fires on the map <ArrowRight size={16} aria-hidden="true" />
          </a>
        )}
      </div>
    </div>
  );
}
