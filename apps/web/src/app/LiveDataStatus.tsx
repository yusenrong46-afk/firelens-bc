import type { LiveCurrentSummary } from "../shared/api/api";

export type ReadinessState = "ready" | "not_ready" | "unknown";

function relativeUpdate(iso: string | null | undefined): string | undefined {
  if (!iso) return undefined;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return undefined;
  const minutes = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 60_000));
  if (minutes < 1) return "Updated just now";
  if (minutes === 1) return "Updated 1 min ago";
  if (minutes < 60) return `Updated ${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours === 1) return "Updated 1 hour ago";
  return `Updated ${hours} hours ago`;
}

export function liveDataTone(
  liveSummary: LiveCurrentSummary | undefined,
  readiness: ReadinessState,
): "unavailable" | "delayed" | "live" {
  if (readiness === "not_ready") return "unavailable";
  if (!liveSummary) return "unavailable";

  const status = liveSummary.source_status?.toLowerCase() ?? "";
  const freshness = liveSummary.freshness?.toLowerCase() ?? "";
  const bothLayersMissing = liveSummary.incident_record_count == null
    && liveSummary.evacuation_record_count == null;

  if (
    bothLayersMissing
    || status.includes("unavailable")
    || status.includes("fail")
    || status.includes("error")
  ) {
    return "unavailable";
  }

  if (
    freshness === "stale"
    || freshness === "mixed"
    || status.includes("delay")
    || status.includes("stale")
    || status.includes("partial")
  ) {
    return "delayed";
  }

  return "live";
}

export function LiveDataStatus({
  liveSummary,
  readiness,
}: {
  liveSummary: LiveCurrentSummary | undefined;
  readiness: ReadinessState;
}) {
  const tone = liveDataTone(liveSummary, readiness);
  const update = relativeUpdate(liveSummary?.retrieved_at ?? null);

  if (tone === "unavailable") {
    return (
      <p className="live-data-status live-data-status--unavailable" role="status">
        <span className="live-data-status__dot" aria-hidden="true" />
        <span>
          <strong>Live data unavailable</strong>
          <small>Check official sources</small>
        </span>
      </p>
    );
  }

  if (tone === "delayed") {
    return (
      <p className="live-data-status live-data-status--delayed" role="status">
        <span className="live-data-status__dot" aria-hidden="true" />
        <span>
          <strong>Official data delayed</strong>
          <small>{update ? update.replace("Updated", "Last successful update") : "Update time not published"}</small>
        </span>
      </p>
    );
  }

  return (
    <p className="live-data-status live-data-status--live" role="status">
      <span className="live-data-status__dot" aria-hidden="true" />
      <span>
        <strong>Live data</strong>
        <small>{update ?? "Update time not published"}</small>
      </span>
    </p>
  );
}
