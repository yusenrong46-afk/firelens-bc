import type { AskResponse } from "../../shared/api/api";

type Claim = NonNullable<AskResponse["claims"]>[number];
export type GuidanceGroup = { heading: string; claims: Claim[] };

/** Labels for supplied content only. No question parsing, rewriting, or new authority. */
export function guidanceGroups(response: AskResponse): GuidanceGroup[] {
  const claims = response.claims ?? [];
  if (claims.length < 2 || response.answer_sections?.length
    || claims.some(c => !["official_quote_only", "structured_reviewed"].includes(c.publication?.kind ?? ""))) return [];
  const evidence = response.evidence ?? [];
  const bound = claims.flatMap(c => (c.supports ?? []).map(s => evidence.find(e => e.evidence_id === s.evidence_id)));
  if (claims.some(c => !c.supports?.length) || bound.some(e => !e?.document_sha256)) return [];
  // Never join labels across source revisions or repair a broken source reference.
  if (new Set(bound.map(e => `${e!.canonical_url}\n${e!.document_sha256}`)).size !== 1) return [];
  const text = (c: Claim) => c.text.toLowerCase().replace(/\s+/g, " ");
  const groups = (headings: string[], classify: (c: Claim) => number) => {
    const entries = headings.map(heading => ({ heading, claims: [] as Claim[] }));
    for (const claim of claims) {
      const index = classify(claim);
      if (index < 0) return [];
      entries[index]!.claims.push(claim);
    }
    return entries.every(e => e.claims.length) ? entries : [];
  };
  if (bound.every(e => e!.title === "FireSmart BC Information Guide and Key Messaging")) {
    return groups(["Home Partners — property-specific assessment", "General FireSmart guidance — published tasks"], c => {
      const t = text(c);
      if (t.includes("home partners") && t.includes("professional home assessment") && t.includes("property-specific")) return 0;
      if (t.includes("simple firesmart tasks") && t.includes("scientific research")) return 1;
      return -1;
    });
  }
  if (bound.some(e => /Water Use, Structure Protection and FireSmart/.test(e!.title))) {
    return groups(["Installation", "During evacuation", "Why timing matters"], c => {
      const t = text(c);
      if (/pre-emptively/.test(t) && t.includes("first responders") && !t.includes("if you have installed")) return 2;
      if (t.includes("if you have installed") || t.includes("follow official evacuation alerts and orders")) return 1;
      if (t.includes("install") && (t.includes("does not recommend") || t.includes("uninsurable water") || t.includes("technical expertise"))) return 0;
      return -1;
    });
  }
  return [];
}
