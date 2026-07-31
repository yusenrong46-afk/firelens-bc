# FireLens BC V1.5 principal remediation report

Date: 2026-07-30 (America/Vancouver)

Status: **local remediation passes; release qualification remains blocked**

## Scope and decision rule

Two independent engineering reviews were treated as hypotheses, then reproduced against the
current repository before code changed. Confirmed defects received failing tests and bounded
fixes. Stale findings were corrected in documentation, and recommendations that would change the
retrieval strategy, model stack, public product scope, or external infrastructure were not
silently adopted.

This pass preserves the FireLens foundation:

1. deterministic code owns admission, safety, evidence sufficiency, protected facts, citations,
   conflicts, freshness, geometry, schemas, and final acceptance;
2. model output is a proposal and can never authorize rejected evidence;
3. exact quote matching proves provenance, not general semantic entailment;
4. OpenRouter remains the only model-provider boundary, with no fallback;
5. live chat and map share one typed source path; and
6. local automated evidence is never presented as paid, human-reviewed, preview, or production
   evidence.

## Confirmed findings and dispositions

| Finding | Reproduction | Remediation | Result |
|---|---|---|---|
| Lexical validation accepted changed quantities and inverted safety actions | Adversarial drafts passed the old validator | Added closed deterministic preservation checks and positive paraphrase controls | fixed |
| Status, condition, polarity, and date mutations could retain high lexical overlap | Four focused mutations passed before the new tests | Added protected status groups, optional-condition preservation, action-clause polarity, and date checks | fixed |
| Exact citations could support an answer unrelated to the user question | Offline probe returned grounded sprinkler, smoke, or governance text for unrelated questions | Added a deterministic question-to-evidence support floor before generation | fixed |
| A mixed unrelated clause could be pulled back into RAG by one corpus topic | Corpus-reference override defeated the mixed-scope decision | Mixed-scope decisions now end at a deterministic scope redirect | fixed |
| A non-human-approved page repair was present in the runtime corpus without durable repair provenance | Registry and corpus disagreed; ten derived chunks had no typed approval marker | Only `human_verified` repairs are admitted; provenance is typed through chunks, hits, and evidence; ten chunks and vector rows were quarantined | fixed |
| Cross-authority near-matching prescriptions were not compared for conflict | Different authorities with teal/orange requirements produced an ordinary answer | Removed the authority-class skip while retaining distinct-document and similarity gates | fixed |
| Stale official records were presented under a current-information heading | Stale fixtures retained current wording | Stale headings and limitations are explicit; records remain visible but not current | fixed |
| Unknown geometry disappeared from located live results | Valid records with unusable geometry were dropped | Records remain visible with `unknown` relation and an explicit geometry limitation | fixed |
| ArcGIS pagination lacked a stable order and hard ceiling | Repeated/unstable pages could continue without a bounded proof of progress | Added stable object-ID order, deduplication, progress checks, repeat detection, and a 100-page fail-closed ceiling | fixed |
| Forwarded IP input could be spoofed and streaming bodies were fully buffered before rejection | Header/body adversarial tests reproduced both paths | Ignore ordinary forwarding headers; trust only the Vercel-owned header on an identified Vercel deployment; reject declared and streamed oversize bodies early | fixed |
| Debug routes and readiness status were too permissive for production operations | Production debug flag still registered routes; unready health returned 200 | Production never registers debug routes; readiness returns 503 when unready | fixed |
| Conversation history could not round-trip a valid generated answer | A 2,500-character answer violated the 2,000-character turn limit | Raised the per-turn bound to 6,000 while retaining six turns and the 64 KiB total body limit | fixed |
| Public work lacked a total deadline | Slow live work exceeded a bounded request lifecycle | Ask and live-map handlers enforce a 45-second total deadline and cancel downstream work | fixed |

## Implementation history

| Commit | Purpose |
|---|---|
| `bfac0b5` | Reject material grounded-claim mutations and preserve the original question at safety routing |
| `73d811b` | Quarantine unverified repairs and carry typed review provenance |
| `2987bd5` | Close repair-provenance typing found by static analysis |
| `2577462` | Preserve truth in stale, unknown-geometry, and paginated live results |
| `b3e202a` | Harden proxy, request-size, readiness, and production-debug boundaries |
| `1a47099` | Bound cross-authority conflict, history, and public reliability edge cases |
| `be3cb4e` | Preserve protected statuses, conditions, polarity, and dates |
| `6ad68aa` | Apply the same total deadline to the live-map endpoint |
| `ea0f633` | Require direct question support and preserve mixed-scope redirects |

The commits are intentionally separated by failure class. No application framework, UI kit,
provider, runtime model, retrieval configuration, reranker, or official source changed.

## Executed evidence

The final local verification command is:

```text
make verify
```

It covers tracked-secret scanning, generated OpenAPI and TypeScript drift, Ruff, formatting, mypy,
the Python suite, frontend unit/accessibility tests, production build, Sites packaging, and 18
desktop/mobile Playwright flows.

Final result: 203 Python tests passed, 10 opt-in network/paid tests skipped, 76 Python subtests
passed, mypy passed across 55 source files, 12 frontend tests passed, 4 Sites packaging tests
passed, the production build completed, and all 18 Playwright flows passed.

The permanent zero-cost probe command is:

```text
.venv/bin/python scripts/run_hard_probe.py --mode offline
```

The first remediated-tree run was `95/105`; a second was `101/105`; the final run was `105/105`.
The progression is retained here because failed experiments are evidence. The final run used the
same frozen 105-case dataset, controlled provider/live doubles, and `$0.00` paid cost. It verifies
offline policy and state-machine behavior only.

## Recommendations deliberately not implemented

- No runtime LLM reviewer was added. Human semantic adjudication remains the release authority.
- No GraphRAG or contextual-retrieval experiment was promoted.
- No retrieval weights, candidate counts, top-k value, model, reranker, corpus source, or live
  source changed without the deferred sealed comparison.
- No distributed-rate-limit claim was made. Vercel documents that its request headers overwrite
  forwarding input (<https://examples.vercel.com/docs/headers/request-headers>) and that WAF rate
  limiting is an external action (<https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting>).
  The report baseline used log-only rule preparation. The later GP-004 remediation prepares an
  enforced deny rule, but publication and cross-instance preview proof remain external gates.
- No merge, push, preview, firewall publication, or deployment occurred.

## Remaining risk and release blockers

The principal remaining uncertainty is semantic and operational, not compilation. Closed
deterministic checks prevent known high-risk transformations, but they cannot prove arbitrary
entailment, completeness, authority preference, or retrieval quality. The 170-chunk corpus also
invalidates current-use claims based on the prior 180-chunk paid and retrieval artifacts.

Before release, complete the qualified 105-case OpenRouter rerun, regenerate and sign the 47-case
retrieval and 50-case semantic reviews, run the sealed three-repeat retrieval gate once, refresh
generalization/live/latency/concurrency evidence, qualify an anonymous preview with distributed
rate-limit enforcement, rehearse rollback, and reconstruct a tree-identical release branch.

Until then, the honest disposition is: **good enough for another strict engineering review; not
good enough for release or production promotion**.
