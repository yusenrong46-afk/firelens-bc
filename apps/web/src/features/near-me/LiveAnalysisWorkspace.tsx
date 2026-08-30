import { ChartBar, Database, ListBullets, MapTrifold, ShieldCheck } from "@phosphor-icons/react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { LiveResult } from "../../shared/api/api";
import type { FireLensSession } from "../ask/useFireLensSession";
import { splitLimitations } from "../ask/limitationsPresentation";
import { EvidencePlaceholder } from "../evidence/evidencePresentation";
import {
  buildLiveAnalysis,
  sortAnalysisResults,
  type AnalysisSort,
} from "./liveAnalysis";
import {
  isRenderableGeometry,
  formatTimestamp,
} from "./liveResultPresentation";
import {
  AnalysisFilters,
  joinAnalysisLabels,
  RecordsView,
} from "./analysisWorkspaceParts";
import "./analysisWorkspace.css";

const LiveMap = lazy(() => import("./LiveMap").then((module) => ({ default: module.LiveMap })));
let analysisChartsModule: ReturnType<typeof importAnalysisCharts> | undefined;

function importAnalysisCharts() {
  return import("./AnalysisCharts");
}

export function preloadAnalysisCharts() {
  analysisChartsModule ??= importAnalysisCharts();
  return analysisChartsModule;
}

const AnalysisCharts = lazy(() =>
  preloadAnalysisCharts().then((module) => ({ default: module.AnalysisCharts })),
);

type AnalysisSurface = "summary" | "map" | "records";

export function LiveAnalysisWorkspace({
  session,
  answerIdentity,
  evidenceOpen = false,
  initialSurface,
  onOpenEvidence,
}: {
  session: FireLensSession;
  answerIdentity: string;
  evidenceOpen?: boolean;
  initialSurface: "summary" | "map";
  onOpenEvidence?: (() => void) | undefined;
}) {
  const results = useMemo(
    () => (session.response?.live_results ?? []).filter((result) => result.kind === "incident"),
    [session.response?.live_results],
  );
  const hasUsefulMap = useMemo(() => results.some(isRenderableGeometry), [results]);
  // Every new analytical answer opens on the compact overview. The map is a
  // deliberate secondary surface, so a previous question or a map-oriented
  // request cannot make the first viewport skip the answer and KPI context.
  void initialSurface;
  const resolvedInitialSurface: AnalysisSurface = "summary";
  const [surface, setSurface] = useState<AnalysisSurface>(resolvedInitialSurface);
  const [fireCentreFilter, setFireCentreFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState<AnalysisSort>("default");
  const previousAnswerIdentity = useRef(answerIdentity);
  const tabRefs = useRef<Partial<Record<AnalysisSurface, HTMLButtonElement | null>>>({});
  const filteredResults = useMemo(() => {
    const filtered = results.filter((result) =>
      (!fireCentreFilter || result.fire_centre?.trim() === fireCentreFilter)
      && (!statusFilter || result.status?.trim() === statusFilter),
    );
    return sortAnalysisResults(filtered, sort);
  }, [fireCentreFilter, results, sort, statusFilter]);
  const analysis = useMemo(() => buildLiveAnalysis(filteredResults), [filteredResults]);
  const mapFilterActive = Boolean(fireCentreFilter || statusFilter);
  const applyMapFilters = (mapResults: LiveResult[]) => {
    if (!mapFilterActive) return mapResults;
    return mapResults.filter((result) => result.kind !== "incident"
      || ((!fireCentreFilter || result.fire_centre?.trim() === fireCentreFilter)
        && (!statusFilter || result.status?.trim() === statusFilter)));
  };
  const filteredMapResults = useMemo(() => {
    return applyMapFilters(session.mapResults);
  }, [fireCentreFilter, mapFilterActive, session.mapResults, statusFilter]);
  const filteredMapMatchingResults = useMemo(() => {
    return applyMapFilters(session.mapMatchingResults);
  }, [fireCentreFilter, mapFilterActive, session.mapMatchingResults, statusFilter]);
  const filteredMapProvinceResults = useMemo(() => {
    return applyMapFilters(session.mapProvinceResults);
  }, [fireCentreFilter, mapFilterActive, session.mapProvinceResults, statusFilter]);
  const analysisLimitations = useMemo(() => {
    const unavailable = session.response?.unavailable_layers ?? [];
    const unavailableNotice = unavailable.length > 0
      ? `Some official layers are unavailable: ${unavailable.join(", ")}. This is not an all-clear.`
      : undefined;
    const limitations = [unavailableNotice, ...(session.response?.limitations ?? [])]
      .filter((item): item is string => Boolean(item?.trim()))
      .map((item) => item.trim());
    return splitLimitations(Array.from(new Set(limitations)));
  }, [session.response?.limitations, session.response?.unavailable_layers]);
  const newestSourceTime = results.reduce<string | undefined>((latest, result) => {
    if (!latest) return result.source_updated_at;
    return new Date(result.source_updated_at) > new Date(latest) ? result.source_updated_at : latest;
  }, undefined);

  useEffect(() => {
    session.setMapVisible(hasUsefulMap && surface === "map");
    return () => session.setMapVisible(false);
  }, [hasUsefulMap, session.setMapVisible, surface]);

  useEffect(() => {
    if (!hasUsefulMap && surface === "map") setSurface("summary");
  }, [hasUsefulMap, surface]);

  useEffect(() => {
    if (previousAnswerIdentity.current === answerIdentity) return;
    previousAnswerIdentity.current = answerIdentity;
    setSurface(resolvedInitialSurface);
    setFireCentreFilter("");
    setStatusFilter("");
    setSort("default");
  }, [answerIdentity, resolvedInitialSurface]);

  const surfaces = (hasUsefulMap ? ["summary", "map", "records"] : ["summary", "records"]) as AnalysisSurface[];
  const moveTab = (index: number) => {
    const next = surfaces[(index + surfaces.length) % surfaces.length] ?? "summary";
    setSurface(next);
    requestAnimationFrame(() => tabRefs.current[next]?.focus());
  };
  const handleTabKey = (event: KeyboardEvent<HTMLButtonElement>, current: AnalysisSurface) => {
    const index = surfaces.indexOf(current);
    if (event.key === "ArrowRight") { event.preventDefault(); moveTab(index + 1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); moveTab(index - 1); }
    if (event.key === "Home") { event.preventDefault(); moveTab(0); }
    if (event.key === "End") { event.preventDefault(); moveTab(surfaces.length - 1); }
  };

  return (
    <section className="analysis-workspace" aria-label="Analysis view">
      <div className="analysis-workspace__heading">
        <h2 data-surface-visually-hidden="true">Analysis view</h2>
        <div className={`analysis-tabs ${hasUsefulMap ? "" : "analysis-tabs--two"}`} role="tablist" aria-label="Choose analysis view">
          <button type="button" role="tab" id="analysis-tab-summary" aria-controls="analysis-panel-summary" className={surface === "summary" ? "analysis-tabs__active" : ""} aria-selected={surface === "summary"} tabIndex={surface === "summary" ? 0 : -1} ref={(node) => { tabRefs.current.summary = node; }} onKeyDown={(event) => handleTabKey(event, "summary")} onClick={() => setSurface("summary")}>
            <ChartBar size={19} /> Summary
          </button>
          {hasUsefulMap && (
            <button type="button" role="tab" id="analysis-tab-map" aria-controls="analysis-panel-map" className={surface === "map" ? "analysis-tabs__active" : ""} aria-selected={surface === "map"} tabIndex={surface === "map" ? 0 : -1} ref={(node) => { tabRefs.current.map = node; }} onKeyDown={(event) => handleTabKey(event, "map")} onClick={() => setSurface("map")}>
              <MapTrifold size={19} /> Map
            </button>
          )}
          <button type="button" role="tab" id="analysis-tab-records" aria-controls="analysis-panel-records" className={surface === "records" ? "analysis-tabs__active" : ""} aria-selected={surface === "records"} tabIndex={surface === "records" ? 0 : -1} ref={(node) => { tabRefs.current.records = node; }} onKeyDown={(event) => handleTabKey(event, "records")} onClick={() => setSurface("records")}>
            <ListBullets size={19} /> Records
          </button>
        </div>
      </div>

      <div
        id="analysis-panel-summary"
        role="tabpanel"
        aria-labelledby="analysis-tab-summary"
        tabIndex={0}
        hidden={surface !== "summary"}
      >
        {surface === "summary" && (
          <>
          <Suspense fallback={<div className="analysis-chart-loading" role="status">Preparing the official-record summary…</div>}>
            <AnalysisCharts
              byFireCentre={analysis.byFireCentre}
              byStatus={analysis.byStatus}
              total={analysis.total}
            />
          </Suspense>
          {analysis.highestFireCentre && (
            <p className="analysis-insight">
              <ChartBar size={20} aria-hidden="true" />
              <span><strong>Insight:</strong> {analysis.highestFireCentre.label} has the highest number of incident records in this result.</span>
            </p>
          )}
          {!analysis.highestFireCentre && analysis.highestFireCentres.length > 1 && (
            <p className="analysis-insight">
              <ChartBar size={20} aria-hidden="true" />
              <span><strong>Insight:</strong> {joinAnalysisLabels(analysis.highestFireCentres.map((row) => row.label))} are tied for the highest count in this bounded result, with {analysis.highestFireCentres[0]?.count} each.</span>
            </p>
          )}
          </>
        )}
      </div>

      {hasUsefulMap && (
        <div
          id="analysis-panel-map"
          role="tabpanel"
          aria-labelledby="analysis-tab-map"
          tabIndex={0}
          hidden={surface !== "map"}
        >
          {surface === "map" && (
          <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading map">Preparing map…</EvidencePlaceholder>}>
            <LiveMap
              results={filteredMapResults}
              matchingResults={filteredMapMatchingResults}
              provinceResults={filteredMapProvinceResults}
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
        </div>
      )}

      <div
        id="analysis-panel-records"
        role="tabpanel"
        aria-labelledby="analysis-tab-records"
        tabIndex={0}
        hidden={surface !== "records"}
      >
        {surface === "records" && (
          <>
          <AnalysisFilters results={results} fireCentre={fireCentreFilter} status={statusFilter} sort={sort} onFireCentre={setFireCentreFilter} onStatus={setStatusFilter} onSort={setSort} />
          <RecordsView results={filteredResults} totalResults={results.length} />
          </>
        )}
      </div>

      <div className="analysis-evidence-rail">
        {analysisLimitations.material.length > 0 && (
          <aside className="analysis-limitations" aria-label="Analysis limitations">
            {analysisLimitations.material.join(" ")}
          </aside>
        )}
        {analysisLimitations.boilerplate.length > 0 && (
          <details className="analysis-disclosure analysis-disclosure--limits">
            <summary><ShieldCheck size={20} /><strong>Limits</strong><span>Boundaries</span></summary>
            <ul>
              {analysisLimitations.boilerplate.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </details>
        )}
        <details className="analysis-disclosure">
          <summary><Database size={20} /><strong>Sources</strong><span>Official records</span></summary>
          <p>These {results.length} incident records came from the official data returned with this answer.</p>
          {newestSourceTime && <p>Newest source update in this result: {formatTimestamp(newestSourceTime)}.</p>}
        </details>
        <details className="analysis-disclosure">
          <summary><ShieldCheck size={20} /><strong>Method</strong><span>Deterministic counts</span></summary>
          <p>FireLens grouped typed official records by their fire-centre and status fields. The browser calculated these counts deterministically; model prose is not used as data.</p>
          {onOpenEvidence && (
            <button
              type="button"
              aria-controls="answer-context"
              aria-expanded={evidenceOpen}
              onClick={onOpenEvidence}
            >
              Inspect answer evidence
            </button>
          )}
        </details>
      </div>
    </section>
  );
}
