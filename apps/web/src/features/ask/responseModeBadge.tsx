import type { AskResponse, ResponseMode } from "../../shared/api/api";
import { abstentionPresentation } from "./abstentionPresentation";
import type { AggregateFreshness } from "./responseModel";

export function ResponseModeBadge({
  mode,
  aggregateFreshness,
  answerSectionKinds = [],
  reasonCode,
}: {
  mode: ResponseMode;
  aggregateFreshness?: AggregateFreshness | undefined;
  answerSectionKinds?: string[] | undefined;
  reasonCode?: AskResponse["reason_code"] | undefined;
}) {
  const labels: Record<ResponseMode, string> = {
    grounded: "Reviewed sources",
    partial: "Partially supported",
    background: "General background",
    capability: "FireLens topics",
    scope_redirect: "Related official service",
    abstention: "Could not complete",
    live: "Official live records",
    mixed: "Live records + reviewed guidance",
    conflict: "Conflicting reviewed sources",
    requires_input: "One detail needed",
  };
  if (mode === "abstention") labels.abstention = abstentionPresentation(reasonCode).badge;
  if (mode === "mixed" && answerSectionKinds.includes("conflicting_guidance")) {
    labels.mixed = "Live records + conflicting sources";
  } else if (mode === "mixed" && answerSectionKinds.includes("general_background")) {
    labels.mixed = "Live records + general background";
  } else if (mode === "mixed" && answerSectionKinds.includes("official_handoff")) {
    labels.mixed = "Live records + official link";
  }
  if (mode === "live" && aggregateFreshness === "stale") labels.live = "Official cached records";
  else if (mode === "live" && aggregateFreshness === "mixed") labels.live = "Official records — mixed freshness";
  else if (mode === "mixed" && aggregateFreshness === "stale") labels.mixed = labels.mixed.replace("Live records", "Cached records");
  else if (mode === "mixed" && aggregateFreshness === "mixed") labels.mixed = labels.mixed.replace("Live records", "Mixed-freshness records");
  return <span className={`response-badge response-badge--${mode}`}>{labels[mode]}</span>;
}
