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
  return {
    total: incidents.length,
    byFireCentre,
    byStatus,
    highestFireCentre: byFireCentre.find((row) => row.label !== NOT_REPORTED),
  };
}
