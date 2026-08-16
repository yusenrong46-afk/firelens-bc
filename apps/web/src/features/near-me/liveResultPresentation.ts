import type { LiveResult } from "../../shared/api/api";

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable";
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

export function resultKindLabel(kind: LiveResult["kind"]): string {
  if (kind === "evacuation") return "Evacuation area";
  if (kind === "perimeter") return "Wildfire perimeter";
  return "Wildfire incident";
}

export function resultDisplayName(result: LiveResult): string {
  const name = result.name?.trim();
  if (name && name.toLowerCase() !== "unnamed official record") return name;
  const incidentNumber = result.incident_number?.trim();
  if (incidentNumber) return `${resultKindLabel(result.kind)} ${incidentNumber}`;
  return resultKindLabel(result.kind);
}

export function resultStatus(result: LiveResult): string {
  return result.status?.trim() || "Status unavailable";
}

export function sourceLinkLabel(result: LiveResult): string {
  return /(?:featureserver|mapserver|arcgis)/i.test(result.source_url)
    ? "GIS dataset"
    : "Source";
}

export function interleaveByKind(results: LiveResult[]): LiveResult[] {
  const grouped = new Map<LiveResult["kind"], LiveResult[]>();
  for (const result of results) {
    const bucket = grouped.get(result.kind) ?? [];
    bucket.push(result);
    grouped.set(result.kind, bucket);
  }
  const ordered: LiveResult[] = [];
  const kinds: LiveResult["kind"][] = ["incident", "evacuation", "perimeter"];
  let index = 0;
  while (ordered.length < results.length) {
    let added = false;
    for (const kind of kinds) {
      const result = grouped.get(kind)?.[index];
      if (result) {
        ordered.push(result);
        added = true;
      }
    }
    if (!added) break;
    index += 1;
  }
  return ordered;
}

export function resultColour(kind: LiveResult["kind"]): string {
  if (kind === "evacuation") return "#9b3f26";
  if (kind === "perimeter") return "#c26b2d";
  return "#b42318";
}

export function isRenderableGeometry(result: LiveResult): boolean {
  const geometry = result.geometry as { type?: string; coordinates?: unknown } | undefined;
  if (!geometry || !Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) {
    return false;
  }
  return ["Point", "Polygon", "MultiPolygon"].includes(geometry.type ?? "");
}

export function geometryLatLngs(result: LiveResult): [number, number][] {
  const geometry = result.geometry as { type?: string; coordinates?: unknown } | undefined;
  if (!geometry || !Array.isArray(geometry.coordinates)) return [];
  if (geometry.type === "Point") {
    const [longitude, latitude] = geometry.coordinates as number[];
    return Number.isFinite(latitude) && Number.isFinite(longitude)
      ? ([[latitude, longitude]] as [number, number][])
      : [];
  }
  const points: [number, number][] = [];
  const walk = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
      const longitude = value[0];
      const latitude = value[1];
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        points.push([latitude, longitude]);
      }
      return;
    }
    value.forEach(walk);
  };
  walk(geometry.coordinates);
  return points;
}
