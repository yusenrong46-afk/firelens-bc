import type { LiveCurrentSummary } from "../shared/api/api";

export type ReadinessState = "ready" | "not_ready" | "unknown";

function relativeCheck(iso: string | null | undefined, now: number): string {
  const checked = iso ? Date.parse(iso) : NaN;
  if (!Number.isFinite(checked)) return "Check time unavailable";
  const minutes = Math.max(0, Math.floor((now - checked) / 60_000));
  if (minutes < 1) return "Checked by FireLens just now";
  if (minutes < 60) return `Checked by FireLens ${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `Checked by FireLens ${hours} ${hours === 1 ? "hour" : "hours"} ago`;
}

export function liveDataTone(
  liveSummary: LiveCurrentSummary | undefined,
  readiness: ReadinessState,
): "unavailable" | "partial" | "delayed" | "live" {
  if (readiness === "not_ready" || !liveSummary) return "unavailable";
  const missing = [liveSummary.incident_record_count, liveSummary.evacuation_record_count]
    .filter((count) => count == null).length;
  if (missing === 2) return "unavailable";
  if (missing === 1 || liveSummary.source_status === "partial") return "partial";
  if (/unavailable|fail|error/i.test(liveSummary.source_status)) return "unavailable";
  if (liveSummary.freshness !== "fresh" || /delay|stale/i.test(liveSummary.source_status)) return "delayed";
  return "live";
}

export function LiveDataStatus({ liveSummary, readiness, now = Date.now() }: {
  liveSummary: LiveCurrentSummary | undefined;
  readiness: ReadinessState;
  now?: number;
}) {
  const tone = liveDataTone(liveSummary, readiness);
  const missing = liveSummary ? [
    liveSummary.incident_record_count == null ? "Incident records unavailable" : undefined,
    liveSummary.evacuation_record_count == null ? "Evacuation records unavailable" : undefined,
  ].filter(Boolean).join("; ") : "";
  const label = tone === "unavailable" ? "Live data unavailable"
    : tone === "partial" ? "Partial official coverage"
    : tone === "delayed" ? (liveSummary?.freshness === "stale" ? "Official records stale" : "Record freshness uncertain")
    : "Official records available";
  return (
    <p className={`live-data-status live-data-status--${tone === "partial" ? "delayed" : tone}`} role="status">
      <span className="live-data-status__dot" aria-hidden="true" />
      <span>
        <strong>{label}</strong>
        {missing && <small>{missing}</small>}
        <small>{liveSummary ? relativeCheck(liveSummary.retrieved_at, now) : "Check official sources"}</small>
      </span>
    </p>
  );
}
