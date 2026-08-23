# ADR 0013: V1.6 evidence-efficient agent

Status: accepted
Date: 2026-08-16

## Context

V1.5 V3 already used Luna as the Ask brain (ADR 0011) with a thin application
that owns official fetch, RAG, rails, and geodesic numbers. Three costs were
wrong for ordinary supported questions:

1. Pure reviewed guidance still prepaid a full grounded generation, then called
   outer `chat_turn`, then `compose_response` dropped the Luna string.
2. Retrieval was a single hybrid pass. Multi-aspect questions could miss a
   likely aspect with no bounded second look.
3. Public wording, failures, and the handbook lagged the runtime: “verified”
   over-claimed, `except Exception` swallowed tool failures, and the handbook
   still named `service.py` as the Ask orchestrator and said V1.5 excludes
   agents.

Models must not become the authority. They may choose tools and propose
wording. Code and humans decide what is official fact.

## Decision

Keep ADR 0011. Change only the wasteful and unbounded parts:

- When reviewed guidance is already validated and no live records are in the
  packet, **skip the discarded outer `chat_turn`** and return the static
  `AskResponse`. Count `outer_chat_turn` separately from static
  `grounded_generation`.
- Bound every route with `RequestExecutionPolicy`. Deduplicate identical tool
  name plus normalized arguments on the provider path.
- Add **opt-in** `adaptive_v1` retrieval: plan aspects, retrieve, assess, at
  most one targeted second cycle, then generate. Default remains `baseline`
  until H4 and H8 clear on development labels. Repair-time retrieval stays
  forbidden (ADR 0009).
- Publish additive claim-trust, typed public-agent failures, Proof Cards, and
  a current architecture guide. Do not retune frozen catalogs or `FL-V16-S1`
  thresholds after seeing results.

## Consequences

Grab-and-go and similar kit questions no longer pay for a thrown-away Luna
write. Live-only questions must not prefetch SilentStatic / reviewed RAG.
Adaptive retrieval can improve aspect coverage only inside the two-cycle,
six-query, eight-span box, and can be rolled back by env flag. Unexpected
errors stay loud in local/test and never look like a BCWS outage.

`service.py` and `contracts.py` remain above the 650-line modified-module
target with written exceptions in `docs/ARCHITECTURE_V1_6.md`. `loop.py` must
stay ≤350 lines.
