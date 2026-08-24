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

function unknownProofCard(card: ProofCardView): ProofCardView {
  return {
    ...card,
    support_state: "unknown",
    support_label: SUPPORT_LABELS.unknown,
    authority: "Authority not established",
    exact_passage: null,
    source_title: null,
    source_revision: null,
    review_state: "Review state not established",
    critical_fields_checked: "Critical-field validation not established",
    freshness: "Freshness not established",
    official_url: null,
  };
}

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
  official_quote_only: "Exact source wording — not a structured FireLens claim",
  source_linked_explanation: "Source-linked explanation",
  unknown: "Not established from FireLens sources",
  background: "General background — not a reviewed quotation",
  conflict: "Conflicting reviewed sources; no winner chosen",
  live_record: "Official live record as published",
};

type Claim = NonNullable<AskResponse["claims"]>[number];

export function getClaimSupportState(response: AskResponse, claim: Claim): SupportState {
  if (response.validation?.accepted === false) return "unknown";
  if (claim.trust?.critical_field_preservation === "failed") return "unknown";

  const kind = claim.publication?.kind;
  if (kind === "structured_reviewed") {
    return response.response_mode === "conflict" ? "conflict" : "structured_reviewed";
  }
  if (kind === "official_live_typed") return "official_live_typed";
  if (kind === "official_quote_only") return "official_quote_only";
  if (kind === "source_linked_explanation") return "source_linked_explanation";
  if (kind === "general_background") return "background";
  if (kind === "unsupported") return "unknown";

  // Compatibility for older responses that predate publication authority.
  if (response.response_mode === "conflict") return "conflict";
  if (claim.evidence_status === "verified_corpus" && (claim.supports?.length ?? 0) > 0) {
    return "supported";
  }
  if (claim.evidence_status === "general_background") return "background";
  return "unknown";
}

export function getClaimSupportLabel(response: AskResponse, claim: Claim): string {
  return SUPPORT_LABELS[getClaimSupportState(response, claim)];
}

function publicationBanner(response: AskResponse): Pick<
  StatusBannerView,
  "headline" | "detail" | "freshness_label"
> | undefined {
  const states = (response.claims ?? []).map((claim) => getClaimSupportState(response, claim));
  if (states.length === 0) return undefined;
  const hasReviewed = states.some((state) =>
    state === "structured_reviewed" || state === "official_live_typed" || state === "supported"
  );
  const hasQuoteOnly = states.includes("official_quote_only");
  const hasSourceLinked = states.includes("source_linked_explanation");
  const hasUnknown = states.includes("unknown");

  if (hasQuoteOnly && hasReviewed) {
    return {
      headline: "Reviewed claims plus source wording",
      detail: "Reviewed structured claims and extraction-only source wording are labelled separately.",
      freshness_label: "Stable guidance and source wording",
    };
  }
  if (hasQuoteOnly && states.every((state) => state === "official_quote_only")) {
    return {
      headline: "Official wording from a source",
      detail: "FireLens is showing an exact source quotation. It has not been approved as a structured FireLens claim.",
      freshness_label: "Stable source wording",
    };
  }
  if (hasQuoteOnly) {
    return {
      headline: "Source wording with unreviewed content",
      detail: "Exact source wording and content without structured FireLens approval are labelled separately.",
      freshness_label: "Source wording and unresolved content",
    };
  }
  if (hasSourceLinked) {
    return {
      headline: hasReviewed ? "Reviewed claims plus a source-linked explanation" : "Source-linked explanation",
      detail: hasReviewed
        ? "Reviewed structured claims and a source-linked explanation are labelled separately."
        : "This explanation links to source material but is not a reviewed structured FireLens claim.",
      freshness_label: hasReviewed ? "Stable guidance and linked source material" : "Linked source material",
    };
  }
  if (hasUnknown) {
    return {
      headline: hasReviewed ? "Reviewed claims with unresolved content" : "Support not established",
      detail: hasReviewed
        ? "Reviewed claims and content not established from FireLens sources are labelled separately."
        : "FireLens did not establish this content from its reviewed or official sources.",
      freshness_label: hasReviewed ? "Stable guidance with unresolved content" : "Freshness unknown",
    };
  }
  return undefined;
}

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
  if (response.validation?.accepted === false) {
    const official = api?.official_escalation_title && api.official_escalation_url
      ? { title: api.official_escalation_title, url: api.official_escalation_url }
      : escalation(response);
    const retrieved = response.live_results?.map((item) => item.retrieved_at).filter(Boolean).sort().at(-1);
    const updated = response.live_results?.map((item) => item.source_updated_at).filter(Boolean).sort().at(-1);
    return {
      headline: "Support not established",
      detail: "FireLens did not establish or validate support for this response.",
      freshness_label: "Freshness not established",
      availability_label: "This request did not complete with established sources.",
      retrieval_completed_at: retrieved ?? null,
      source_updated_at: updated ?? null,
      official_escalation_title: official.title ?? null,
      official_escalation_url: official.url ?? null,
    };
  }
  const authority = publicationBanner(response);
  if (api?.headline && api.detail) {
    return {
      headline: authority?.headline ?? api.headline,
      detail: authority?.detail ?? api.detail,
      freshness_label: authority?.freshness_label ?? api.freshness_label,
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
    headline: authority?.headline ?? headline,
    detail: authority?.detail ?? bannerDetail(response),
    freshness_label: authority?.freshness_label ?? freshness,
    availability_label: availabilityLabel(response),
    retrieval_completed_at: retrieved ?? null,
    source_updated_at: updated ?? null,
    official_escalation_title: official.title ?? null,
    official_escalation_url: official.url ?? null,
  };
}

export function getProofCards(response: AskResponse | undefined): ProofCardView[] {
  if (!response) return [];
  const projectValidation = (card: ProofCardView) =>
    response.validation?.accepted === false || card.support_state === "unknown"
      ? unknownProofCard(card)
      : card;
  if ((response.proof_cards?.length ?? 0) > 0) {
    const claims = response.claims ?? [];
    const claimsById = new Map(claims.map((claim) => [claim.claim_id, claim]));
    const validCardIds = new Set(
      claims.length > 0
        ? claims.map((claim) => claim.claim_id)
        : (response.live_results ?? []).map((result) => result.result_id),
    );
    return (response.proof_cards ?? []).filter((card) => validCardIds.has(card.claim_id)).map((card) => {
      const claim = claimsById.get(card.claim_id);
      if (!claim) return projectValidation(card);
      const state = getClaimSupportState(response, claim);
      return projectValidation({
        ...card,
        support_state: state,
        support_label: SUPPORT_LABELS[state],
        review_state: state === "official_quote_only"
          ? "Source extraction only; no structured-claim review"
          : card.review_state,
        freshness: state === "official_quote_only" ? "Stable source wording" : card.freshness,
      });
    });
  }
  const evidenceById = new Map((response.evidence ?? []).map((item) => [item.evidence_id, item]));
  const fromClaims = (response.claims ?? []).map((claim) => {
    const support = claim.supports?.[0];
    const evidence = support ? evidenceById.get(support.evidence_id) : undefined;
    const state = getClaimSupportState(response, claim);
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
      review_state: state === "official_quote_only"
        ? "Source extraction only; no structured-claim review"
        : trust?.human_review_state === "human_verified_repair" || evidence?.review_provenance === "human_verified_repair"
        ? "Human-verified source transcription"
        : evidence
          ? "Native reviewed text"
          : "No reviewed passage attached",
      critical_fields_checked: trust?.critical_field_preservation === "preserved"
        ? "Critical fields checked and preserved"
        : trust?.critical_field_preservation === "failed"
          ? "Critical-field check failed"
          : "Not applicable",
      freshness: state === "official_quote_only"
        ? "Stable source wording"
        : trust?.freshness === "stable_guidance" || !trust
        ? freshnessLabel(response)
        : String(trust.freshness),
      conflicts_or_unknowns: (response.limitations ?? []).slice(0, 4),
      official_url: evidence?.canonical_url ?? null,
    } satisfies ProofCardView;
  });
  if (fromClaims.length > 0) return fromClaims.map(projectValidation);
  return (response.live_results ?? []).map((result) => projectValidation({
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
