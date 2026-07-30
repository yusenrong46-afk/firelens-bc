# FireLens BC V1.5 release-review handoff

Updated: 2026-07-30 (America/Vancouver)

This handoff separates executed evidence from gates that still require paid provider access,
a named human reviewer, or an owner-approved external change. It does not authorize a merge or
production deployment.

## Current candidate

- Branch: `maintenance/v1-5-principal-remediation`
- Retrieval strategy: `metadata_context_v1`
- Runtime provider boundary: OpenRouter only
- Public API: unchanged
- Production: unchanged

## Executed locally

- The permanent hard-probe runner completes all 105 cases in `offline` mode with an explicit
  zero-dollar ceiling.
- Result: `105/105`, zero network calls, zero reported cost.
- The V2 sealed retrieval packet can be generated entirely from governed corpus chunks.
- Focused hard-probe, retrieval-review, and frozen-qualification tests pass.
- The enforced Vercel firewall plan renders successfully without publishing external state.

## Retrieval review decision

Engineering pre-review recommends all 47 V2 labels for human confirmation. This recommendation is
not a substitute for the named owner review required by the validator.

The original V1 packet was not reviewable:

- `V1-HOLD-106` required a negative inference that its listed FAQ chunk did not establish.
- `V1-HOLD-141` began mid-sentence and did not identify the subject of the distance claim.
- `V1-HOLD-142`, `V1-HOLD-143`, and `V1-HOLD-144` referenced page-10 chunks that had been removed
  from the governed corpus because the underlying text repair was still pending owner review.

V2 replaces those five questions with direct, single-chunk questions over governed raw text. The
configuration remained frozen, and no V2 retrieval ranking was inspected before the replacements
were selected. The new dataset is bound to:

- Dataset SHA-256: `565a4d2c29e6b0dec1953c38b25943880ea2e2ec08146c1a27a246e44051d2ca`
- Ordered holdout SHA-256: `4f2d8dfc8cae3644c4b9a3defed98b0c76322dd2457b6115ac45af9319490684`
- Case count: `47`

Fresh local review artifacts:

- `output/review_handoff/v1_5_retrieval_packet.v2-final.md`
- `output/review_handoff/v1_5_retrieval_owner_review.v2-final.yaml`

The reviewer must inspect the packet without running retrieval, enter their own name and review
timestamp, and make every decision in the hash-bound YAML. Do not copy the obsolete V1 review.

After human approval, validate and run the paid gate exactly once:

```bash
.venv/bin/python scripts/retrieval_owner_review.py validate \
  --review output/review_handoff/v1_5_retrieval_owner_review.v2-final.yaml
.venv/bin/python scripts/run_retrieval_qualification.py \
  --owner-review output/review_handoff/v1_5_retrieval_owner_review.v2-final.yaml \
  --repetitions 3 \
  --max-cost-usd 0.75
```

Every repetition must reach at least `46/47` Recall@5. No failed case may be tuned in place.

## Paid hard probe and semantic review

The qualified 105-case hard probe has not run on this candidate because no local
`OPENROUTER_API_KEY` is available. Historical paid reports are not accepted as current evidence.

Run the paid hard probe with an explicit ceiling, then generate a fresh semantic-review template
from that exact report. The existing 50-case review is obsolete because it is bound to an older
report and contains 12 rejected responses.

```bash
.venv/bin/python scripts/run_hard_probe.py \
  --mode qualified \
  --max-cost-usd 1.50 \
  --output output/hard_probe/current_candidate_qualified.json
make benchmark-v1-1-paid
make owner-review-template
```

The 50-case semantic review remains human-only. Deterministic validation must report zero
unsupported verified-corpus claims, zero unclear claims, all 50 cases approved, and an exact report
hash match.

## Preview and distributed rate limiting

The GitHub review branch is published. No Vercel preview was created because preview scope has no
OpenRouter key and preview publication requires explicit owner approval. Production has an encrypted
key, but it was not exported or copied.

After the owner adds a preview-scoped key and explicitly approves preview publication:

1. Create a non-production preview with `npx vercel@58.1.0 deploy --yes`.
2. Run the documented anonymous preview qualification.
3. Observe request traffic for at least 24 hours before enforcement.
4. Review the rendered method-scoped thresholds.
5. The owner publishes the firewall rules; repository tooling must not auto-publish them.
6. Run the two-instance quota probe and record response IDs, statuses, and timestamps.

Do not merge, deploy production, or describe V1.5 as released until the current paid, human,
preview, and distributed-enforcement gates all pass.
