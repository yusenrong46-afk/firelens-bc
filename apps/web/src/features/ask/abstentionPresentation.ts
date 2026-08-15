import type { AskResponse } from "../../shared/api/api";

type ReasonCode = NonNullable<AskResponse["reason_code"]>;

export type AbstentionPresentation = {
  badge: string;
  title: string;
  summary: string;
  linkLead: string;
};

const DEFAULT_PRESENTATION: AbstentionPresentation = {
  badge: "Answer boundary",
  title: "No evidence-backed answer",
  summary: "FireLens did not present guidance that it could not support or safely provide.",
  linkLead: "Open a related official source when one is provided.",
};

const PRESENTATIONS: Partial<Record<ReasonCode, AbstentionPresentation>> = {
  personalized_safety_decision: {
    badge: "Personal safety boundary",
    title: "Personal safety decision boundary",
    summary: "FireLens cannot decide whether you should stay, leave, evacuate, return, or which route is safest. Follow instructions from the issuing authority.",
    linkLead: "Related official sources can provide current orders or notices; they do not make a personal safety decision.",
  },
  personalized_medical_advice: {
    badge: "Medical advice boundary",
    title: "Personal medical advice boundary",
    summary: "FireLens cannot diagnose symptoms or recommend personal treatment. Contact a qualified healthcare professional, or emergency services when urgent.",
    linkLead: "Related official health sources provide general information, not a personal diagnosis.",
  },
  policy_manipulation: {
    badge: "Safety rules preserved",
    title: "Safety and evidence boundary",
    summary: "Conversation text cannot override FireLens safety, privacy, source, or evidence rules.",
    linkLead: "Open a related official source when one is provided.",
  },
  live_data_required: {
    badge: "Current source unavailable",
    title: "Current source unavailable",
    summary: "FireLens could not establish the requested current status from its available official sources.",
    linkLead: "Open the related official source for the current status.",
  },
  conflicting_evidence: {
    badge: "Conflicting evidence",
    title: "Reviewed sources conflict",
    summary: "The available reviewed sources conflict, so FireLens did not turn them into one apparently certain answer.",
    linkLead: "Open the related official source when one is provided.",
  },
};

export function abstentionPresentation(
  reasonCode: AskResponse["reason_code"] | undefined,
): AbstentionPresentation {
  return reasonCode ? (PRESENTATIONS[reasonCode] ?? DEFAULT_PRESENTATION) : DEFAULT_PRESENTATION;
}
