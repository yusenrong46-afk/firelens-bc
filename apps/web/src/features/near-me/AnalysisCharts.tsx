import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { AnalysisCount } from "./liveAnalysis";

const STATUS_COLOURS = ["#c96950", "#d9a13b", "#315f4a", "#c7cbc9", "#82968c"];

function statusColour(index: number): string {
  return STATUS_COLOURS[index % STATUS_COLOURS.length] ?? STATUS_COLOURS[0]!;
}

function conciseFireCentre(value: string): string {
  return value.replace(/\s+Fire\s+Centre$/i, "");
}

function percentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function FireCentreChart({ rows }: { rows: AnalysisCount[] }) {
  const data = rows.map((row) => ({ ...row, shortLabel: conciseFireCentre(row.label) }));
  return (
    <section className="analysis-chart-card" aria-label="Incident records by fire centre">
      <h3>Incident records by fire centre</h3>
      {data.length === 0 ? (
        <p className="analysis-empty">Fire-centre fields were not available in these records.</p>
      ) : (
        <div className="analysis-chart analysis-chart--bars" role="img" aria-label={data.map((row) => `${row.shortLabel}: ${row.count}`).join(", ")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 8, right: 32, bottom: 18, left: 6 }}>
              <CartesianGrid horizontal={false} stroke="#e2e5df" />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={{ stroke: "#cfd5cf" }} />
              <YAxis dataKey="shortLabel" type="category" width={104} tickLine={false} axisLine={false} />
              <Tooltip formatter={(value) => [`${String(value)} incident records`, "Count"]} />
              <Bar dataKey="count" fill="#c96950" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                <LabelList dataKey="count" position="right" fill="#1a2b26" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {data.length > 0 && <ul className="analysis-chart-data" aria-label="Fire-centre record totals">{data.map((row) => <li key={row.label}><span>{row.shortLabel}</span><strong>{row.count}</strong><small>{percentage(row.share)}</small></li>)}</ul>}
    </section>
  );
}

export function StatusChart({ rows, total }: { rows: AnalysisCount[]; total: number }) {
  return (
    <section className="analysis-chart-card" aria-label="Incident records by status">
      <h3>Incident records by status</h3>
      {rows.length === 0 ? (
        <p className="analysis-empty">Status fields were not available in these records.</p>
      ) : (
        <div className="analysis-status-chart">
          <div className="analysis-chart analysis-chart--donut" role="img" aria-label={rows.map((row) => `${row.label}: ${row.count}, ${percentage(row.share)}`).join(", ")}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip formatter={(value) => [`${String(value)} incident records`, "Count"]} />
                <Pie
                  data={rows}
                  dataKey="count"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius="43%"
                  outerRadius="76%"
                  paddingAngle={1}
                  stroke="#fff"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {rows.map((row, index) => <Cell key={row.label} fill={statusColour(index)} />)}
                  <LabelList dataKey="share" position="inside" formatter={(value) => percentage(Number(value ?? 0))} fill="#fff" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
            <div className="analysis-status-legend" aria-label="Incident status totals">
            <ul>
              {rows.map((row, index) => (
                <li key={row.label}>
                  <span className="analysis-status-legend__swatch" style={{ backgroundColor: statusColour(index) }} aria-hidden="true" />
                  <span>{row.label}</span>
                  <strong>{row.count} <small>{percentage(row.share)}</small></strong>
                </li>
              ))}
            </ul>
            <p><span>Total incident records</span><strong>{total}</strong></p>
          </div>
        </div>
      )}
    </section>
  );
}

export function AnalysisCharts({ byFireCentre, byStatus, total }: {
  byFireCentre: AnalysisCount[];
  byStatus: AnalysisCount[];
  total: number;
}) {
  const [view, setView] = useState<"charts" | "table">("charts");
  const chartsId = useId();
  const tableId = useId();
  const chartTab = useRef<HTMLButtonElement>(null);
  const tableTab = useRef<HTMLButtonElement>(null);
  const setDisplay = (next: "charts" | "table") => {
    setView(next);
    requestAnimationFrame(() => (next === "charts" ? chartTab.current : tableTab.current)?.focus());
  };
  const onDisplayKey = (event: KeyboardEvent<HTMLButtonElement>, current: "charts" | "table") => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const next = event.key === "Home"
        ? "charts"
        : event.key === "End"
          ? "table"
          : event.key === "ArrowRight"
            ? (current === "charts" ? "table" : "charts")
            : (current === "table" ? "charts" : "table");
      setDisplay(next);
    }
  };
  return (
    <div>
      <div className="analysis-chart-switch" role="tablist" aria-label="Analysis display">
        <button
          type="button"
          role="tab"
          id={`${chartsId}-tab`}
          aria-controls={chartsId}
          aria-selected={view === "charts"}
          tabIndex={view === "charts" ? 0 : -1}
          ref={chartTab}
          onKeyDown={(event) => onDisplayKey(event, "charts")}
          onClick={() => setDisplay("charts")}
        >Charts</button>
        <button
          type="button"
          role="tab"
          id={`${tableId}-tab`}
          aria-controls={tableId}
          aria-selected={view === "table"}
          tabIndex={view === "table" ? 0 : -1}
          ref={tableTab}
          onKeyDown={(event) => onDisplayKey(event, "table")}
          onClick={() => setDisplay("table")}
        >Table</button>
      </div>
      <div
        id={chartsId}
        role="tabpanel"
        aria-labelledby={`${chartsId}-tab`}
        className="analysis-grid"
        hidden={view !== "charts"}
      >
        {view === "charts" && (
          <>
          <FireCentreChart rows={byFireCentre} />
          <StatusChart rows={byStatus} total={total} />
          </>
        )}
      </div>
      <div
        id={tableId}
        role="tabpanel"
        aria-labelledby={`${tableId}-tab`}
        className="analysis-table-wrap"
        hidden={view !== "table"}
      >
        {view === "table" && (
          <table>
            <caption>Incident records grouped by field</caption>
            <thead><tr><th scope="col">Group</th><th scope="col">Category</th><th scope="col">Records</th><th scope="col">Share</th></tr></thead>
            <tbody>
              {byFireCentre.map((row) => (
                <tr key={`centre-${row.label}`}><th scope="row">Fire centre</th><td>{row.label}</td><td>{row.count}</td><td>{percentage(row.share)}</td></tr>
              ))}
              {byStatus.map((row) => (
                <tr key={`status-${row.label}`}><th scope="row">Status</th><td>{row.label}</td><td>{row.count}</td><td>{percentage(row.share)}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
