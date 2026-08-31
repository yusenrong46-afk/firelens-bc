import type { LiveResult } from "../../shared/api/api";

export type PointCluster =
  | { type: "record"; result: LiveResult; latitude: number; longitude: number }
  | { type: "cluster"; latitude: number; longitude: number; count: number; ids: string[] };

const MIN_POINTS_TO_CLUSTER = 28;
const INDIVIDUAL_MARKER_ZOOM = 8;

export function isQuestionMatch(
  recordIds: readonly string[],
  matchingResultIds: ReadonlySet<string>,
): boolean {
  return matchingResultIds.size === 0 || recordIds.some((resultId) => matchingResultIds.has(resultId));
}

export function excludeQuestionMatches(
  results: LiveResult[],
  matchingResultIds: ReadonlySet<string>,
): LiveResult[] {
  return results.filter((result) => !matchingResultIds.has(result.result_id));
}

function pointCoordinates(result: LiveResult): { latitude: number; longitude: number } | undefined {
  const geometry = result.geometry as { type?: string; coordinates?: number[] } | undefined;
  if (geometry?.type !== "Point" || !Array.isArray(geometry.coordinates)) return undefined;
  const longitude = geometry.coordinates[0];
  const latitude = geometry.coordinates[1];
  if (longitude === undefined || latitude === undefined) return undefined;
  return { latitude, longitude };
}

export function clusterPointResults(results: LiveResult[], zoom: number): PointCluster[] {
  const points = results.flatMap((result) => {
    const coordinates = pointCoordinates(result);
    return coordinates ? [{ result, ...coordinates }] : [];
  }).sort((left, right) => left.result.result_id.localeCompare(right.result.result_id));
  if (zoom >= INDIVIDUAL_MARKER_ZOOM || points.length < MIN_POINTS_TO_CLUSTER) {
    return points.map((point) => ({ type: "record", ...point }));
  }
  const step = zoom >= 7 ? 0.25 : zoom >= 6 ? 0.5 : 1;
  const buckets = new Map<string, typeof points>();
  for (const point of points) {
    const key = `${Math.round(point.latitude / step)}_${Math.round(point.longitude / step)}`;
    const bucket = buckets.get(key) ?? [];
    bucket.push(point);
    buckets.set(key, bucket);
  }
  const clustered: PointCluster[] = [];
  for (const bucket of buckets.values()) {
    if (bucket.length === 1) {
      const only = bucket[0];
      if (only) clustered.push({ type: "record", ...only });
      continue;
    }
    const latitude = bucket.reduce((sum, item) => sum + item.latitude, 0) / bucket.length;
    const longitude = bucket.reduce((sum, item) => sum + item.longitude, 0) / bucket.length;
    clustered.push({
      type: "cluster",
      latitude,
      longitude,
      count: bucket.length,
      ids: bucket.map((item) => item.result.result_id).sort(),
    });
  }
  return clustered.sort((left, right) => {
    const leftKey = left.type === "cluster" ? left.ids.join("|") : left.result.result_id;
    const rightKey = right.type === "cluster" ? right.ids.join("|") : right.result.result_id;
    return leftKey.localeCompare(rightKey);
  });
}
