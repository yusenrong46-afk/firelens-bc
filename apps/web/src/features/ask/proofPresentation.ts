import type { AskResponse } from "../../shared/api/api";

export const GROUNDED_PUBLIC_WORDING =
  "Grounded in reviewed official sources with exact supporting quotations and automated critical-field checks.";

export const BCWS_MAP_URL = "https://wildfiresituation.nrs.gov.bc.ca/map";

export type SupportState =
  | "supported"
  | "structured_reviewed"
  | "official_live_typed"
  | "official_quote_only"
  | "source_linked_explanation"
  | "unknown"
  | "background"
  | "conflict"
  | "live_record";

export type StatusBannerView = {
  headline: string;
  detail: string;
  freshness_label: string;
  availability_label: string;
  retrieval_completed_at?: string | null;
  source_updated_at?: string | null;
  official_escalation_title?: string | null;
  official_escalation_url?: string | null;
};

export type ProofCardView = {
  claim_id: string;
  claim_text: string;
  support_state: SupportState;
  support_label: string;
  authority: string;
  exact_passage?: string | null;
  source_title?: string | null;
  source_revision?: string | null;
  review_state: string;
  critical_fields_checked: string;
  freshness: string;
  conflicts_or_unknowns?: string[];
  official_url?: string | null;
};

const HEADLINES: Record<string, string> = {
  grounded: "Grounded in reviewed official sources",
  partial: "Partially supported by reviewed sources",
  conflict: "Reviewed sources conflict",
  background: "General background — not corpus-checked",
  mixed: "Official records plus reviewed guidance",
  capability: "What you can ask FireLens",
  scope_redirect: "Outside FireLens live sources",
  abstention: "FireLens could not establish this",
  requires_input: "A BC place is needed to continue",
};

function liveHeadline(freshness: string | null | undefined): string {
  if (freshness === "stale") return "Official cached records";
  if (freshness === "mixed") return "Official records with mixed freshness";
  if (freshness === "fresh") return "Official current records";
  return "Official records";
}

const SUPPORT_LABELS: Record<SupportState, string> = {
  supported: "Supported by an exact reviewed quotation",
  structured_reviewed: "Reviewed structured claim",
  official_live_typed: "Official live record",
  official_quote_only: "Official wording — not paraphrased",
  source_linked_explanation: "Source-linked explanation",
  unknown: "Not established from FireLens sources",
  background: "General background — not a reviewed quotation",
  conflict: "Conflicting reviewed sources; no winner chosen",
  live_record: "Official live record as published",
};

function clip(text: string, limit = 200): string {
  const stripped = text.trim();
  return stripped.length <= limit ? stripped : `${stripped.slice(0, limit - 1).trimEnd()}…`;
}

function resultName(result: NonNullable<AskResponse["live_results"]>[number]): string {
  return result.name || result.incident_number || result.result_id;
}

function freshnessLabel(response: AskResponse): string {
  if (response.aggregate_freshness === "stale") return "Stale cached official records";
  if (response.aggregate_freshness === "mixed") return "Mixed freshness — check each record timestamp";
  if (response.aggregate_freshness === "fresh") return "Fresh official records";
  if ((response.evidence ?? []).length > 0) return "Stable reviewed guidance";
  return "Freshness not applicable";
}

function availabilityLabel(response: AskResponse): string {
  const layers = response.unavailable_layers ?? [];
  if (layers.length > 0) {
    return `Unavailable layers: ${layers.join(", ")}. That is not an all-clear.`;
  }
  if (response.status === "error" || response.response_mode === "abstention") {
    return "This request did not complete with established sources.";
  }
  return "Sources required for this request were available.";
}

function escalation(response: AskResponse): { title?: string; url?: string } {
  const link = response.related_links?.[0];
  if (link) return { title: link.title, url: link.url };
  const evidence = response.evidence?.[0];
  if (evidence) return { title: "Open official source", url: evidence.canonical_url };
  if ((response.live_results ?? []).length > 0) {
    return { title: "Open BCWS map", url: BCWS_MAP_URL };
  }
  return {};
}

function bannerDetail(response: AskResponse): string {
  const mode = response.response_mode ?? "abstention";
  if (mode === "grounded" || mode === "partial") return GROUNDED_PUBLIC_WORDING;
  if (mode === "conflict") {
    return "FireLens is showing both reviewed statements and cannot determine which version governs.";
  }
  if (mode === "background") {
    return "This explanation uses general model knowledge, not reviewed quotations.";
  }
  if (mode === "live") {
    return "These facts come from official BC wildfire records. This is not a safety determination.";
  }
  if (mode === "mixed") {
    return "Official records and reviewed guidance are labelled separately below.";
  }
  if (mode === "capability") {
    return "Ask about reviewed preparedness guidance or official BC wildfire records.";
  }
  if (mode === "requires_input") {
    return "FireLens needs a BC community or approximate location to continue this live request.";
  }
  if (mode === "scope_redirect") {
    return "Use the related official service for information FireLens does not ingest live.";
  }
  if (response.answer) return clip(response.answer, 500);
  return "FireLens could not produce a validated answer from the available evidence.";
}

export function getStatusBanner(response: AskResponse | undefined): StatusBannerView | undefined {
  if (!response) return undefined;
  const api = response.status_banner;
  if (api?.headline && api.detail) {
    return {
      headline: api.headline,
      detail: api.detail,
      freshness_label: api.freshness_label,
      availability_label: api.availability_label,
      retrieval_completed_at: api.retrieval_completed_at ?? null,
      source_updated_at: api.source_updated_at ?? null,
      official_escalation_title: api.official_escalation_title ?? null,
      official_escalation_url: api.official_escalation_url ?? null,
    };
  }
  const mode = response.response_mode ?? "abstention";
  const freshness = freshnessLabel(response);
  const headline =
    mode === "live"
      ? liveHeadline(response.aggregate_freshness)
      : HEADLINES[mode] ?? "FireLens response";
  const official = escalation(response);
  const retrieved = response.live_results?.map((item) => item.retrieved_at).filter(Boolean).sort().at(-1);
  const updated = response.live_results?.map((item) => item.source_updated_at).filter(Boolean).sort().at(-1);
  return {
    headline,
    detail: bannerDetail(response),
    freshness_label: freshness,
    availability_label: availabilityLabel(response),
    retrieval_completed_at: retrieved ?? null,
    source_updated_at: updated ?? null,
    official_escalation_title: official.title ?? null,
    official_escalation_url: official.url ?? null,
  };
}

export function getSupportChecklist(response: AskResponse | undefined): {
  supported: string[];
  unknown: string[];
} {
  if (!response) return { supported: [], unknown: [] };
  if ((response.supported_items?.length ?? 0) > 0 || (response.unknown_items?.length ?? 0) > 0) {
    return {
      supported: response.supported_items ?? [],
      unknown: response.unknown_items ?? [],
    };
  }
  const supported = [
    ...(response.claims ?? [])
      .filter((claim) => {
        const kind = claim.publication?.kind;
        return kind === "structured_reviewed" || kind === "official_live_typed";
      })
      .map((claim) => clip(claim.text)),
    ...(response.live_results ?? []).map((result) => clip(`${resultName(result)} (${result.kind})`)),
  ];
  const unknown = [
    ...(response.limitations ?? []).map((item) => clip(item)).filter(Boolean),
    ...(response.unavailable_layers ?? []).map((kind) => `Official ${kind} layer unavailable this turn`),
  ];
  return { supported: supported.slice(0, 12), unknown: [...new Set(unknown)].slice(0, 12) };
}

export function getProofCards(response: AskResponse | undefined): ProofCardView[] {
  if (!response) return [];
  if ((response.proof_cards?.length ?? 0) > 0) {
    return response.proof_cards ?? [];
  }
  const evidenceById = new Map((response.evidence ?? []).map((item) => [item.evidence_id, item]));
  const fromClaims = (response.claims ?? []).map((claim) => {
    const support = claim.supports?.[0];
    const evidence = support ? evidenceById.get(support.evidence_id) : undefined;
    const kind = claim.publication?.kind;
    const state: SupportState = response.response_mode === "conflict"
      ? "conflict"
      : kind === "structured_reviewed"
        ? "structured_reviewed"
        : kind === "official_live_typed"
          ? "official_live_typed"
          : kind === "official_quote_only"
            ? "official_quote_only"
            : kind === "source_linked_explanation"
              ? "source_linked_explanation"
              : claim.evidence_status === "general_background"
                ? "background"
                : "unknown";
    const trust = claim.trust;
    return {
      claim_id: claim.claim_id,
      claim_text: claim.text,
      support_state: state,
      support_label: SUPPORT_LABELS[state],
      authority: trust?.source_authority || evidence?.publisher || "FireLens reviewed sources",
      exact_passage: support?.quote ?? null,
      source_title: evidence?.title ?? null,
      source_revision: evidence?.locator ?? null,
      review_state: trust?.human_review_state === "human_verified_repair" || evidence?.review_provenance === "human_verified_repair"
        ? "Human-verified source transcription"
        : evidence
          ? "Native reviewed text"
          : "No reviewed passage attached",
      critical_fields_checked: trust?.critical_field_preservation === "preserved"
        ? "Critical fields checked and preserved"
        : trust?.critical_field_preservation === "failed"
          ? "Critical-field check failed"
          : "Not applicable",
      freshness: trust?.freshness === "stable_guidance" || !trust
        ? freshnessLabel(response)
        : String(trust.freshness),
      conflicts_or_unknowns: (response.limitations ?? []).slice(0, 4),
      official_url: evidence?.canonical_url ?? null,
    } satisfies ProofCardView;
  });
  if (fromClaims.length > 0) return fromClaims;
  return (response.live_results ?? []).map((result) => ({
    claim_id: result.result_id,
    claim_text: resultName(result),
    support_state: "live_record" as const,
    support_label: SUPPORT_LABELS.live_record,
    authority: result.authority,
    exact_passage: result.status ?? null,
    source_title: resultName(result),
    source_revision: result.source_updated_at,
    review_state: "Official live feed as published",
    critical_fields_checked: "Not applicable — live record, not a reviewed claim",
    freshness: result.freshness,
    conflicts_or_unknowns: [],
    official_url: result.source_url,
  }));
}
