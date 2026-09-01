import type { AskResponse } from "../../shared/api/api";
import {
  ClaimEvidence,
  NonSelectableClaim,
  PreparednessSources,
} from "./ConversationPresentation";
import { getClaimSupportLabel, getClaimSupportState } from "./proofPresentation";
import type { Claim, Evidence } from "./responseModel";

const PRESENTABLE_STATES = new Set([
  "supported",
  "structured_reviewed",
  "official_quote_only",
  "source_linked_explanation",
  "conflict",
]);

export function ConversationEvidenceDetails({
  allClaimsQuoteOnly,
  claims,
  onReviewEvidence,
  response,
}: {
  allClaimsQuoteOnly: boolean;
  claims: Claim[];
  onReviewEvidence: (index: number) => void;
  response: AskResponse;
}) {
  const evidenceById = new Map((response.evidence ?? []).map((item) => [item.evidence_id, item]));
  const presentableEvidence = (response.evidence ?? []).flatMap((item) => {
    const linkedClaim = claims.find((claim) => claim.supports?.some((support) => support.evidence_id === item.evidence_id));
    if (!linkedClaim) return [];
    const state = getClaimSupportState(response, linkedClaim);
    if (!PRESENTABLE_STATES.has(state)) return [];
    return [{ item, state }];
  });

  return (
    <details className="answer-details">
      <summary>Sources and technical evidence</summary>
      <div className="claim-group">
        <span className="panel-label">Answer evidence and support</span>
        <div className="claim-list">
          {claims.map((claim, index) => {
            const state = getClaimSupportState(response, claim);
            const supportLabel = getClaimSupportLabel(response, claim);
            const showSource = PRESENTABLE_STATES.has(state);
            const hasLinkedEvidence = claim.supports?.some((support) => evidenceById.has(support.evidence_id)) ?? false;
            const canReview = showSource || hasLinkedEvidence || state === "official_live_typed";
            return canReview ? (
              <ClaimEvidence
                key={claim.claim_id}
                claim={claim}
                index={index}
                supportLabel={supportLabel}
                evidence={showSource && claim.supports?.[0] ? evidenceById.get(claim.supports[0].evidence_id) as Evidence | undefined : undefined}
                showSource={showSource}
                onReviewEvidence={() => onReviewEvidence(index)}
              />
            ) : (
              <NonSelectableClaim
                key={claim.claim_id}
                claim={claim}
                index={index}
                supportLabel={supportLabel}
              />
            );
          })}
        </div>
      </div>
      {!allClaimsQuoteOnly && <PreparednessSources evidence={presentableEvidence} />}
    </details>
  );
}
