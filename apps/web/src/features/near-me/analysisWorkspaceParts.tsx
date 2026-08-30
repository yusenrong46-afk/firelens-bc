import { useState } from "react";
import type { LiveResult } from "../../shared/api/api";
import { RecordRow } from "./LiveRecordLists";
import {
  availableAnalysisSorts,
  type AnalysisSort,
  type LiveAnalysis,
} from "./liveAnalysis";
import { formatTimestamp } from "./liveResultPresentation";

export function joinAnalysisLabels(labels: string[]): string {
  if (labels.length < 2) return labels[0] ?? "";
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels.at(-1)}`;
}

export function RecordsView({ results, totalResults }: { results: LiveResult[]; totalResults: number }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? results : results.slice(0, 18);
  return (
    <section className="analysis-records" aria-label="Incident records returned for this request">
      <div className="analysis-records__heading">
        <div><h3>Incident records returned for this request</h3><p>{results.length} of {totalResults} records shown</p></div>
        {results.length > 18 && <button type="button" onClick={() => setShowAll((current) => !current)} aria-expanded={showAll}>{showAll ? "Show fewer" : `Show all ${results.length}`}</button>}
      </div>
      <ul>{visible.map((result) => <RecordRow key={result.result_id} result={result} variant="analysis" />)}</ul>
    </section>
  );
}

export function AnalysisFilters({
  results,
  fireCentre,
  status,
  sort,
  onFireCentre,
  onStatus,
  onSort,
}: {
  results: LiveResult[];
  fireCentre: string;
  status: string;
  sort: AnalysisSort;
  onFireCentre: (value: string) => void;
  onStatus: (value: string) => void;
  onSort: (value: AnalysisSort) => void;
}) {
  const centres = Array.from(new Set(results.map((result) => result.fire_centre?.trim()).filter(Boolean) as string[])).sort();
  const statuses = Array.from(new Set(results.map((result) => result.status?.trim()).filter(Boolean))).sort();
  const sorts = availableAnalysisSorts(results);
  if (results.length <= 12) return null;
  return (
    <div className="analysis-filters" aria-label="Filter incident records">
      <label>Fire centre<select value={fireCentre} onChange={(event) => onFireCentre(event.target.value)}><option value="">All fire centres</option>{centres.map((value) => <option key={value} value={value}>{value.replace(/\s+Fire\s+Centre$/i, "")}</option>)}</select></label>
      <label>Status<select value={status} onChange={(event) => onStatus(event.target.value)}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Sort<select value={sort} onChange={(event) => onSort(event.target.value as AnalysisSort)}><option value="default">Original order</option>{sorts.includes("newest") && <option value="newest">Newest source update</option>}{sorts.includes("largest") && <option value="largest">Largest first</option>}{sorts.includes("nearest") && <option value="nearest">Nearest first</option>}</select></label>
    </div>
  );
}

export function AnalysisKpis({ results, analysis }: { results: LiveResult[]; analysis: LiveAnalysis }) {
  const newest = results.map((result) => result.source_updated_at).map((value) => ({ value, time: Date.parse(value) })).filter(({ time }) => Number.isFinite(time)).sort((left, right) => right.time - left.time).at(0)?.value;
  const reportedStatuses = analysis.byStatus.filter((row) => row.label !== "Not reported");
  const dominantCount = reportedStatuses[0]?.count;
  const dominantStatuses = dominantCount === undefined ? [] : reportedStatuses.filter((row) => row.count === dominantCount);
  return (
    <dl className="analysis-kpis" aria-label="Incident record summary">
      <div><dt>Incident records</dt><dd>{results.length}</dd></div>
      <div><dt>Leading fire centre</dt><dd>{analysis.highestFireCentre?.label?.replace(/\s+Fire\s+Centre$/i, "") ?? "Tie or unavailable"}</dd></div>
      <div><dt>Dominant status</dt><dd>{dominantStatuses.length === 1 ? dominantStatuses[0]?.label : dominantStatuses.length > 1 ? "Tie" : "Unavailable"}</dd></div>
      <div><dt>Newest source update</dt><dd>{newest ? formatTimestamp(newest) : "Unavailable"}</dd></div>
    </dl>
  );
}
