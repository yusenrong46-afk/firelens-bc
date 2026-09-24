# Source follow-up release repair v3

Predecessor: `2ae0370fe571da46b8c540eda205000e3b5d4682`, PR #83.
This supplements the [map-first release](map-first-release-v2.md); previous
campaign evidence and submission limits remain intact.

## Demonstrated defect and repair

After actual grab-and-go and pet answers, “Explain the source you used for that
answer” could reach an unrelated high-risk handoff. Conversation authority labels
were treated as a source antecedent even though public history contains no
verified preceding document revision or passage packet.

The existing input-clarity owner now explicitly requests that missing source
information for standalone preceding-answer provenance questions. It does not
invent a citation or make a provider call. New guidance, mixed requests, selected
records, and actual personal-safety questions retain their existing paths.

Independent review also caught a location-required banner on this source-required
response. The existing presentation owner now consistently asks for a source.
The bounded application changes are `input_clarity.py`, its existing coordinator
call, and `proof_presentation.py`. This extends the v2 preservation scope by these
three owners; frontend, models, Python dependencies, public schema, and the
178-chunk corpus/index remain unchanged.

## Verification and limits

`tests/test_release_source_followup.py` preserves recorded history, checks six
equivalent formulations with and without history, tests meaningful task changes,
and verifies the full response banner and zero service calls. Historical
acceptance obligations are protected separately.

The 105-case offline hard probe has unchanged outcomes and identical payloads for
all nine historical discrepancies. Fourteen passing live cases differ only in
fixture clocks. Versioned v4 policy/v3 dispositions bind the repaired owners;
previous policies, raw failures, and expectations are unchanged.

A preceding-source answer may explicitly report missing provenance; this does not
claim general citation reconstruction. Offline success does not close the
remote-browser requirement.

## Remaining release gates

The recorded weather explanation failed with a provider rate limit; its cause and
recovery remain unverified. A narrowly authorized read of the production key
returned no usable credential because Vercel exposes it as sensitive. No
credential was saved/displayed, no settings changed, and no paid call was made.

New browser execution must use an authorized successor allowance and actual
prerequisite history. Release stays **BLOCKED** until exact-candidate preview
checks, source follow-up, weather-to-Prince-George sequence, CI, packaging, and
production verification pass. Do not merge or promote on offline evidence alone.

Rollback and project identity remain as documented in the v2 runbook.
