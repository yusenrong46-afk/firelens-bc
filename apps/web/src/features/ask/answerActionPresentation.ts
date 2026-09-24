import type { AskResponse } from "../../shared/api/api";
import { readableAnswer } from "./readableAnswer";
import { guidanceGroups } from "./guidanceGroups";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import { getClaimSupportLabel, getProofCards, getStatusBanner } from "./proofPresentation";
import { reviewedSources, sourcesForQuote } from "./SourceProof";

export type AnswerActionSource = {
  title: string;
  publisher: string;
  url: string;
  revision?: string;
  checkedAt?: string;
  updatedAt?: string;
};

export type AnswerCheck = {
  label: string;
  result: "Passed" | "Failed" | "Not supplied";
};

export type AnswerExplanation = {
  answerTypes: string[];
  supportLabels: string[];
  sources: AnswerActionSource[];
  coverage: string[];
  location: string[];
  limitations: string[];
  checks: AnswerCheck[] | null;
  checkedAt?: string;
  updatedAt?: string;
  canInspectEvidence: boolean;
};

const LAYER_LABELS = { incident: "fires", perimeter: "perimeters", evacuation: "evacuations" };

function unique(items: string[]): string[] {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

/** Return supplied times only. Never use the browser clock as a source timestamp. */
function suppliedTimestamp(value: string | null | undefined): string | undefined {
  return value && Number.isFinite(Date.parse(value)) ? value : undefined;
}

/** Public response metadata only: this is an explanation of support, not an execution trace. */
export function explainAnswer(response: AskResponse): AnswerExplanation {
  const banner = getStatusBanner(response);
  const sections = getAnswerSections(response);
  const cards = getProofCards(response);
  const background = response.response_mode === "background";
  const rejected = response.validation?.accepted === false;
  const sources: AnswerActionSource[] = [];
  if (!background && !rejected) {
    for (const source of reviewedSources(response)) {
      sources.push({
        title: source.title, publisher: source.publisher, url: source.url,
        ...(source.revision ? { revision: source.revision } : {}),
      });
    }
    for (const record of response.live_results ?? []) {
      const checkedAt = suppliedTimestamp(record.retrieved_at);
      const updatedAt = suppliedTimestamp(record.source_updated_at);
      sources.push({
        title: record.name?.trim() || record.incident_number?.trim() || `Official ${record.kind} record`,
        publisher: record.authority,
        url: record.source_url,
        ...(checkedAt ? { checkedAt } : {}),
        ...(updatedAt ? { updatedAt } : {}),
      });
    }
  }
  const distinctSources = sources.filter((source, index) => sources.findIndex((other) => (
    other.title === source.title && other.url === source.url && other.publisher === source.publisher
      && other.revision === source.revision
      && other.checkedAt === source.checkedAt && other.updatedAt === source.updatedAt
  )) === index);
  const coverage: string[] = [];
  if (response.requested_layers?.length) {
    coverage.push(`Requested records: ${response.requested_layers.map((layer) => LAYER_LABELS[layer]).join(", ")}.`);
  }
  if (response.partial_layers?.length) {
    coverage.push(`Partial coverage: ${response.partial_layers.map((layer) => LAYER_LABELS[layer]).join(", ")}. Missing records are not an all-clear.`);
  }
  if (response.unavailable_layers?.length) {
    coverage.push(`Unavailable records: ${response.unavailable_layers.map((layer) => LAYER_LABELS[layer]).join(", ")}. These layers cannot be counted as empty.`);
  }
  if (response.aggregate_freshness) {
    const freshness = { fresh: "Fresh official records", stale: "Cached official records; they may be out of date", mixed: "Official records with mixed freshness" };
    coverage.push(freshness[response.aggregate_freshness]);
  }
  if ((response.live_results?.length ?? 0) > 0 || response.roster_total != null) {
    const returned = response.live_results?.length ?? 0;
    const recordLabel = returned === 1 ? "record" : "records";
    coverage.push(response.roster_total != null
      ? `${returned} returned official ${recordLabel}; ${response.roster_total} ${response.roster_total === 1 ? "record" : "records"} in the reported matching roster.`
      : `${returned} official ${recordLabel} attached to this response.`);
  }
  const location: string[] = [];
  if (response.resolved_location && !background && !rejected) {
    location.push("An approximate location was returned with this response.");
  }
  for (const card of background || rejected ? [] : cards) {
    const derivation = card.derivation;
    if (!derivation || card.support_state === "unknown" || card.support_state === "background") continue;
    const basis = derivation.distance_basis === "perimeter_boundary" ? "perimeter boundary" : "incident point";
    location.push(`${derivation.distance_km} ${derivation.units} geodesic distance to the ${basis}; algorithm: ${derivation.algorithm}; validation: ${derivation.validation_status}; publication: ${derivation.publication_state}.`);
  }
  const report = response.validation;
  const checkFields = [
    ["Response acceptance", "accepted"],
    ["Response format", "schema_valid"],
    ["Citation references", "citation_ids_valid"],
    ["Exact quotations", "quotes_exact"],
    ["Claim support", "claim_support_valid"],
    ["Publication policy", "policy_valid"],
  ] as const;
  const checks = report ? checkFields.map(([label, field]): AnswerCheck => ({
    label,
    result: report[field] === true ? "Passed" : report[field] === false ? "Failed" : "Not supplied",
  })) : null;
  const checkedAt = suppliedTimestamp(banner?.retrieval_completed_at);
  const updatedAt = suppliedTimestamp(banner?.source_updated_at);
  return {
    answerTypes: background
      ? ["General knowledge — not checked against FireLens sources"]
      : rejected
        ? [banner?.headline ?? "Support not established"]
        : unique([
          ...sections.map((section) => answerSectionAuthority(section.kind)),
          ...(banner?.headline ? [banner.headline] : []),
        ]),
    supportLabels: background ? [] : unique((response.claims ?? []).map((claim) => getClaimSupportLabel(response, claim))),
    sources: distinctSources,
    coverage,
    location: unique(location),
    // Copy and Why are the complete public snapshot. Compact layout may group
    // routine notes, but it cannot erase supplied authority/safety boundaries.
    limitations: unique(response.limitations ?? []),
    checks,
    ...(checkedAt ? { checkedAt } : {}),
    ...(updatedAt ? { updatedAt } : {}),
    canInspectEvidence: !background && (distinctSources.length > 0 || cards.length > 0),
  };
}

function copiedPassageSources(response: AskResponse, quote: string): string {
  const bound = sourcesForQuote(response, quote);
  if (!bound.length) return "Source attribution unavailable";
  return bound.map((source) => {
    const revisions = [...new Set((response.evidence ?? [])
      .filter((item) => item.canonical_url === source.canonical_url)
      .map((item) => item.document_sha256 ?? "unknown"))];
    // Distinguish retained revisions without copying internal hashes or IDs.
    const revision = revisions.length > 1
      ? ` · Retained revision ${revisions.indexOf(source.document_sha256 ?? "unknown") + 1}` : "";
    return `Source: ${source.title}${source.locator ? ` · ${source.locator}` : ""}${revision}\n${source.publisher} — ${source.canonical_url}`;
  }).join("\n");
}

/** Copy only the displayed answer and its public context, never the request/session object. */
export function formatAnswerForCopy(response: AskResponse, displayedText: string): string {
  const explanation = explainAnswer(response);
  const sections = getAnswerSections(response);
  const claims = response.claims ?? [];
  // QuoteOnlyAnswer displays claim text (including its expandable remainder),
  // which can differ from the response's combined answer prose.
  const quotes = claims.length > 0 && claims.every((claim) => claim.publication?.kind === "official_quote_only")
    ? claims.map((claim) => claim.text.trim()).filter(Boolean)
    : [];
  const groups = guidanceGroups(response);
  const answer = groups.length > 0
    ? groups.map(group => `${group.heading}\n${group.claims.map(claim => `${claim.publication?.kind === "official_quote_only" ? "Exact source wording" : "Reviewed guidance"}: ${readableAnswer(claim.text, claims, response.evidence)}\n${copiedPassageSources(response, claim.text)}`).join("\n")}`).join("\n\n")
    : sections.length > 0
    ? sections.map((section) => `${answerSectionAuthority(section.kind)}\n${section.heading}\n${readableAnswer(section.text, claims, response.evidence)}`).join("\n\n")
    : quotes.length > 0 ? quotes.map((quote) => `“${readableAnswer(quote, claims, response.evidence)}”\n${copiedPassageSources(response, quote)}`).join("\n\n") : readableAnswer(displayedText.trim(), claims, response.evidence);
  const parts = ["FireLens", answer];
  if (explanation.answerTypes.length > 0) parts.push(`Answer type: ${explanation.answerTypes.join("; ")}`);
  if (explanation.checkedAt) parts.push(`Checked by FireLens: ${explanation.checkedAt}`);
  if (explanation.updatedAt) parts.push(`Source updated: ${explanation.updatedAt}`);
  if (explanation.coverage.length > 0) parts.push(explanation.coverage.join("\n"));
  if (explanation.limitations.length > 0) parts.push(`Important limits\n${explanation.limitations.map((item) => `• ${item}`).join("\n")}`);
  if (explanation.sources.length > 0) {
    parts.push(`Sources\n${explanation.sources.map((source) => [
      `${source.publisher} — ${source.title}`,
      source.url,
      ...(source.checkedAt ? [`Checked by FireLens: ${source.checkedAt}`] : []),
      ...(source.updatedAt ? [`Source updated: ${source.updatedAt}`] : []),
    ].join("\n")).join("\n\n")}`);
  }
  return parts.filter(Boolean).join("\n\n");
}
