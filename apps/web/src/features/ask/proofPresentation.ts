import type { AskResponse } from "../../shared/api/api";

export const GROUNDED_PUBLIC_WORDING =
  "Based on reviewed official guidance, quoted exactly.";

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

export type TruthClass = "source_fact" | "deterministic_derivation" | "model_summary" | "unknown";
export type PublicationState = "verified" | "review" | "rejected";

export type DistanceDerivationView = {
  truth_class: TruthClass;
  publication_state: PublicationState;
  input_source_ids: string[];
  algorithm: string;
  crs: string;
  coordinate_order: string;
  units: string;
  calculated_at: string;
  validation_status: "valid" | "invalid";
  input_freshness?: string;
  distance_km: number;
  distance_basis: "incident_point" | "perimeter_boundary";
};

export const CANONICAL_DISTANCE_DERIVATION = {
  algorithm: "pyproj.Geod.inv WGS84 after shapely nearest_points",
  crs: "EPSG:4326",
  coordinate_order: "longitude_latitude",
  units: "km",
} as const;

const ALLOWED_FRESHNESS = new Set(["fresh", "stale"]);
const DERIVATION_CLOCK_SKEW_MS = 5 * 60 * 1000;
const KM_GEODESIC = /(\d+(?:\.\d+)?)\s*km\s+geodesic/gi;
const BASIS_LABELS: Record<DistanceDerivationView["distance_basis"], string> = {
  incident_point: "incident point",
  perimeter_boundary: "perimeter boundary",
};

export function freshnessToken(freshness?: string | null): string | null {
  if (freshness == null) return null;
  const token = String(freshness).trim().toLowerCase();
  return ALLOWED_FRESHNESS.has(token) ? token : null;
}

export function distanceWordingMatches(
  claimText: string,
  derivation: DistanceDerivationView | null | undefined,
): boolean {
  if (!/km geodesic/i.test(claimText)) return true;
  if (!derivation) return false;
  const quantities = [...claimText.matchAll(KM_GEODESIC)].map((match) => Number(match[1]));
  if (quantities.length === 0) return false;
  if (!quantities.some((value) => Math.abs(value - derivation.distance_km) <= 0.05)) {
    return false;
  }
  const text = claimText.toLowerCase();
  const mentionsBasis = text.includes("incident point") || text.includes("perimeter boundary");
  if (!mentionsBasis) return true;
  return text.includes(BASIS_LABELS[derivation.distance_basis]);
}

export function derivationCitesRecordAndPlace(ids: string[] | undefined): boolean {
  if (!ids?.length) return false;
  return ids.some((id) => id.startsWith("place:"))
    && ids.some((id) => !id.startsWith("place:"));
}

export function derivationPublicationState(options: {
  validationStatus: "valid" | "invalid";
  freshness?: string | null;
  inputSourceIds?: string[];
}): PublicationState {
  if (options.validationStatus !== "valid") return "rejected";
  if (freshnessToken(options.freshness) !== "fresh") return "review";
  if (options.inputSourceIds && !derivationCitesRecordAndPlace(options.inputSourceIds)) {
    return "review";
  }
  return "verified";
}

export function bindDistanceDerivation(
  derivation: DistanceDerivationView | null | undefined,
  input: { freshness?: string | null } = {},
): DistanceDerivationView | null {
  if (!derivation) return null;
  const canonical = derivation.crs === CANONICAL_DISTANCE_DERIVATION.crs
    && derivation.units === CANONICAL_DISTANCE_DERIVATION.units
    && derivation.coordinate_order === CANONICAL_DISTANCE_DERIVATION.coordinate_order
    && derivation.algorithm === CANONICAL_DISTANCE_DERIVATION.algorithm
    && derivation.input_source_ids.length > 0;
  const calculated = Date.parse(derivation.calculated_at);
  const future = Number.isFinite(calculated) && calculated > Date.now() + DERIVATION_CLOCK_SKEW_MS;
  const valid = derivation.validation_status === "valid" && canonical && !future;
  const freshness = "freshness" in input ? input.freshness : (derivation.input_freshness ?? null);
  const validation_status = valid ? "valid" as const : "invalid" as const;
  return {
    ...derivation,
    truth_class: "deterministic_derivation",
    input_freshness: freshnessToken(freshness) ?? "unknown",
    validation_status,
    publication_state: derivationPublicationState({
      validationStatus: validation_status,
      freshness,
      inputSourceIds: derivation.input_source_ids,
    }),
  };
}

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
  truth_class?: TruthClass;
  publication_state?: PublicationState;
  derivation?: DistanceDerivationView | null;
  publication?: {
    kind?: string | null;
    typed_claim_id?: string | null;
    typed_live_fact_id?: string | null;
    review_status?: string | null;
    source_revision_sha256?: string | null;
    source_span_sha256?: string | null;
    renderer_id?: string | null;
    support_provenance?: string | null;
    risk_tier?: string | null;
  } | null;
};

type Claim = NonNullable<AskResponse["claims"]>[number];
type ApiProofCard = NonNullable<AskResponse["proof_cards"]>[number];

function asProofCardView(card: ApiProofCard): ProofCardView {
  // Runtime JSON may still carry constructor authority; it is not a public OpenAPI field.
  return card as ProofCardView;
}

export function bindProofProfile(
  supportState: SupportState,
  options: { rejected?: boolean; freshness?: string | null } = {},
): { truth_class: TruthClass; publication_state: PublicationState } {
  const token = freshnessToken(options.freshness);
  if (options.rejected || supportState === "unknown") {
    return { truth_class: "unknown", publication_state: "rejected" };
  }
  if (supportState === "structured_reviewed" || supportState === "supported") {
    return { truth_class: "source_fact", publication_state: "verified" };
  }
  if (supportState === "official_live_typed" || supportState === "live_record") {
    if (token === "fresh") {
      return { truth_class: "source_fact", publication_state: "verified" };
    }
    return { truth_class: "source_fact", publication_state: "review" };
  }
  if (supportState === "official_quote_only") {
    return { truth_class: "source_fact", publication_state: "review" };
  }
  if (supportState === "source_linked_explanation" || supportState === "background") {
    return { truth_class: "model_summary", publication_state: "review" };
  }
  if (supportState === "conflict") {
    return { truth_class: "source_fact", publication_state: "review" };
  }
  return { truth_class: "unknown", publication_state: "rejected" };
}

function withProfile(card: ProofCardView, rejected = false): ProofCardView {
  const derivation = rejected
    ? null
    : bindDistanceDerivation(card.derivation, { freshness: card.freshness });
  if (!rejected && !distanceWordingMatches(card.claim_text, derivation)) {
    return unknownProofCard(card);
  }
  return {
    ...card,
    ...bindProofProfile(card.support_state, { rejected, freshness: card.freshness }),
    derivation,
  };
}

function unknownProofCard(card: ProofCardView): ProofCardView {
  return withProfile({
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
    derivation: null,
    publication: UNSUPPORTED_PUBLICATION,
  }, true);
}

const HEADLINES: Record<string, string> = {
  grounded: "From reviewed official guidance",
  partial: "Partly from reviewed guidance",
  conflict: "Official sources disagree",
  background: "General knowledge",
  mixed: "Official records and reviewed guidance",
  capability: "What you can ask FireLens",
  scope_redirect: "Not something FireLens tracks",
  abstention: "FireLens could not answer this from its sources",
  requires_input: "Name a B.C. place to continue",
};

function isValidRelatedLink(link: unknown): boolean {
  if (typeof link !== "object" || link === null) return false;
  const { title, url } = link as { title?: unknown; url?: unknown };
  if (typeof title !== "string" || title.trim().length === 0 || typeof url !== "string") return false;
  const trimmedUrl = url.trim();
  if (!trimmedUrl || /[\u0000-\u0020\u007f-\u009f]/.test(trimmedUrl)) return false;
  try {
    const parsed = new URL(trimmedUrl);
    return parsed.protocol === "https:" && Boolean(parsed.hostname) && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

function canonicalRelatedLink(
  response: Pick<AskResponse, "related_links"> | undefined,
): { title: string; url: string } | null {
  const link = response?.related_links?.[0];
  if (!isValidRelatedLink(link)) return null;
  if (link == null) return null;
  return {
    title: link.title.trim(),
    url: link.url.trim(),
  };
}

export function isReviewedSourceHandoff(
  response: Pick<AskResponse, "response_mode" | "reason_code" | "related_links"> | undefined,
): boolean {
  return response != null
    && response.response_mode === "scope_redirect"
    && response.reason_code === "no_approved_evidence"
    && canonicalRelatedLink(response) !== null;
}

function liveHeadline(freshness: string | null | undefined): string {
  if (freshness === "stale") return "Cached official records";
  if (freshness === "mixed") return "Official records, some out of date";
  if (freshness === "fresh") return "Current official records";
  return "Official records";
}

const SUPPORT_LABELS: Record<SupportState, string> = {
  supported: "Quoted from a reviewed source",
  structured_reviewed: "Reviewed official guidance",
  official_live_typed: "Official record",
  official_quote_only: "Exact wording from the source",
  source_linked_explanation: "Explanation linked to a source",
  unknown: "Not confirmed by FireLens sources",
  background: "General knowledge, not from a source",
  conflict: "Sources disagree",
  live_record: "Official record as published",
};

const KIND_SUPPORT_STATE: Record<string, SupportState> = {
  structured_reviewed: "structured_reviewed",
  official_live_typed: "official_live_typed",
  official_quote_only: "official_quote_only",
  source_linked_explanation: "source_linked_explanation",
  general_background: "background",
  unsupported: "unknown",
};

const UNSUPPORTED_PUBLICATION = {
  kind: "unsupported",
  review_status: "none",
  renderer_id: "none",
  support_provenance: "none",
} as const;

function livePublication(resultId: string) {
  return {
    kind: "official_live_typed" as const,
    typed_live_fact_id: resultId,
    review_status: "official_live_record",
    renderer_id: "firelens.live_typed_renderer.v1",
    support_provenance: "typed_official_live_fact",
    risk_tier: "B",
  };
}

function isOfficialLiveTyped(card: ProofCardView): boolean {
  return card.support_state === "official_live_typed" || card.publication?.kind === "official_live_typed";
}

function officialLiveIdMatchesBound(
  card: ProofCardView,
  boundId: string | null | undefined,
): boolean {
  if (!isOfficialLiveTyped(card)) return true;
  if (boundId == null) return false;
  const liveId = card.publication?.typed_live_fact_id;
  if (liveId != null) return liveId === boundId;
  return card.claim_id === boundId;
}

type PublicationAuthorityView = NonNullable<ProofCardView["publication"]>;

const PUBLICATION_AUTHORITY_FIELDS = [
  "kind",
  "typed_claim_id",
  "typed_live_fact_id",
  "review_status",
  "source_revision_sha256",
  "source_span_sha256",
  "renderer_id",
  "support_provenance",
  "risk_tier",
] as const;

type PublicationAuthorityField = (typeof PUBLICATION_AUTHORITY_FIELDS)[number];

function normalizedAuthorityValue(
  authority: PublicationAuthorityView | null | undefined,
  field: PublicationAuthorityField,
): string | null {
  const value = authority?.[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function hasRecognizedPublicationAuthority(
  authority: PublicationAuthorityView | null | undefined,
): authority is PublicationAuthorityView {
  const kind = normalizedAuthorityValue(authority, "kind");
  return kind != null && kind in KIND_SUPPORT_STATE;
}

/**
 * Publication authority is an identity, not a display category.  A proof card
 * may reuse a claim's authority only when every field is identical after
 * normalising absent optional fields to null.  Comparing only `kind` would let
 * a stale source revision, review decision, or renderer look authoritative.
 */
function publicationAuthoritiesEqual(
  left: PublicationAuthorityView | null | undefined,
  right: PublicationAuthorityView | null | undefined,
): boolean {
  if (!hasRecognizedPublicationAuthority(left) || !hasRecognizedPublicationAuthority(right)) {
    return false;
  }
  return PUBLICATION_AUTHORITY_FIELDS.every(
    (field) => normalizedAuthorityValue(left, field) === normalizedAuthorityValue(right, field),
  );
}

function cardAuthorityMatchesClaim(card: ProofCardView, claim: Claim): boolean {
  if (!publicationAuthoritiesEqual(card.publication, claim.publication)) return false;
  if (claim.publication?.kind === "official_live_typed") {
    return officialLiveIdMatchesBound(card, claim.publication?.typed_live_fact_id ?? claim.claim_id);
  }
  return true;
}

export function getClaimSupportState(response: AskResponse, claim: Claim): SupportState {
  if (response.validation?.accepted === false) return "unknown";
  if (claim.trust?.critical_field_preservation === "failed") return "unknown";
  const kind = String(claim.publication?.kind ?? "");
  return KIND_SUPPORT_STATE[kind] ?? "unknown";
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
      headline: "Reviewed guidance plus exact source wording",
      detail: "Reviewed guidance and exact source wording are labelled separately.",
      freshness_label: "Stable guidance and source wording",
    };
  }
  if (hasQuoteOnly && states.every((state) => state === "official_quote_only")) {
    return {
      headline: "Exact wording from an official source",
      detail: "FireLens is showing the source's own words rather than a summary.",
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
      headline: hasReviewed ? "Reviewed guidance with unconfirmed content" : "Not confirmed by FireLens sources",
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
  if (response.aggregate_freshness === "stale") return "Cached official records; the live refresh failed";
  if (response.aggregate_freshness === "mixed") return "Some records are out of date; check each record's time";
  if (response.aggregate_freshness === "fresh") return "Current official records";
  if ((response.evidence ?? []).length > 0) return "Stable reviewed guidance";
  return "Does not change day to day";
}

function availabilityLabel(response: AskResponse): string {
  const layers = response.unavailable_layers ?? [];
  if (layers.length > 0) {
    return `Unavailable layers: ${layers.join(", ")}. That is not an all-clear.`;
  }
  if (response.status === "error" || response.response_mode === "abstention") {
    return "FireLens could not reach the sources this needed.";
  }
  return "The sources this needed were available.";
}

function escalation(response: AskResponse): { title?: string; url?: string } {
  const link = canonicalRelatedLink(response);
  if (link) return link;
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
    return "These facts come from official B.C. wildfire records. This is not a safety assessment.";
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
    if (response.reason_code === "live_data_required") {
      return "Click a fire on the map or name a British Columbia community, then ask again.";
    }
    if (isReviewedSourceHandoff(response)) {
      return "Open the source for its exact wording.";
    }
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
      headline: "Not confirmed by FireLens sources",
      detail: "FireLens did not establish or validate support for this response.",
      freshness_label: "Freshness not established",
      availability_label: "FireLens could not reach the sources this needed.",
      retrieval_completed_at: retrieved ?? null,
      source_updated_at: updated ?? null,
      official_escalation_title: official.title ?? null,
      official_escalation_url: official.url ?? null,
    };
  }
  const authority = publicationBanner(response);
  const selectionNeeded =
    response.response_mode === "scope_redirect"
    && response.reason_code === "live_data_required";
  const reviewedSourceHandoff = isReviewedSourceHandoff(response);
  if (api?.headline && api.detail) {
    return {
      headline: authority?.headline
        ?? (selectionNeeded
          ? "Select an official record to continue"
          : reviewedSourceHandoff
            ? "The reviewed source does not directly answer this"
            : api.headline),
      detail: authority?.detail
        ?? (selectionNeeded
          ? "Click a fire on the map or name a British Columbia community, then ask again."
          : reviewedSourceHandoff
            ? "Open the source for its exact wording."
            : api.detail),
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
      : mode === "scope_redirect" && response.reason_code === "live_data_required"
        ? "Select an official record to continue"
        : reviewedSourceHandoff
          ? "The reviewed source does not directly answer this"
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

function rebindLiveProofCard(
  card: ProofCardView,
  liveResults: NonNullable<AskResponse["live_results"]>,
): ProofCardView {
  if (card.support_state !== "live_record" && card.support_state !== "official_live_typed") {
    return card;
  }
  const byId = liveResults.find((result) => result.result_id === card.claim_id);
  const byLiveFact = liveResults.find((result) => result.result_id === card.publication?.typed_live_fact_id);
  const byDerivation = isOfficialLiveTyped(card)
    ? undefined
    : liveResults.find((result) => card.derivation?.input_source_ids?.includes(result.result_id));
  const live = byId ?? byLiveFact ?? byDerivation;
  if (!live) {
    return isOfficialLiveTyped(card) ? unknownProofCard(card) : card;
  }
  if (!officialLiveIdMatchesBound(card, live.result_id)) {
    return unknownProofCard(card);
  }
  return {
    ...card,
    freshness: live.freshness,
    official_url: live.source_url,
    exact_passage: live.status ?? card.exact_passage ?? null,
    authority: live.authority,
    derivation: live.distance_derivation ?? card.derivation ?? null,
    publication: card.publication ?? livePublication(live.result_id),
  };
}

function claimProofCard(
  response: AskResponse,
  claim: Claim,
  evidenceById: Map<string, NonNullable<AskResponse["evidence"]>[number]>,
): ProofCardView {
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
    publication: claim.publication ?? UNSUPPORTED_PUBLICATION,
  };
}

function canRebuildClaimProofCard(
  response: AskResponse,
  claim: Claim,
  evidenceById: Map<string, NonNullable<AskResponse["evidence"]>[number]>,
): boolean {
  const publication = claim.publication;
  if (!hasRecognizedPublicationAuthority(publication) || getClaimSupportState(response, claim) === "unknown") {
    return false;
  }
  if (
    normalizedAuthorityValue(publication, "review_status") == null
    || normalizedAuthorityValue(publication, "renderer_id") == null
    || normalizedAuthorityValue(publication, "support_provenance") == null
  ) {
    return false;
  }
  if (publication.kind === "official_live_typed") {
    const liveId = normalizedAuthorityValue(publication, "typed_live_fact_id");
    return liveId != null && (response.live_results ?? []).some((result) => result.result_id === liveId);
  }
  if (publication.kind === "general_background") return true;
  const support = claim.supports?.[0];
  return support != null && evidenceById.has(support.evidence_id) && Boolean(support.quote?.trim());
}

export function getProofCards(response: AskResponse | undefined): ProofCardView[] {
  if (!response) return [];
  const liveResults = response.live_results ?? [];
  const evidenceById = new Map((response.evidence ?? []).map((item) => [item.evidence_id, item]));
  const projectValidation = (card: ProofCardView) =>
    response.validation?.accepted === false || card.support_state === "unknown"
      ? unknownProofCard(card)
      : withProfile(rebindLiveProofCard(card, liveResults));
  if ((response.proof_cards?.length ?? 0) > 0) {
    const claims = response.claims ?? [];
    const claimsById = new Map(claims.map((claim) => [claim.claim_id, claim]));
    const validCardIds = new Set(
      claims.length > 0
        ? claims.map((claim) => claim.claim_id)
        : (response.live_results ?? []).map((result) => result.result_id),
    );
    return (response.proof_cards ?? []).filter((card) => validCardIds.has(card.claim_id)).map((card) => {
      const view = asProofCardView(card);
      const claim = claimsById.get(view.claim_id);
      if (!claim) {
        const bound = liveResults.find((result) => result.result_id === view.claim_id)
          ?? liveResults.find((result) => result.result_id === view.publication?.typed_live_fact_id);
        if (isOfficialLiveTyped(view) && !officialLiveIdMatchesBound(view, bound?.result_id)) {
          return unknownProofCard(view);
        }
        return projectValidation(view);
      }
      const state = getClaimSupportState(response, claim);
      if (state === "unknown" || !cardAuthorityMatchesClaim(view, claim)) {
        return state === "unknown"
          ? unknownProofCard({ ...view, claim_text: claim.text })
          : canRebuildClaimProofCard(response, claim, evidenceById)
            ? projectValidation(claimProofCard(response, claim, evidenceById))
            : unknownProofCard({ ...view, claim_text: claim.text });
      }
      return projectValidation({
        ...view,
        support_state: state,
        support_label: SUPPORT_LABELS[state],
        review_state: state === "official_quote_only"
          ? "Source extraction only; no structured-claim review"
          : view.review_state,
        freshness: state === "official_quote_only" ? "Stable source wording" : view.freshness,
        publication: claim.publication ?? view.publication ?? UNSUPPORTED_PUBLICATION,
      });
    });
  }
  const fromClaims = (response.claims ?? []).map((claim) => claimProofCard(response, claim, evidenceById));
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
    derivation: result.distance_derivation ?? null,
    publication: livePublication(result.result_id),
  }));
}
