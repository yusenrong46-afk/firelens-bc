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

export function selectedResultIdForQuestion(
  question: string,
  selectedId: string | undefined,
  override?: string,
): string | undefined {
  if (override) return override;
  if (!selectedId) return undefined;
  const trimmed = question.trim();
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
