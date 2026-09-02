import type { AskResponse, LiveResult } from "../../shared/api/api";
import {
  resultDisplayName,
  resultStatus,
} from "../near-me/liveResultPresentation";

const BCWS_MAP_URL = "https://wildfiresituation.nrs.gov.bc.ca/map";

const EVAC_INFO_URL = "https://www.emergencyinfobc.gov.bc.ca/";

function latestStamp(results: LiveResult[]): string | undefined {
  return results
    .map((item) => item.source_updated_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
}

function provenance(results: LiveResult[]): string {
  const authorities = [...new Set(results.map((item) => item.authority.trim()).filter(Boolean))];
  if (authorities.length === 0) return "Official source authority not supplied";
  if (authorities.length === 1) return authorities[0]!;
  if (authorities.length === 2) return authorities.join(" and ");
  return `${authorities.slice(0, 2).join(", ")}, and other official authorities`;
}

export function LiveAnswerSummary({
  onSelectResult,
  response,
}: {
  onSelectResult?: ((resultId: string) => void) | undefined;
  response: AskResponse;
}) {
  const results = response.live_results ?? [];
  if (results.length === 0) return null;
  const freshnessWarning = response.aggregate_freshness === "stale"
    || response.aggregate_freshness === "mixed";
  const sampleIds = response.sample_record_ids ?? [];
  const sampled = sampleIds.length
    ? sampleIds
      .map((resultId) => results.find((item) => item.result_id === resultId))
      .filter((item): item is LiveResult => item != null)
    : results.slice(0, 8);
  const top = sampled.slice(0, 8);
  const rosterTotal = response.roster_total ?? results.length;
  return (
    <div className="live-answer-summary" aria-label="Live answer summary">
      <p className="live-answer-summary__place">
        <strong>Official records returned</strong>
        {" · "}
        {rosterTotal} {rosterTotal === 1 ? "record" : "records"}
        {rosterTotal > top.length ? ` · priority sample of ${top.length}` : ""}
      </p>
      {!freshnessWarning && (
        <p className="live-answer-summary__fresh">
          {provenance(results)}
          {latestStamp(results) ? ` · source updated ${latestStamp(results)}` : " · source update time not supplied"}
        </p>
      )}
      <ul className="live-answer-summary__records" aria-label="Top matching records">
        {top.map((result) => (
          <li key={result.result_id}>
            <button type="button" onClick={() => onSelectResult?.(result.result_id)}>
              <strong>{resultDisplayName(result)}</strong>
              <small>
                {resultStatus(result)}
                {result.distance_km != null ? ` · ${result.distance_km.toFixed(1)} km` : ""}
              </small>
            </button>
          </li>
        ))}
      </ul>
      <p className="live-answer-summary__links">
        <a href={BCWS_MAP_URL} target="_blank" rel="noreferrer">BCWS map</a>
        <a href={EVAC_INFO_URL} target="_blank" rel="noreferrer">Evacuations</a>
      </p>
    </div>
  );
}
