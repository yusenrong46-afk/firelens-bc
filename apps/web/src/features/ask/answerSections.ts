import type {
  AnswerSection,
  AnswerSectionKind,
  AskResponse,
} from "../../shared/api/api";

const SECTION_KINDS = new Set<AnswerSectionKind>([
  "current_records",
  "reviewed_guidance",
  "conflicting_guidance",
  "general_background",
  "official_handoff",
  "uncertainty",
]);

const AUTHORITY_LABELS: Record<AnswerSectionKind, string> = {
  current_records: "Official current records",
  reviewed_guidance: "Reviewed guidance",
  conflicting_guidance: "Conflicting reviewed sources",
  general_background: "General background",
  official_handoff: "Official next step",
  uncertainty: "What FireLens cannot establish",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function getAnswerSections(response: AskResponse | undefined): AnswerSection[] {
  const raw: unknown = response?.answer_sections;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is AnswerSection => (
    isRecord(item)
    && typeof item.kind === "string"
    && SECTION_KINDS.has(item.kind as AnswerSectionKind)
    && typeof item.heading === "string"
    && item.heading.trim().length > 0
    && typeof item.text === "string"
    && item.text.trim().length > 0
  ));
}

export function answerSectionAuthority(kind: AnswerSectionKind): string {
  return AUTHORITY_LABELS[kind];
}
