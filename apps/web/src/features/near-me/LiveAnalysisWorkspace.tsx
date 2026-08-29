import { ChartBar, Database, ListBullets, MapTrifold, ShieldCheck } from "@phosphor-icons/react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { LiveResult } from "../../shared/api/api";
import type { FireLensSession } from "../ask/useFireLensSession";
import { splitLimitations } from "../ask/limitationsPresentation";
import { EvidencePlaceholder } from "../evidence/evidencePresentation";
import { buildLiveAnalysis } from "./liveAnalysis";
import {
  formatTimestamp,
  isRenderableGeometry,
  resultDisplayName,
  sourceLinkLabel,
} from "./liveResultPresentation";
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

function joinLabels(labels: string[]): string {
  if (labels.length < 2) return labels[0] ?? "";
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels.at(-1)}`;
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
  const analysis = useMemo(() => buildLiveAnalysis(results), [results]);
  const hasUsefulMap = useMemo(() => results.some(isRenderableGeometry), [results]);
  const resolvedInitialSurface: AnalysisSurface = initialSurface === "map" && hasUsefulMap
    ? "map"
    : "summary";
  const [surface, setSurface] = useState<AnalysisSurface>(resolvedInitialSurface);
  const previousAnswerIdentity = useRef(answerIdentity);
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
  }, [answerIdentity, resolvedInitialSurface]);

  return (
    <section className="analysis-workspace" aria-label="Analysis view">
      <div className="analysis-workspace__heading">
        <h2>Analysis view</h2>
        <div className={`analysis-tabs ${hasUsefulMap ? "" : "analysis-tabs--two"}`} role="group" aria-label="Choose analysis view">
          <button type="button" className={surface === "summary" ? "analysis-tabs__active" : ""} aria-pressed={surface === "summary"} onClick={() => setSurface("summary")}>
            <ChartBar size={19} /> Summary
          </button>
          {hasUsefulMap && (
            <button type="button" className={surface === "map" ? "analysis-tabs__active" : ""} aria-pressed={surface === "map"} onClick={() => setSurface("map")}>
              <MapTrifold size={19} /> Map
            </button>
          )}
          <button type="button" className={surface === "records" ? "analysis-tabs__active" : ""} aria-pressed={surface === "records"} onClick={() => setSurface("records")}>
            <ListBullets size={19} /> Records
          </button>
        </div>
      </div>

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
              <span><strong>Insight:</strong> {analysis.highestFireCentre.label} has the highest number of active wildfires in this result.</span>
            </p>
          )}
          {!analysis.highestFireCentre && analysis.highestFireCentres.length > 1 && (
            <p className="analysis-insight">
              <ChartBar size={20} aria-hidden="true" />
              <span><strong>Insight:</strong> {joinLabels(analysis.highestFireCentres.map((row) => row.label))} are tied for the highest count in this bounded result, with {analysis.highestFireCentres[0]?.count} each.</span>
            </p>
          )}
        </>
      )}

      {surface === "map" && (
        <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading map">Preparing map…</EvidencePlaceholder>}>
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

      {analysisLimitations.material.length > 0 && (
        <aside className="analysis-limitations" aria-label="Analysis limitations">
          {analysisLimitations.material.join(" ")}
        </aside>
      )}
      {analysisLimitations.boilerplate.length > 0 && (
        <details className="analysis-disclosure analysis-disclosure--limits">
          <summary><ShieldCheck size={20} /><strong>About this analysis</strong><span>Boundaries that apply to these records</span></summary>
          <ul>
            {analysisLimitations.boilerplate.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>
      )}
      <details className="analysis-disclosure">
        <summary><Database size={20} /><strong>Sources and freshness</strong><span>Where this data comes from and when it was updated</span></summary>
        <p>These {analysis.total} incident records came from the BC Wildfire Service data returned with this answer.</p>
        {newestSourceTime && <p>Newest source update in this result: {formatTimestamp(newestSourceTime)}.</p>}
      </details>
      <details className="analysis-disclosure">
        <summary><ShieldCheck size={20} /><strong>Technical evidence</strong><span>How this answer was derived and verified</span></summary>
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
    </section>
  );
}
