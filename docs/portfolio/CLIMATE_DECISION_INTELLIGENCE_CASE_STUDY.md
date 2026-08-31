# FireLens BC: Evidence-Bound Climate Decision Intelligence

## The decision problem

People asking about wildfire conditions need two very different kinds of
information: changing operational records and stable preparedness guidance. A
conventional chatbot can retrieve both, summarize both, and still leave the
user unable to tell which sentence is current, reviewed, merely quoted, or
unsupported.

FireLens BC is an independent engineering prototype built around that problem.
It applies a pattern relevant to climate and building intelligence: keep
changing operational records, governed documents, model language, and
user-facing confidence visibly distinct.

It is not an emergency authority. Its goal is to make a useful answer and its
limits inspectable.

[Open the public V1.6.2 demo](https://firelens-bc.vercel.app) or follow the
[3–5 minute demo script](DEMO_SCRIPT.md). Live records and timestamps change;
the architecture and failure boundaries are the intended demonstration. The
[public readiness endpoint](https://firelens-bc.vercel.app/api/v1/health/ready)
exposes the deployed runtime identity separately from this checkout.

## Why naive RAG fails

Retrieval proves that text was found, not that a generated sentence is entailed,
current, atomic, or authorized for publication. A large source chunk may contain
several unrelated facts. A citation may point to the right document but the
wrong span. A live adapter may be unavailable while a model still sounds
confident.

Those are data-contract problems, not prompt-writing problems. I therefore
treated publication as a separate deterministic system:

```text
question
  -> typed intent and immutable request plan
  -> bounded official adapters and/or reviewed retrieval
  -> evidence packet
  -> identity, relevance, quotation, field, and authority validation
  -> labelled response, Proof Cards, and useful analytical context
```

The model can help communicate. It cannot authorize a live fact, choose new
tools, widen geography, or promote an extracted quotation into a reviewed
claim.

## What I built

### Separate evidence lanes

Official live records, reviewed structured guidance, exact source quotations,
general background, and unknowns are different publication kinds. They retain
different labels even when one question needs more than one lane.

### Governed claims and atomic evidence

High-risk structured guidance compiles from a 26-record typed inventory with
human review state, source-document revision, atomic quote, span hash, and
approved wording. A changed source, missing chunk, altered quote, pending review,
or changed surface fails closed. Nine source-repair deferrals remain
non-compilable rather than being forced through review.

### Deterministic request authority

An immutable query plan fixes which tools, official layers, and geography a
request may use. The plan also carries selected-record identity into a bounded
follow-up, so “How large is it?” can remain tied to the record the user actually
selected instead of silently choosing another incident.

### Adaptive product presentation

The interface does not show the same map-heavy shell for every question.
Guidance and ordinary conversation stay in a focused Chat view. Multi-record
questions open a snapshot-only Analysis workspace with Summary, Map, and Records.
Named, nearby, and closest-fire questions use a Spatial view when map context is
useful. Missing or stale layers remain visible and never become an all-clear.

### Operational value beyond wildfire

For building and climate-intelligence teams, the same separation reduces the
risk of treating a stale sensor reading, extracted document sentence, or model
summary as an approved operational fact. It also gives reviewers a smaller,
traceable surface to inspect: each published item carries its source identity,
scope, validation state, and permitted presentation. That can make exception
handling and evidence review more repeatable across maintenance, sustainability,
and compliance workflows. This is an architectural risk-control hypothesis,
not a measured business or user outcome from FireLens.

## A representative journey

Consider: “Show current wildfire distribution by fire centre across B.C.”

1. Typed intent classifies a province-wide multi-record analysis without
   inventing a place requirement.
2. The immutable plan authorizes the required official layer and no unrelated
   geography.
3. The live adapter returns typed records and freshness metadata.
4. Application-owned analysis counts the returned snapshot by fire centre and
   status. No provider writes those facts.
5. The UI leads with a concise answer, then renders accessible charts and a
   sortable record table. It says “returned records,” not an unsupported claim
   about every real-world incident.

If the source is unavailable, the answer names that limitation. If zero records
are returned, FireLens does not infer that B.C. is safe.

## What failure taught me

Adversarial journey testing found defects that ordinary unit tests missed:
questions containing “wildfire” could be routed into irrelevant live rosters;
province-wide analysis could be mistaken for a place lookup; negated source
wording could lose its negation; and multi-turn location or selected-record
state could be dropped by the interface.

The repair strategy was not to add a longer prompt. I separated scope,
capability, safety, tool planning, publication, and presentation; then added
failing behavioral tests. During the pre-candidate repair campaign I ran
backend, frontend, browser, structural-publication, hard-probe, and ProductBench
checks. A later 100-journey public ProductBench run exposed failures that unit
tests had missed, including quote negation, vague-place routing, refresh scope,
and selected-record continuity. Those failures were reproduced and locked with
behavioral tests before repair. Current results remain attached to the exact Git
candidate and CI/runtime artifacts that produced them rather than being frozen
into this narrative.

## Why the pattern transfers

The same architecture applies when operational data and governed documents have
different authority or update rates:

- building performance and maintenance records;
- sustainability reporting and climate-risk analytics;
- inspections, work orders, and compliance documents;
- document-plus-sensor decision support;
- any workflow where “we found text” is weaker than “this claim is authorized.”

The transferable skill is not simply building a chatbot. It is designing data
identity, policy, validation, analytical computation, and interface state so a
user can see what the system knows, what it does not know, and why.

## Remaining limits and evidence

The repository includes a [V1.6 architecture](../ARCHITECTURE_V1_6.md),
[Product Constitution](../quality/FIRELENS_PRODUCT_CONSTITUTION.md),
[ProductBench protocol](../protocols/PRODUCTBENCH_V2.md),
[release runbook](../releases/V1_6_RUNBOOK.md), and
[fixture-backed demo script](DEMO_SCRIPT.md).

Automated evidence can establish deterministic behavior, source identity,
quotation integrity, request authority, and interface states for a particular
commit. It cannot establish personal safety, universal answer quality, human
comprehension, or approval by an emergency authority. Public runtime identity is
exposed separately by the readiness endpoint; human and institutional gates
remain explicit rather than implied.
