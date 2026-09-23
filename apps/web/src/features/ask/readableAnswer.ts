import type { AskResponse } from "../../shared/api/api";

/** Layout only: use supplied claim boundaries, never infer or rewrite guidance. */
export function readableAnswer(text: string, claims: AskResponse["claims"] = [], evidence: AskResponse["evidence"] = []): string {
  let result = "";
  let cursor = 0;
  for (const claim of claims ?? []) {
    if (claim.publication?.kind !== "official_quote_only") continue;
    const source = claim.text;
    const markers = [...source.matchAll(/(?:^|\s)[¢•]\s+(?=[A-Za-z])/g)];
    const start = text.indexOf(source, cursor);
    if (start < 0) continue;
    let passage = source;
    const supportIds = new Set((claim.supports ?? []).map((support) => support.evidence_id));
    const locators = (evidence ?? []).filter((item) => supportIds.has(item.evidence_id)).map((item) => item.locator);
    const page = /^\s*(\d+)\s*\n/.exec(passage);
    // Remove only a leading folio corroborated by the cited page locator.
    // The original passage remains available in source inspection.
    if (page && locators.some((locator) => new RegExp(`^(?:PDF )?page[: ]${page[1]}$`, "i").test(locator ?? ""))) {
      passage = passage.slice(page[0].length);
    }
    if (markers.length === 0) {
      const formatted = passage.replace(/([A-Za-z])-\s*\n\s*(?=[a-z])/g, "$1-")
        .replace(/([^\n])\n(?!\n|[•¢*\-]\s)/g, "$1 ");
      result += text.slice(cursor, start) + formatted;
      cursor = start + source.length;
      continue;
    }
    // Keep real hyphens; remove only a PDF line wrap after a hyphen.
    const list = passage.replace(/([A-Za-z])-\s*\n\s*(?=[a-z])/g, "$1-")
      .replace(/(?:^|\s)[¢•]\s+(?=[A-Za-z])/g, "\n- ");
    result += text.slice(cursor, start) + "\n\n" + list.trim() + "\n\n";
    cursor = start + source.length;
  }
  return cursor ? (result + text.slice(cursor)).trim() : text;
}
