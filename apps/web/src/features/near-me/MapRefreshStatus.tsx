import type { LiveMapResponse, LiveResult } from "../../shared/api/api";
import { MAP_REFRESH_MS } from "./useProvinceMap";
import { formatTimestamp, resultDisplayName } from "./liveResultPresentation";

export type MapSnapshotStatus = {
  mode?: "province" | "answer";
  generatedAt?: string | undefined;
  checkedAt?: number | undefined;
  now: number;
  refreshing: boolean;
  error?: string | undefined;
  statuses?: LiveMapResponse["layer_statuses"];
  limitations?: string[] | undefined;
  selectionMessage?: string | undefined;
  onRefresh?: (() => void) | undefined;
};

export function mapSnapshotAge(status: MapSnapshotStatus, results: LiveResult[]) {
  const observations = [
    ...(status.statuses ?? []).filter((layer) => layer.available).map((layer) => layer.retrieved_at),
    ...results.map((result) => result.retrieved_at),
  ];
  const times = observations.map((value) => value ? Date.parse(value) : NaN);
  const known = times.filter(Number.isFinite);
  return {
    oldest: known.length ? Math.min(...known) : undefined,
    unknown: times.length === 0 || times.some((value) => !Number.isFinite(value)),
    overdue: (known.length > 0 && status.now - Math.min(...known) >= MAP_REFRESH_MS)
      || (status.checkedAt !== undefined && status.now - status.checkedAt >= MAP_REFRESH_MS),
  };
}

export function MapRefreshStatus({ status, results }: { status?: MapSnapshotStatus | undefined; results: LiveResult[] }) {
  if (!status) return null;
  const age = mapSnapshotAge(status, results);
  const answerSnapshot = status.mode === "answer";
  const materialLimitations = (status.limitations ?? []).filter((note) => ![
    "Official records can change quickly; confirm emergency directions with the issuing authority.",
    "No matching record is not a safety determination.",
  ].includes(note));
  return <div className="map-refresh-status">
    {answerSnapshot && <p><strong>Answer snapshot</strong> · Records supplied with this answer. Ask again for updated official records.</p>}
    {(status.checkedAt !== undefined || results.length > 0) && (status.error || age.overdue) && <p className="live-map__warning" role="status">
      {answerSnapshot ? "This answer snapshot may be out of date." : status.error ? "Refresh failed. Showing the previously retrieved map snapshot." : "Map snapshot is due for refresh."} These records do not establish current conditions.
    </p>}
    {materialLimitations.map((note) => <p className="live-map__warning" key={note}>{note}</p>)}
    {status.selectionMessage && <p role="status">{status.selectionMessage}</p>}
    <div className="map-refresh-status__check">
      <span>{status.refreshing ? "Refreshing official records…" : age.oldest !== undefined
        ? `Oldest retrieval ${formatTimestamp(new Date(age.oldest).toISOString())}` : "Retrieval time unavailable"}</span>
      {!answerSnapshot && status.onRefresh && <button type="button" onClick={status.onRefresh} disabled={status.refreshing}>{status.error ? "Retry map" : "Refresh map"}</button>}
    </div>
    <details>
      <summary>Source times</summary>
      {status.generatedAt && <p>Response generated {formatTimestamp(status.generatedAt)}</p>}
      {age.unknown && <p>Some retrieval times are unavailable.</p>}
      {(status.statuses ?? []).map((layer) => <p key={layer.kind}>
        <strong>{layer.kind}</strong>: {layer.available ? `Source updated ${layer.source_updated_at ? formatTimestamp(layer.source_updated_at) : "unavailable"} · Retrieved ${layer.retrieved_at ? formatTimestamp(layer.retrieved_at) : "unavailable"} · ${layer.freshness ?? "Freshness unavailable"}` : "Unavailable; no source observation supplied"}
      </p>)}
      {answerSnapshot && results.map((record) => <p key={record.result_id}>
        <strong>{resultDisplayName(record)}</strong>: Source updated {formatTimestamp(record.source_updated_at)} · Retrieved {formatTimestamp(record.retrieved_at)} · {record.freshness} at retrieval
      </p>)}
      <p>Missing records are not an all-clear. Confirm directions with local authorities.</p>
    </details>
  </div>;
}

export function HistoricalMapRecords({ results, selectedId, onSelect }: { results: LiveResult[]; selectedId?: string | undefined; onSelect?: ((id: string) => void) | undefined }) {
  if (!results.length) return null;
  return <details className="map-historical-records">
    <summary>{results.length} earlier answer {results.length === 1 ? "record" : "records"}</summary>
    <p>These answer records are absent from the latest map response. They are excluded from displayed map totals; absence does not establish that an incident ended.</p>
    <ul>{results.map((record) => <li key={record.result_id}>
      <button type="button" aria-pressed={record.result_id === selectedId} onClick={() => onSelect?.(record.result_id)}>{resultDisplayName(record)}</button>
      <span> Retrieved {formatTimestamp(record.retrieved_at)}</span>
    </li>)}</ul>
  </details>;
}
