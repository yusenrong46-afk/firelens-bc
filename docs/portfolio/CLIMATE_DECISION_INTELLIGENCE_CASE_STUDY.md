# FireLens BC V1.6: Evidence-Bound Climate Decision Intelligence

## Problem

Wildfire information products have to make uncertainty legible. People need to
find official incident records and stable preparedness guidance quickly, but a
fluent answer alone cannot establish a current fact, a recommendation, or an
evacuation decision.

FireLens BC is an answer-first engineering prototype for British Columbia. It
combines official records, reviewed guidance, and explicit limits without
presenting retrieval or model output as authority.

## Why naive RAG fails

Retrieval can find relevant text without proving that a sentence is current,
atomic, applicable, or authorized for publication. A naive RAG flow also tends
to merge live records, quotations, and generated interpretation into one
confident-looking answer. That makes it hard for a user to see what was actually
established, what is only source wording, and what could not be verified.

## System architecture

```text
Question -> deterministic request plan -> official adapters / reviewed retrieval
         -> evidence packet -> deterministic validation -> labelled response
         -> Proof Cards and map context when useful
```

The request plan fixes permitted tools, source layers, geography, and any
reviewed-guidance subrequest before a provider can participate. Validation checks
identity, relevance, exact quotation, typed fields, and publication authority.

## Authority model

The model may propose language from an application-owned packet; it does not
authorize facts, choose tools, widen geography, or promote an extraction into a
reviewed claim. FireLens keeps these states distinct:

- official live typed records for current integrated data;
- reviewed structured claims for approved, hash-bound guidance;
- exact source quotations when extraction has not become a structured claim;
- unknown, partial, or official-handoff states when support is missing.

Proof Cards expose the associated source, identity, and publication state rather
than treating a citation as proof of entailment.

## Regional routing defect discovered

An independent defect-first examination reproduced a location-routing failure:
a named fire question that already contained a British Columbia place could
fall into a generic “enter a BC community” continuation. Related mixed and
province-wide requests could also lose the distinction between a deterministic
analysis and a conversational answer.

## Repair design

The repair introduced a single immutable `AgentQueryPlan` and a shared request
grammar. It decides whether a question is a named-record lookup, regional or
province-wide analysis, reviewed guidance, a mixed request, a handoff, or a
request for additional input. The plan is also the sole authority for live
layers and geography. The interface then uses an answer-first conversation for
named records and guidance, and a deterministic summary/map/records workspace
only for genuine multi-record analysis.

## Before-versus-after benchmark

In the local repair campaign, the public structural suite improved from **10/24
to 24/24** cases. The offline hard probe improved from **86/105 to 88/105** with
no previously passing case reported as regressed and zero provider cost. A full
local Python run recorded **1300 passed, 10 skipped, and 584 subtests**; mocked
browser checks recorded **31 passed and one intended skip**, while a deterministic
backend-to-browser lane recorded **9/9**.

These are executed local engineering results, not deployment, certification, or
release evidence. Final qualification commands and a sealed holdout remain
separate gates for this candidate.

## Failure handling

An empty, unavailable, stale, or partial official layer is never an all-clear.
The response says which layer was unavailable, keeps available records separate,
and directs the user to an official source when FireLens cannot establish the
requested fact. Rejected or malformed evidence is downgraded to unknown instead
of being strengthened in the interface.

## Engineering tradeoffs

The system intentionally favors bounded behavior over broad conversational
coverage. That costs some apparent fluency and requires careful data contracts,
but it makes source changes, review state, failure paths, and response authority
inspectable. The product does not browse arbitrary websites or infer local
safety from absent results.

## Transferability

The same design is useful wherever document evidence and changing operational
data have different authority:

- building operations and maintenance intelligence;
- sustainability and climate-risk analytics;
- modular construction and inspection workflows;
- document-plus-sensor systems;
- regulated or otherwise high-consequence decision support.

In each case, the transferable pattern is not “use a chatbot.” It is to bind
data identity, rules, provenance, and presentation state so a user can see what
the system knows, what it does not know, and why.

## Remaining limits

FireLens V1.6 is not an emergency authority and does not establish personal
safety, evacuation decisions, medical advice, continuous monitoring, or
production readiness. Paid H4/H8 evaluation, participant comprehension, manual
VoiceOver review, preview qualification, firewall and rollback proof,
deployment, and release GO remain external human-authorized gates.
