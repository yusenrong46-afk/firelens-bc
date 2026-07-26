# FireLens BC R0 Product Contract

Status: Owner-approved for R0 implementation  
Contract version: `r0.4`  
Date: `2026-07-25`

## 1. Product identity

FireLens BC is a verified wildfire-preparedness RAG system for British
Columbia. It retrieves approved official guidance and produces answers whose
important factual claims can be traced to supporting evidence.

It is not a generic PDF chatbot, an emergency authority, or an evacuation
decision system.

## 2. Primary user

A British Columbia resident or visitor who needs understandable, source-backed
wildfire preparedness information.

## 3. R0 user need

The first release addresses:

> What official guidance should I understand or prepare before or during a
> wildfire-related emergency?

Examples include:

- preparing an emergency plan;
- building a grab-and-go bag;
- understanding evacuation terminology;
- following an evacuation alert or order;
- reducing household wildfire exposure;
- understanding general wildfire-smoke guidance.

## 4. R0 capability boundary

### In scope

- stable official preparedness and public-safety guidance;
- evidence retrieval from an approved corpus;
- document and page provenance;
- structured factual claims;
- explicit limitations;
- abstention when evidence is missing or insufficient;
- directing users to the relevant official live authority when the corpus
  cannot answer safely.

### Out of scope for the RAG foundation

- determining whether a location is currently safe;
- determining whether a particular address is under an alert or order;
- reporting current fire location, perimeter, size, direction, or containment;
- inventing or optimizing evacuation routes;
- predicting ignition, spread, property loss, or evacuation orders;
- medical diagnosis or personalized medical instructions;
- satellite-image modelling;
- autonomous agents.

Questions requiring current incident status belong to a later live-data tool,
not the static RAG corpus.

These live-data capabilities are excluded from the RAG foundation but are
mandatory for the first customer MVP.

## 4.1 First customer MVP definition

The first customer MVP is complete only when the verified RAG layer and
narrowly scoped live authoritative tools are exposed through a conversational
LLM API.

### Mandatory conversational capability

Users must be able to chat with FireLens through a backend chat endpoint. The
LLM may:

- interpret the user's question in conversation context;
- classify stable-guidance, live-status, mixed, or prohibited intent;
- rewrite a conversational follow-up into a standalone retrieval query;
- select the approved retrieval or live-tool path;
- synthesize evidence into a clear answer;
- preserve citations, timestamps, uncertainty, and limitations;
- ask for a location or other required information when it is genuinely
  missing.

The LLM may not:

- answer factual wildfire questions from model memory;
- fabricate citations or tool results;
- silently convert `unknown` into `safe`, `none`, or `not applicable`;
- override an issuing authority;
- retain unlimited conversation history;
- allow earlier user messages to erase safety and evidence rules.

### Initial chat endpoint

```text
POST /chat
```

Request:

```json
{
  "conversation_id": "optional identifier",
  "message": "What is happening near Kelowna, and what should I prepare?",
  "location": {
    "latitude": 49.888,
    "longitude": -119.496
  }
}
```

Response:

```json
{
  "answer": "Conversational response",
  "answer_type": "guidance | live | mixed | abstention",
  "claims": [],
  "sources": [],
  "live_results": [],
  "limitations": [],
  "requires_live_verification": true,
  "conversation_id": "identifier"
}
```

Streaming may be added for user experience, but the completed structured
response remains the evaluation and audit contract.

### Evidence gate

Before a factual answer reaches the user:

1. the system retrieves approved document evidence and/or live official data;
2. the LLM drafts only from that supplied evidence;
3. claims are linked to their supporting passages or tool results;
4. unsupported claims are removed or cause abstention;
5. the final response preserves source and freshness information.

The LLM provider must be accessed behind a provider-neutral interface so a
model can be replaced without rewriting retrieval, tools, evaluation, or the
public API.

### Mandatory live-tool capabilities

- retrieve current wildfire incidents from an authoritative source;
- retrieve current evacuation alerts and orders from EmergencyInfoBC and/or
  the issuing authority;
- determine whether returned official geometries intersect or fall within a
  declared radius of a user-selected location;
- display source update time, retrieval time, authority, and freshness;
- distinguish "no matching record was returned" from "the location is safe";
- fail closed when a live source is unavailable, malformed, or stale.

### Mandatory live-result fields

```json
{
  "authority": "EmergencyInfoBC",
  "source_url": "canonical official URL",
  "source_updated_at": "timestamp supplied by the authority",
  "retrieved_at": "timestamp recorded by FireLens",
  "freshness": "fresh | stale | unknown",
  "status": "source-specific status",
  "geometry_relation": "inside | nearby | outside | unknown"
}
```

### Routing rule

- Stable preparedness and explanatory questions route to RAG.
- Current incident, alert, order, perimeter, and location questions route to
  live tools.
- Questions containing both kinds of intent use both, while keeping the
  resulting claims visibly separated.
- Current-status claims may not be answered from embedded documents or cached
  prose when a live tool is required.
- Conversational follow-ups must be resolved into standalone intent before
  retrieval or tool execution.

### Truth hierarchy

1. The issuing authority controls the meaning and applicability of its current
   alert or order.
2. Live official data controls current-status claims.
3. Approved stable documents control general preparedness explanations.
4. FireLens may synthesize these results but may not override, silently merge,
   or reinterpret an authority's instruction.

### First customer MVP example

For:

> What is happening near Kelowna, do any official evacuation notices apply,
> and what should I prepare?

FireLens must produce separately labelled sections:

- `Live official facts`
- `Retrieved official guidance`
- `System limitations`

The answer must not imply that the absence of a returned alert proves that the
user is safe.

### First customer MVP acceptance gate

The first customer MVP must demonstrate:

- multi-turn chat through the LLM API;
- evidence-grounded answers from the RAG layer;
- current-status answers from live authoritative tools;
- mixed answers that visibly separate guidance from live facts;
- correct abstention under missing, stale, or unavailable evidence;
- citations and freshness metadata that survive LLM generation;
- conversation tests showing that a user cannot persuade the model to invent
  an order, ignore an authority, or remove required safety limitations.

## 5. Source policy

### Approved authority classes

1. Government of British Columbia agencies and services:
   - PreparedBC;
   - BC Wildfire Service;
   - EmergencyInfoBC;
   - BC Centre for Disease Control;
   - other clearly identified provincial public-safety or health authorities.
2. FireSmart BC and FireSmart Canada materials when the document's ownership,
   publication context, and intended audience are clear.
3. A local authority or First Nation for an alert or order that it has issued.
   These sources are live-event evidence and are not treated as timeless
   guidance.

### Rejected as answer evidence

- news reporting;
- social-media reposts;
- commercial wildfire products;
- personal blogs and discussion forums;
- search-result snippets;
- unattributed summaries;
- model-generated text;
- a third-party quotation when the original authority is available.

### Source freshness rules

Every ingested source must store:

- `source_id`;
- title;
- publisher;
- canonical URL;
- source type;
- publication or last-updated date when available;
- retrieval date;
- version or content hash;
- authority class;
- temporal class: `stable_guidance` or `live_status`;
- review status.

Live-status material must never be presented as current unless it is fetched
through a live tool and displays its update and retrieval timestamps.

## 6. Answer contract

Each answer must contain:

```json
{
  "answer": "A concise synthesis of supported guidance.",
  "claims": [
    {
      "claim": "One independently checkable factual statement.",
      "source_id": "preparedbc_wildfire_guide",
      "page": 6,
      "evidence": "The supporting passage.",
      "support_level": "direct"
    }
  ],
  "confidence": "high",
  "limitations": [],
  "requires_live_verification": false
}
```

Allowed support levels:

- `direct`: the evidence explicitly supports the claim;
- `partial`: the evidence supports only part of the claim;
- `none`: the evidence does not support the claim.

A citation is not sufficient by itself. The cited passage must entail the
claim.

## 7. Abstention contract

The system must abstain when:

- no approved evidence is retrieved;
- evidence is only partially relevant;
- approved sources conflict and the conflict cannot be resolved;
- the question asks for live status unavailable to the static corpus;
- the question requests a prohibited safety decision;
- the answer would require personalized medical, legal, or emergency judgment;
- a source is stale for the requested claim.

An abstention should state:

1. what the system cannot establish;
2. why it cannot establish it;
3. which official authority the user should check.

It must not fill the gap with a plausible guess.

## 8. Initial evaluation standard

The initial gold set will contain:

- 10 directly answerable questions;
- 5 multi-passage or multi-document questions;
- 3 unanswerable questions;
- 2 adversarial or misleading questions.

Every gold item must identify its expected evidence before retrieval is
evaluated.

Initial metrics:

- retrieval Recall@5;
- citation precision;
- citation completeness;
- unsupported-claim rate;
- abstention accuracy;
- answer faithfulness;
- latency.

## 9. Forbidden product claims

FireLens BC must not claim that it:

- tells users whether they should evacuate;
- replaces EmergencyInfoBC, BC Wildfire Service, or local authorities;
- provides real-time information before a live-data capability exists;
- guarantees that an answer or cited document is current;
- predicts wildfires or property safety;
- eliminates hallucinations.

## 10. R0 exit gate

R0 is complete only when:

- this contract is accepted;
- at least 10 sources are reviewed in the registry;
- 20 gold questions are evidence-anchored;
- the first three documents are manually inspected;
- every gold question is labelled by answerability and difficulty;
- prohibited claims and abstention triggers are testable.

Passing R0 does not mean the customer MVP is complete. R0 enables the RAG
foundation; the first customer MVP additionally requires the live-tool gate
defined in Section 4.1.
