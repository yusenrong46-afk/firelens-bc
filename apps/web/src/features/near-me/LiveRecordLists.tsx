import { useEffect, useMemo, useState } from "react";
import type { LiveResult } from "../../shared/api/api";
import {
  formatTimestamp,
  interleaveByKind,
  resultDisplayName,
  resultKindLabel,
  resultStatus,
  sourceLinkLabel,
} from "./liveResultPresentation";

const INITIAL_LIST_LIMIT = 12;
const INITIAL_MATCHING_LIMIT = 6;

function RecordRow({
  result,
  selectedResultId,
  onSelectResult,
}: {
  result: LiveResult;
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
}) {
  const displayName = resultDisplayName(result);
  const status = resultStatus(result);
  const sourceLabel = sourceLinkLabel(result);
  return (
    <li className={result.result_id === selectedResultId ? "live-list__selected" : ""}>
      <span className={`live-dot live-dot--${result.kind}`} aria-hidden="true" />
      <button
        type="button"
        className="live-list__select"
        onClick={() => onSelectResult?.(result.result_id)}
        aria-label={`${displayName} ${status} ${resultKindLabel(result.kind)}, source updated ${formatTimestamp(result.source_updated_at)}`}
      >
        <strong>{displayName}</strong>
        <small>{status} · {result.freshness} · {result.authority}</small>
        <small>Source updated {formatTimestamp(result.source_updated_at)}</small>
        <small>Retrieved {formatTimestamp(result.retrieved_at)}</small>
        {result.distance_km != null && (
          <small>{result.distance_km.toFixed(1)} km · {result.distance_basis?.replaceAll("_", " ")}</small>
        )}
      </button>
      <a
        href={result.source_url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Open ${sourceLabel} for ${displayName}, record ${result.result_id}`}
      >
        {sourceLabel}
      </a>
    </li>
  );
}

export function MatchingRecordList({
  results,
  selectedResultId,
  onSelectResult,
}: {
  results: LiveResult[];
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
}) {
  const [showAll, setShowAll] = useState(false);
  const signature = results.map((result) => result.result_id).join("|");
  useEffect(() => setShowAll(false), [signature]);
  const visibleResults = useMemo(() => {
    if (showAll || results.length <= INITIAL_MATCHING_LIMIT) return results;
    const initial = results.slice(0, INITIAL_MATCHING_LIMIT);
    const selected = selectedResultId
      ? results.find((result) => result.result_id === selectedResultId)
      : undefined;
    if (!selected || initial.some((result) => result.result_id === selected.result_id)) return initial;
    return [selected, ...initial.slice(0, INITIAL_MATCHING_LIMIT - 1)];
  }, [results, selectedResultId, showAll]);
  if (results.length === 0) return null;
  return (
    <div className="live-matches">
      <h2 className="live-list-heading">Matching this question</h2>
      <ul className="live-list" aria-label="Matching this question">
        {visibleResults.map((result) => (
          <RecordRow
            key={result.result_id}
            result={result}
            selectedResultId={selectedResultId}
            onSelectResult={onSelectResult}
          />
        ))}
      </ul>
      {results.length > INITIAL_MATCHING_LIMIT && (
        <button
          type="button"
          className="live-list-toggle"
          onClick={() => setShowAll((current) => !current)}
          aria-expanded={showAll}
        >
          {showAll ? "Show fewer matching records" : `Show all ${results.length} matching records`}
        </button>
      )}
    </div>
  );
}

export function ProvinceRecordList({
  results,
  hasMatchingResults,
  selectedResultId,
  onSelectResult,
}: {
  results: LiveResult[];
  hasMatchingResults: boolean;
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
}) {
  const [showAll, setShowAll] = useState(false);
  const orderedResults = useMemo(() => interleaveByKind(results), [results]);
  const signature = orderedResults.map((result) => result.result_id).join("|");
  useEffect(() => setShowAll(false), [signature]);
  const initialResults = useMemo(() => {
    if (showAll || orderedResults.length <= INITIAL_LIST_LIMIT) return orderedResults;
    const initial = orderedResults.slice(0, INITIAL_LIST_LIMIT);
    const selected = selectedResultId
      ? orderedResults.find((result) => result.result_id === selectedResultId)
      : undefined;
    if (!selected || initial.some((result) => result.result_id === selected.result_id)) return initial;
    return [selected, ...initial.slice(0, INITIAL_LIST_LIMIT - 1)];
  }, [orderedResults, selectedResultId, showAll]);
  if (orderedResults.length === 0) return null;
  const listVisible = !hasMatchingResults || showAll;
  const toggleVisible = hasMatchingResults || orderedResults.length > INITIAL_LIST_LIMIT;
  return (
    <>
      <h2 className="live-list-heading">Rest of B.C.</h2>
      {listVisible && (
        <ul className="live-list" aria-label="Rest of B.C.">
          {initialResults.map((result) => (
            <RecordRow
              key={result.result_id}
              result={result}
              selectedResultId={selectedResultId}
              onSelectResult={onSelectResult}
            />
          ))}
        </ul>
      )}
      {toggleVisible && (
        <button
          type="button"
          className="live-list-toggle"
          onClick={() => setShowAll((current) => !current)}
          aria-expanded={showAll}
        >
          {showAll
            ? "Show fewer records"
            : hasMatchingResults
              ? `Show rest of B.C. (${orderedResults.length} records)`
              : `Show all ${orderedResults.length} official records`}
        </button>
      )}
    </>
  );
}
