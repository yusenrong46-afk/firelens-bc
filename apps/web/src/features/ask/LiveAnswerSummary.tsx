import { ArrowRight, ArrowSquareOut, CaretRight, Clock, Database, Fire, MapPin, Stack } from "@phosphor-icons/react";
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

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function recordSummary(results: LiveResult[], rosterTotal: number): {
  headlineCount: number;
  headlineNoun: string;
  detail?: string;
} {
  if (rosterTotal > results.length) {
    return {
      headlineCount: rosterTotal,
      headlineNoun: rosterTotal === 1 ? "official record" : "official records",
      detail: `Showing ${plural(results.length, "returned record")}; a wildfire total is not inferred from a partial roster`,
    };
  }

  let incidentCount = 0;
  let perimeterCount = 0;
  let evacuationCount = 0;
  const wildfireIds = new Set<string>();
  let allWildfireRowsHaveIncidentIdentity = true;
  for (const item of results) {
    if (item.kind === "incident") incidentCount += 1;
    else if (item.kind === "perimeter") perimeterCount += 1;
    else evacuationCount += 1;
    if (item.kind !== "evacuation") {
      const incidentIdentity = item.incident_number?.trim();
      if (incidentIdentity) wildfireIds.add(incidentIdentity.toLocaleLowerCase("en-CA"));
      else allWildfireRowsHaveIncidentIdentity = false;
    }
  }
  const onlyWildfireRecords = evacuationCount === 0
    && incidentCount + perimeterCount === results.length;
  const onlyEvacuationRecords = evacuationCount === results.length;

  if (onlyWildfireRecords && allWildfireRowsHaveIncidentIdentity) {
    const headlineCount = wildfireIds.size || rosterTotal;
    const breakdown = [
      incidentCount > 0 ? plural(incidentCount, "incident record") : undefined,
      perimeterCount > 0 ? plural(perimeterCount, "mapped perimeter") : undefined,
    ].filter((item): item is string => Boolean(item));
    const summary = {
      headlineCount,
      headlineNoun: headlineCount === 1 ? "wildfire" : "wildfires",
    };
    return rosterTotal !== headlineCount && breakdown.length > 0
      ? { ...summary, detail: `${plural(rosterTotal, "official record")}: ${breakdown.join(" and ")}` }
      : summary;
  }

  if (onlyWildfireRecords) {
    const breakdown = [
      incidentCount > 0 ? plural(incidentCount, "incident record") : undefined,
      perimeterCount > 0 ? plural(perimeterCount, "mapped perimeter") : undefined,
    ].filter((item): item is string => Boolean(item));
    return {
      headlineCount: rosterTotal,
      headlineNoun: rosterTotal === 1 ? "official record" : "official records",
      detail: `${breakdown.join(" and ")}; a wildfire total is not inferred without incident identities`,
    };
  }

  if (onlyEvacuationRecords) {
    return {
      headlineCount: rosterTotal,
      headlineNoun: rosterTotal === 1 ? "official evacuation record" : "official evacuation records",
    };
  }

  return {
    headlineCount: rosterTotal,
    headlineNoun: rosterTotal === 1 ? "official record" : "official records",
  };
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
  const place = placeName?.trim();
  const radius = typeof radiusKm === "number" ? Math.round(radiusKm) : undefined;
  const summary = recordSummary(results, rosterTotal);
  const completeWildfireRoster = rosterTotal <= sampled.length
    && results.every((item) => item.kind !== "evacuation" && Boolean(item.incident_number?.trim()));
  const internalMapLabel = rosterTotal > sampled.length
    ? `View all ${rosterTotal} matching records`
    : completeWildfireRoster
      ? "View all fires on the map"
      : "View all matching records on the map";

  const headline = place && radius != null
    ? `${summary.headlineCount} ${summary.headlineNoun} found within ${radius} km of ${place}`
    : place
      ? `${summary.headlineCount} ${summary.headlineNoun} found near ${place}`
      : `${summary.headlineCount} ${summary.headlineNoun} found`;

  return (
    <div className="live-answer-summary" role="region" aria-label="Live answer summary">
      <header className="live-answer-summary__header">
        <h2 className="live-answer-summary__headline"><Stack size={22} aria-hidden="true" />{headline}</h2>
      {(onOpenMap || completeWildfireRoster) && (
        <div className="live-answer-summary__map">
          {onOpenMap ? (
          <button type="button" className="live-answer-map-link" aria-label={`View map — ${internalMapLabel}`} onClick={onOpenMap}>
            View map
            <ArrowRight size={16} aria-hidden="true" />
          </button>
          ) : (
            <a className="live-answer-map-link" href={BCWS_MAP_URL} target="_blank" rel="noreferrer">
              View all fires on the map <ArrowRight size={16} aria-hidden="true" />
            </a>
          )}
        </div>
      )}
        {summary.detail && (rosterTotal > results.length ? <p className="live-answer-summary__fresh-warning">{summary.detail}</p> : <details className="live-answer-coverage">
          <summary>Record coverage</summary><p>{summary.detail}</p>
        </details>)}
        {freshnessWarning && (
          <p className="live-answer-summary__fresh-warning" role="status">
            Official data may be delayed or partially cached. Confirm with the source.
          </p>
        )}
      </header>

      <div className="live-answer-records">
        <article className={`live-answer-lead${selectedResultId === lead.result_id ? " live-answer-lead--selected" : ""}`}>
          <RecordRow result={lead} selected={selectedResultId === lead.result_id} onSelect={onSelectResult} />
        </article>
        {secondary.length > 0 && <ul className="live-answer-secondary" aria-label="Additional matching records">
          {secondary.map((result) => <li key={result.result_id}>
            <RecordRow result={result} selected={selectedResultId === result.result_id} onSelect={onSelectResult} />
          </li>)}
        </ul>}
      </div>


    </div>
  );
}

function RecordRow({ result, selected, onSelect }: {
  result: LiveResult;
  selected: boolean;
  onSelect?: ((resultId: string) => void) | undefined;
}) {
  const status = resultStatus(result);
  return <div className={`live-record-row${selected ? " live-record-row--selected" : ""}`}>
    <button type="button" className={`live-record-select${selected ? " is-selected" : ""}`}
      aria-pressed={selected} onClick={() => onSelect?.(result.result_id)}>
      <span className={`live-record-icon status-pill--${statusTone(status)}`}>
        {result.kind === "incident" ? <Fire size={25} aria-hidden="true" /> : <Stack size={24} aria-hidden="true" />}
      </span>
      <span className="live-record-content">
        <span className="live-record-title"><strong>{resultDisplayName(result)}</strong><StatusPill status={status} /></span>
        <span className="live-record-location"><MapPin size={15} aria-hidden="true" />
          {result.distance_km != null ? `${result.distance_km.toFixed(1)} km away` : result.fire_centre || "Location as published by the official source"}
        </span>
        {(result.size_hectares != null || result.incident_number) && <span className="live-record-facts">
          {result.size_hectares != null && <span>Size {result.size_hectares} ha</span>}
          {result.incident_number && <span>Incident {result.incident_number}</span>}
        </span>}
      </span>
      <CaretRight className="live-record-caret" size={16} aria-hidden="true" />
    </button>
    <div className="live-record-source">
      <a href={result.source_url} target="_blank" rel="noreferrer">{result.authority} <ArrowSquareOut size={14} aria-hidden="true" /></a>
      <span>{relativeMinutes(result.source_updated_at ?? undefined) ?? "Update time not published"}</span>
    </div>
  </div>;
}

export function LiveSourceLine({ results }: { results: LiveResult[] }) {
  const stamp = latestStamp(results);
  return <div className="live-source-line" aria-label="Answer sources and update time">
    <span><Database size={18} aria-hidden="true" />{provenance(results)}</span>
    <span><Clock size={18} aria-hidden="true" />{stamp ? `Latest source update ${formatTimestamp(stamp)}` : "Update time not published"}</span>
  </div>;
}
