import type { LiveResult } from "../../shared/api/api";

function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

export function exportRecordsCsv(
  results: LiveResult[],
  meta: { queryIdentity?: string; retrievedAt?: string; freshness?: string },
): string {
  const header = [
    "result_id",
    "kind",
    "name",
    "incident_number",
    "status",
    "size_hectares",
    "authority",
    "source_updated_at",
    "retrieved_at",
    "freshness",
    "query_identity",
  ];
  const rows = results.map((result) => [
    result.result_id,
    result.kind,
    result.name ?? "",
    result.incident_number ?? "",
    result.status,
    result.size_hectares == null ? "" : String(result.size_hectares),
    result.authority,
    result.source_updated_at,
    result.retrieved_at,
    result.freshness,
    meta.queryIdentity ?? "",
  ]);
  return [header, ...rows].map((row) => row.map((cell) => csvCell(String(cell))).join(",")).join("\n");
}
