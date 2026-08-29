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

function ChartSourceLine({ ranked = false }: { ranked?: boolean }) {
  return (
    <p className="analysis-chart__source">
      Derived from official live records
      {ranked && <span>Ranked</span>}
    </p>
  );
}

export function FireCentreChart({ rows }: { rows: AnalysisCount[] }) {
  const data = rows.map((row) => ({ ...row, shortLabel: conciseFireCentre(row.label) }));
  return (
    <section className="analysis-chart-card" aria-label="Active wildfires by fire centre">
      <h3>Active wildfires by fire centre</h3>
      <ChartSourceLine ranked />
      {data.length === 0 ? (
        <p className="analysis-empty">Fire-centre fields were not available in these records.</p>
      ) : (
        <div className="analysis-chart analysis-chart--bars" role="img" aria-label={data.map((row) => `${row.shortLabel}: ${row.count}`).join(", ")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 8, right: 32, bottom: 18, left: 6 }}>
              <CartesianGrid horizontal={false} stroke="#e2e5df" />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={{ stroke: "#cfd5cf" }} />
              <YAxis dataKey="shortLabel" type="category" width={104} tickLine={false} axisLine={false} />
              <Tooltip formatter={(value) => [`${String(value)} active wildfires`, "Count"]} />
              <Bar dataKey="count" fill="#c96950" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                <LabelList dataKey="count" position="right" fill="#1a2b26" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

export function StatusChart({ rows, total }: { rows: AnalysisCount[]; total: number }) {
  return (
    <section className="analysis-chart-card" aria-label="Active wildfires by status">
      <h3>Active wildfires by status</h3>
      <ChartSourceLine />
      {rows.length === 0 ? (
        <p className="analysis-empty">Status fields were not available in these records.</p>
      ) : (
        <div className="analysis-status-chart">
          <div className="analysis-chart analysis-chart--donut" role="img" aria-label={rows.map((row) => `${row.label}: ${row.count}, ${percentage(row.share)}`).join(", ")}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip formatter={(value) => [`${String(value)} active wildfires`, "Count"]} />
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
          <div className="analysis-status-legend" aria-label="Wildfire status totals">
            <ul>
              {rows.map((row, index) => (
                <li key={row.label}>
                  <span className="analysis-status-legend__swatch" style={{ backgroundColor: statusColour(index) }} aria-hidden="true" />
                  <span>{row.label}</span>
                  <strong>{row.count}</strong>
                </li>
              ))}
            </ul>
            <p><span>Total active wildfires</span><strong>{total}</strong></p>
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
  return (
    <div className="analysis-grid">
      <FireCentreChart rows={byFireCentre} />
      <StatusChart rows={byStatus} total={total} />
    </div>
  );
}
