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
  response?: Pick<AskResponse, "response_mode" | "reason_code" | "related_links" | "claims"> | undefined;
}) {
  const labels: Record<ResponseMode, string> = {
    grounded: "From reviewed guidance",
    partial: "Partly from reviewed guidance",
    background: "General knowledge",
    capability: "FireLens topics",
    scope_redirect: "Official source elsewhere",
    abstention: "Could not answer",
    live: "Official records",
    mixed: "Official records and reviewed guidance",
    conflict: "Sources disagree",
    requires_input: "One detail needed",
  };
  const quoteOnly = (response?.claims?.length ?? 0) > 0
    && (response?.claims ?? []).every((claim) => claim.publication?.kind === "official_quote_only");
  if (mode === "partial" && quoteOnly) labels.partial = "Exact wording from an official source";
  if (mode === "abstention") labels.abstention = abstentionPresentation(reasonCode).badge;
  if (mode === "scope_redirect" && reasonCode === "no_approved_evidence") {
    labels.scope_redirect = isReviewedSourceHandoff(response) ? "Reviewed source handoff" : "Coverage limit";
  }
  if (mode === "mixed" && answerSectionKinds.includes("conflicting_guidance")) {
    labels.mixed = "Official records; sources disagree";
  } else if (mode === "mixed" && answerSectionKinds.includes("general_background")) {
    labels.mixed = "Official records and general knowledge";
  } else if (mode === "mixed" && answerSectionKinds.includes("official_handoff")) {
    labels.mixed = "Official records and an official link";
  }
  if (mode === "live" && aggregateFreshness === "stale") labels.live = "Cached official records";
  else if (mode === "live" && aggregateFreshness === "mixed") labels.live = "Official records, some out of date";
  else if (mode === "mixed" && aggregateFreshness === "stale") labels.mixed = labels.mixed.replace("Official records", "Cached official records");
  else if (mode === "mixed" && aggregateFreshness === "mixed") labels.mixed = labels.mixed.replace("Official records", "Official records, some out of date,");
  return <span className={`response-badge response-badge--${mode}`}>{labels[mode]}</span>;
}
