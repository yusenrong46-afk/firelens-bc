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

type LiveResultReference = { result_id: string };

const ORDINAL_WORDS: Record<string, number> = {
  first: 0,
  second: 1,
  third: 2,
};
const ORDINAL_TOKEN = "(?:first|second|third|[1-9]\\d*(?:st|nd|rd|th)?)";
const ORDINAL_REFERENCE = new RegExp(
  `(?:\\b(?:the\\s+)?(${ORDINAL_TOKEN})\\s+(?:one|fire|wildfire|record|incident|perimeter|evacuation)s?\\b|\\b(?:the\\s+)?(${ORDINAL_TOKEN})(?=\\s*(?:[?.!]|$))|\\b(?:number|no\\.?)\\s*#?\\s*(${ORDINAL_TOKEN})\\b|#\\s*(${ORDINAL_TOKEN})\\b)`,
  "i",
);

function ordinalIndex(question: string): number | undefined {
  const match = ORDINAL_REFERENCE.exec(question);
  if (!match) return undefined;
  const token = [match[1], match[2], match[3], match[4]].find(Boolean);
  if (!token) return undefined;
  const normalized = token.toLowerCase();
  if (normalized in ORDINAL_WORDS) return ORDINAL_WORDS[normalized];
  const numeric = Number.parseInt(normalized.replace(/(?:st|nd|rd|th)$/i, ""), 10);
  return Number.isSafeInteger(numeric) && numeric > 0 ? numeric - 1 : undefined;
}

export function selectedResultIdForQuestion(
  question: string,
  selectedId: string | undefined,
  override?: string,
  availableResults: readonly LiveResultReference[] = [],
): string | undefined {
  if (override) return override;
  const trimmed = question.trim();
  const ordinal = ordinalIndex(trimmed);
  // An explicit ordinal takes precedence over a prior selection. If it cannot
  // be resolved in the visible roster, fail closed rather than falling back to
  // a stale selected record.
  if (ordinal !== undefined) return availableResults[ordinal]?.result_id;
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
