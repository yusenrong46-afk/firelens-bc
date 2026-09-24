# Live release closure v4

This successor starts from 3aba5d1 and preserves earlier campaign failures.
It adds internal, content-free provider observations: a generated request
correlation, unique attempt identity, stage, bounded ordinal, dispatch/terminal
state, transport elapsed time, HTTP/embedded numeric error codes, parsed retry
delay, allowlisted limit classifications, and finite supplied cost. Missing cost
remains unknown and never blocks a valid response.

No upstream messages, raw bodies, credentials, prompts, answers, private
coordinates, or arbitrary metadata enter these observations. HTTP200 does not
establish successful generation. Error responses retain their existing public
shape while logging the internal correlation. Provider retry, model, deadline
and privacy behavior remain unchanged. The unchanged wire-error classifier moves
into the existing provider-support module to preserve the module-size boundary.

The successor bank is tests/fixtures/frontend_release_smoke.v3.json:
ten preview, ten production, and at most four corrective UI submissions.
Failed prerequisites block their dependants. Every uncertain dispatch consumes a
slot. Actual browser history and durable reservations remain required. Existing
campaigns are preserved; this is a separate authorized allowance.

Before release, require offline privacy/resilience controls, independent review,
clean-candidate CI/evaluation, local packaging, exact preview identity, and all ten
preview cases. The weather case must establish actual successful generation.
Source follow-up may explicitly report genuinely unavailable preceding metadata.
Do not infer broad answer completeness from intact supplied quotations.

Merge/promote only after preview closure, then verify all ten production cases.
Rollback remains dpl_EYCT2WNWw1WGTPQdgpTFUzzaeSQP. Account purchases, key changes,
privacy relaxation, model substitutions, and source migration are not authorized
by this successor. Report BLOCKED with evidence if a required case remains open.
