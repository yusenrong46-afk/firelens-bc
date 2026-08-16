const SELECTED_FOLLOW_UP =
  /\b(?:this|that|it|its|selected|source|status|size|how large|how far|how close)\b/i;

export function selectedResultIdForQuestion(
  question: string,
  selectedId: string | undefined,
  override?: string,
): string | undefined {
  if (override) return override;
  if (!selectedId) return undefined;
  return SELECTED_FOLLOW_UP.test(question) ? selectedId : undefined;
}

export function looksLikeCommunityLabel(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || trimmed.includes("?")) return false;
  if (trimmed.split(/\s+/).length > 6) return false;
  return !/\b(?:fire|wildfire|evacuate|kit|grab-and-go|what|why|how|should)\b/i.test(trimmed);
}
