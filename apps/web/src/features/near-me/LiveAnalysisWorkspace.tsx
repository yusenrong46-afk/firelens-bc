import { ChartBar, Database, ListBullets, MapTrifold, ShieldCheck } from "@phosphor-icons/react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { LiveResult } from "../../shared/api/api";
import type { FireLensSession } from "../ask/useFireLensSession";
import { EvidencePlaceholder } from "../evidence/evidencePresentation";
import { buildLiveAnalysis, type AnalysisCount } from "./liveAnalysis";
import { formatTimestamp, resultDisplayName, sourceLinkLabel } from "./liveResultPresentation";

const LiveMap = lazy(() => import("./LiveMap").then((module) => ({ default: module.LiveMap })));

type AnalysisSurface = "summary" | "map" | "records";

function CountTable({ title, rows }: { title: string; rows: AnalysisCount[] }) {
  const maximum = Math.max(1, ...rows.map((row) => row.count));
  return (
    <section className="analysis-breakdown" aria-label={title}>
      <div className="analysis-breakdown__heading">
        <h3>{title}</h3>
      </div>
      <ol>
        {rows.length === 0 && <li className="analysis-empty">This field was not available in the returned records.</li>}
        {rows.map((row, index) => (
          <li key={row.label}>
            <span className="analysis-rank" aria-hidden="true">{index + 1}</span>
            <span className="analysis-label">{row.label}</span>
            <span className="analysis-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(4, (row.count / maximum) * 100)}%` }} />
            </span>
            <strong>{row.count}</strong>
            <small>{Math.round(row.share * 100)}%</small>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecordsView({ results }: { results: LiveResult[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? results : results.slice(0, 18);
  return (
    <section className="analysis-records" aria-label="Incident records returned for this request">
      <div className="analysis-records__heading">
        <div><h3>Incident records returned for this request</h3><p>{results.length} records in this answer</p></div>
        {results.length > 18 && (
          <button type="button" onClick={() => setShowAll((current) => !current)} aria-expanded={showAll}>
            {showAll ? "Show fewer" : `Show all ${results.length}`}
          </button>
        )}
      </div>
      <ul>
        {visible.map((result) => (
          <li key={result.result_id}>
            <div>
              <strong>{resultDisplayName(result)}</strong>
              <span>{result.fire_centre ?? "Fire centre unavailable"} · {result.status}</span>
              <small>Updated {formatTimestamp(result.source_updated_at)}</small>
            </div>
            <a href={result.source_url} target="_blank" rel="noreferrer">{sourceLinkLabel(result)}</a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function LiveAnalysisWorkspace({ session, embedded = false }: { session: FireLensSession; embedded?: boolean }) {
  const [surface, setSurface] = useState<AnalysisSurface>("summary");
  const results = useMemo(
    () => (session.response?.live_results ?? []).filter((result) => result.kind === "incident"),
    [session.response?.live_results],
  );
  const analysis = useMemo(() => buildLiveAnalysis(results), [results]);
  const newestSourceTime = results.reduce<string | undefined>((latest, result) => {
    if (!latest) return result.source_updated_at;
    return new Date(result.source_updated_at) > new Date(latest) ? result.source_updated_at : latest;
  }, undefined);

  useEffect(() => {
    session.setMapVisible(surface === "map");
    return () => session.setMapVisible(false);
  }, [session.setMapVisible, surface]);

  useEffect(() => {
    setSurface("summary");
  }, [session.response?.trace_id]);

  return (
    <section className={`analysis-workspace ${embedded ? "analysis-workspace--embedded" : ""}`} aria-label="Analysis view">
      <div className="analysis-workspace__heading">
        <div>
          <span className="panel-label">Analysis view</span>
          <h2>{embedded ? "Current official records, summarized" : "Current records, summarized"}</h2>
        </div>
        <div className="analysis-tabs" role="group" aria-label="Choose analysis view">
          <button type="button" className={surface === "summary" ? "analysis-tabs__active" : ""} aria-pressed={surface === "summary"} onClick={() => setSurface("summary")}>
            <ChartBar size={19} /> Summary
          </button>
          <button type="button" className={surface === "map" ? "analysis-tabs__active" : ""} aria-pressed={surface === "map"} onClick={() => setSurface("map")}>
            <MapTrifold size={19} /> Map
          </button>
          <button type="button" className={surface === "records" ? "analysis-tabs__active" : ""} aria-pressed={surface === "records"} onClick={() => setSurface("records")}>
            <ListBullets size={19} /> Records
          </button>
        </div>
      </div>

      {surface === "summary" && (
        <>
          <div className="analysis-grid">
            <CountTable title="Wildfires by fire centre" rows={analysis.byFireCentre} />
            <CountTable title="Wildfires by status" rows={analysis.byStatus} />
          </div>
          {analysis.highestFireCentre && (
            <p className="analysis-insight">
              <ChartBar size={20} aria-hidden="true" />
              <span><strong>{analysis.highestFireCentre.label}</strong> has the highest incident count in this bounded result.</span>
            </p>
          )}
          <details className="analysis-disclosure">
            <summary><Database size={20} /><strong>Sources and freshness</strong><span>Where the data came from and when it changed</span></summary>
            <p>These {analysis.total} incident records came from the BC Wildfire Service data returned with this answer.</p>
            {newestSourceTime && <p>Newest source update in this result: {formatTimestamp(newestSourceTime)}.</p>}
          </details>
          <details className="analysis-disclosure">
            <summary><ShieldCheck size={20} /><strong>Technical evidence</strong><span>How the summary was derived</span></summary>
            <p>FireLens grouped typed official records by their fire-centre and status fields. The browser calculated these counts deterministically; model prose is not used as data.</p>
          </details>
        </>
      )}

      {surface === "map" && (
        <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading the official map">Preparing map layers…</EvidencePlaceholder>}>
          <LiveMap
            results={session.mapResults}
            matchingResults={session.mapMatchingResults}
            provinceResults={session.mapProvinceResults}
            aggregateFreshness={session.mapAggregateFreshness}
            unavailableLayers={session.mapUnavailableLayers}
            focus={session.mapFocus}
            focusResults={session.mapFocusResults}
            selectedResultId={session.selectedLiveResultId}
            onSelectResult={session.setSelectedLiveResultId}
            onAskAboutResult={session.askAboutResult}
          />
        </Suspense>
      )}

      {surface === "records" && <RecordsView results={results} />}
    </section>
  );
}
