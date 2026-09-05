import { ArrowSquareOut, Database, Info } from "@phosphor-icons/react";
import type { AskResponse, LiveResult } from "../shared/api/api";
import { formatTimestamp, resultDisplayName } from "../features/near-me/liveResultPresentation";
import { EMERGENCY_INFO_BC_URL } from "../shared/officialLinks";

export function OfficialSourcesCard({ response, selectedResultId, selectedRecord }: {
  response?: AskResponse | undefined;
  selectedResultId?: string | undefined;
  selectedRecord?: LiveResult | undefined;
}) {
  const records = response?.live_results ?? [];
  const record = selectedResultId
    ? selectedRecord ?? records.find((item) => item.result_id === selectedResultId)
    : records[0];
  const sources = [...new Map(records.map((item) => [item.source_url, item])).values()];
  const additionalSources = record ? sources.filter((item) => item.source_url !== record.source_url) : [];
  const unavailable = response?.unavailable_layers ?? [];
  return (
    <aside className="official-sources-card" aria-label="Official sources">
      <div className="official-sources-card__title">
        <Database size={21} aria-hidden="true" />
        <h2>{response ? "Source & freshness" : "Official updates"}</h2>
      </div>
      {record && <>
        <p className="official-sources-card__scope">For {resultDisplayName(record)} <span><span className="response-announcement">Record freshness: </span>{record.freshness === "fresh" ? "Current at retrieval" : record.freshness === "stale" ? "Stale record" : "Freshness unknown"}</span></p>
        <dl>
          <div><dt>Published by</dt><dd><a href={record.source_url} target="_blank" rel="noreferrer">{record.authority} <ArrowSquareOut size={14} aria-hidden="true" /></a></dd></div>
          <div><dt>Source updated</dt><dd>{record.source_updated_at ? formatTimestamp(record.source_updated_at) : "Not published"}</dd></div>
          <div><dt>FireLens fetched</dt><dd>{formatTimestamp(record.retrieved_at)}</dd></div>
        </dl>
      </>}
      {unavailable.length > 0 && <p className="official-sources-card__warning">Unavailable layers: {unavailable.join(", ")}. Returned records do not cover those layers.</p>}
      {!record && response && <p>{response.status_banner?.availability_label || "No current records supplied with this answer."}</p>}
      <div className="official-sources-card__footer">

      <div className="official-sources-card__note"><Info size={18} aria-hidden="true" /><div><p>Confirm critical decisions with local authorities and current official updates.</p>
        <a href={EMERGENCY_INFO_BC_URL} target="_blank" rel="noreferrer">EmergencyInfoBC <ArrowSquareOut size={14} aria-hidden="true" /></a>
        {additionalSources.length > 0 && <details className="official-sources-card__more"><summary>Other sources ({additionalSources.length})</summary>{additionalSources.map((item) => (
          <a className="official-sources-card__additional" key={item.source_url} href={item.source_url} target="_blank" rel="noreferrer">Also used: {item.authority} <ArrowSquareOut size={14} aria-hidden="true" /></a>
        ))}</details>}
      </div></div>
      </div>
    </aside>
  );
}
