// A stored selection stays attached only when the question clearly refers to
// it: a deictic reference ("this fire", "its size") or a short elliptical
// attribute question ("status?", "how large?"). Broad-subject questions
// ("status of fires across the province") must not inherit a stale selection.
const DEICTIC_FOLLOW_UP = /\b(?:this|that|it|its|selected)\b/i;
const BROAD_SUBJECT =
  /\b(?:fires|wildfires|perimeters|evacuations?|orders|alerts|province|province-wide|bc|british columbia|near|around|map)\b/i;
const SHORT_ATTRIBUTE_FOLLOW_UP =
  /^(?:and\s+)?(?:what(?:'s|\s+is)\s+(?:the\s+)?)?(?:status|size|source|how\s+(?:large|big|far|close|old))\b[\s\S]{0,30}$/i;
const REFORMAT_FOLLOW_UP =
  /^\s*(?:please\s+)?(?:give|show|put)\s+(?:me\s+)?(?:the\s+)?answer\s+first(?:,?\s+then\s+(?:the\s+)?evidence)?[.!?]*\s*$/i;

type LiveResultReference = {
  result_id: string;
  kind?: string;
  name?: string | null;
  incident_number?: string | null;
};

function normalizedIdentity(value: string): string {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
}

function explicitVisibleResultId(
  question: string,
  availableResults: readonly LiveResultReference[],
): string | undefined {
  const match = /^\s*where(?:\s+is|['’]s)\s+(?:the\s+)?(.+?)[?.!]*\s*$/i.exec(question);
  if (!match) return undefined;
  const requested = normalizedIdentity(match[1] ?? "");
  if (!requested) return undefined;
  const matches = availableResults.filter((result) => {
    const identities = [result.name, result.incident_number]
      .filter((value): value is string => Boolean(value))
      .map(normalizedIdentity);
    return identities.includes(requested);
  });
  if (matches.length === 0) return undefined;
  const incidents = matches.filter((result) => result.kind === "incident");
  if (incidents.length === 1) return incidents[0]?.result_id;
  if (incidents.length > 1) return undefined;
  return matches.length === 1 ? matches[0]?.result_id : undefined;
}

export function selectedResultIdForQuestion(
  question: string,
  selectedId: string | undefined,
  override?: string,
  availableResults: readonly LiveResultReference[] = [],
): string | undefined {
  if (override) return override;
  const trimmed = question.trim();
  const explicit = explicitVisibleResultId(trimmed, availableResults);
  if (explicit) return explicit;
  // Positions ("the second one") are resolved by the server against the roster
  // sent as visible_live_result_ids, so the client never guesses them here.
  if (!selectedId) return undefined;
  if (DEICTIC_FOLLOW_UP.test(trimmed)) return selectedId;
  if (REFORMAT_FOLLOW_UP.test(trimmed)) return selectedId;
  if (BROAD_SUBJECT.test(trimmed)) return undefined;
  return SHORT_ATTRIBUTE_FOLLOW_UP.test(trimmed) ? selectedId : undefined;
}

export function looksLikeCommunityLabel(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || trimmed.includes("?")) return false;
  if (trimmed.split(/\s+/).length > 6) return false;
  return !/\b(?:fire|wildfire|evacuate|kit|grab-and-go|what|why|how|should)\b/i.test(trimmed);
}
