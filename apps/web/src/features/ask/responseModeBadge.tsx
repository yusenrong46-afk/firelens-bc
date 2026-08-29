import type { AskResponse, ResponseMode } from "../../shared/api/api";
import { abstentionPresentation } from "./abstentionPresentation";
import { isReviewedSourceHandoff } from "./proofPresentation";
import type { AggregateFreshness } from "./responseModel";

export function ResponseModeBadge({
  mode,
  aggregateFreshness,
  answerSectionKinds = [],
  reasonCode,
  response,
}: {
  mode: ResponseMode;
  aggregateFreshness?: AggregateFreshness | undefined;
  answerSectionKinds?: string[] | undefined;
  reasonCode?: AskResponse["reason_code"] | undefined;
  response?: Pick<AskResponse, "response_mode" | "reason_code" | "related_links"> | undefined;
}) {
  const labels: Record<ResponseMode, string> = {
    grounded: "Reviewed sources",
    partial: "Partially supported",
    background: "General knowledge",
    capability: "FireLens topics",
    scope_redirect: "Related official service",
    abstention: "Could not complete",
    live: "Official live records",
    mixed: "Live records + reviewed guidance",
    conflict: "Conflicting reviewed sources",
    requires_input: "One detail needed",
  };
  if (mode === "abstention") labels.abstention = abstentionPresentation(reasonCode).badge;
  if (mode === "scope_redirect" && reasonCode === "no_approved_evidence") {
    labels.scope_redirect = isReviewedSourceHandoff(response) ? "Reviewed source handoff" : "Coverage limit";
  }
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
