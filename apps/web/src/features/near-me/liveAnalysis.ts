import type { LiveResult } from "../../shared/api/api";

export type AnalysisCount = {
  label: string;
  count: number;
  share: number;
};

export type LiveAnalysis = {
  total: number;
  byFireCentre: AnalysisCount[];
  byStatus: AnalysisCount[];
  highestFireCentres: AnalysisCount[];
  highestFireCentre?: AnalysisCount | undefined;
};

const NOT_REPORTED = "Not reported";

function countBy(
  results: LiveResult[],
  valueFor: (result: LiveResult) => string | null | undefined,
): AnalysisCount[] {
  const counts = new Map<string, number>();
  for (const result of results) {
    const value = valueFor(result)?.trim() || NOT_REPORTED;
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  const total = results.length;
  return Array.from(counts, ([label, count]) => ({
    label,
    count,
    share: total === 0 ? 0 : count / total,
  })).sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

export function buildLiveAnalysis(results: LiveResult[]): LiveAnalysis {
  const incidents = results.filter((result) => result.kind === "incident");
  const byFireCentre = countBy(incidents, (result) => result.fire_centre);
  const byStatus = countBy(incidents, (result) => result.status);
  const reportedFireCentres = byFireCentre.filter((row) => row.label !== NOT_REPORTED);
  const highestReportedCount = reportedFireCentres[0]?.count;
  const highestFireCentres = highestReportedCount === undefined
    ? []
    : reportedFireCentres.filter((row) => row.count === highestReportedCount);
  return {
    total: incidents.length,
    byFireCentre,
    byStatus,
    highestFireCentres,
    highestFireCentre: highestFireCentres.length === 1 ? highestFireCentres[0] : undefined,
  };
}

function joinLabels(labels: string[]): string {
  if (labels.length < 2) return labels[0] ?? "";
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels.at(-1)}`;
}

export function analyticalAnswerSummary(results: LiveResult[]): string | undefined {
  const analysis = buildLiveAnalysis(results);
  if (analysis.total === 0) return undefined;
  const noun = analysis.total === 1 ? "record" : "records";
  const clauses = [`This answer includes ${analysis.total} fetched official incident ${noun}.`];
  if (analysis.highestFireCentre) {
    clauses.push(
      `${analysis.highestFireCentre.label} has the highest fire-centre count (${analysis.highestFireCentre.count}).`,
    );
  } else if (analysis.highestFireCentres.length > 1) {
    clauses.push(
      `${joinLabels(analysis.highestFireCentres.map((row) => row.label))} tie for the highest fire-centre count (${analysis.highestFireCentres[0]?.count}).`,
    );
  }
  const highestStatusCount = analysis.byStatus[0]?.count;
  const highestStatuses = highestStatusCount === undefined
    ? []
    : analysis.byStatus.filter((row) => row.count === highestStatusCount);
  if (highestStatuses.length === 1) {
    clauses.push(
      `${highestStatuses[0]?.label} is the most common reported status (${highestStatusCount}).`,
    );
  } else if (highestStatuses.length > 1) {
    clauses.push(
      `${joinLabels(highestStatuses.map((row) => row.label))} tie for the most common reported status (${highestStatusCount}).`,
    );
  }
  return clauses.join(" ");
}
