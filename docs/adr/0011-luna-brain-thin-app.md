# ADR 0011: Luna as Ask brain over a thin application

Status: accepted
Date: 2026-08-15
Amended: 2026-08-15

## Context

V1.5 V3 routed Ask with a growing regex forest (`plan_query` live/closest
patterns, `is_distance_request`, template live composers, and a separate
structured planner that never answered). Ordinary fire questions that were not
hardcoded — closest misspellings, geographic distribution, largest burned
hectares — were rejected, listed without analysis, or sent to a planner that
could not use official records.

GPT-5.6 Luna can choose tools and write from official facts. The first form of
this ADR removed application geodesic composers so Luna would estimate
kilometres from coordinates. Preview failures showed that the app then could
not veto a wrong kilometre, and the offline stand-in picked an arbitrary
record as “closest.”

## Decision

FireLens Ask is an **augmented LLM**: Luna is the brain; the application is
thin and stable.

Luna owns:

- classifying prohibited vs fire-related vs tangent;
- choosing which **fixed** tools to call for any fire-related question,
  including types that were never trained or hardcoded;
- writing the answer from the official packet, and rewriting after a
  guardrail hit;
- saying the official records or reviewed guidance do not contain a fact,
  instead of “I don’t have that capability.”

The application owns:

- official record fetch (BCWS ArcGIS layers and BC place geocode). Province-wide
  labels (`BC`, `British Columbia`) use the full layer, not a community geocode;
- RAG (corpus, BM25, embeddings, fusion, rerank, exact quote ids);
- the agent prompt and tool schemas;
- input, execution, and output rails;
- **post-fetch geodesic numbers**: after a fetch with a resolved place, the
  app sets `distance_km` and `distance_basis` with WGS84
  `distance_to_geometry_km`. Distance and nearest-pick answers use those
  fields. Luna must not invent a different kilometre;
- thin post-fetch composers for existence, evac yes/no, two-largest, oldest
  or field-absent, fire-centre counts, geography from official fields, and
  honest roster counts. These run after fetch for analysis asks so Luna and
  FakeProvider publish the same numbers. They are not a return to regex
  topic routing. Official packets sent to Luna omit raw coordinates;
- the OpenRouter privacy wire (ZDR, `data_collection=deny`, no fallbacks);
- a later consented feedback track for distillation / DPO / GRPO. Production
  Ask content is not persisted.

Fixed tools only:

- `list_official_fires`
- `get_official_fire`
- `list_official_evacuations`
- `search_reviewed_guidance`

There is no `calculate_fire_distance` tool. Nearby bbox filtering may still
use geometry so fetch stays bounded. The app can veto an unfetched fire, a
civic address, evacuate / safe-to-return / medical language, and a kilometre
figure that is not on the packet.

A short frozen **input seatbelt** still blocks personalized evacuate / medical
/ jailbreak before a paid call. Luna cannot disable it. Output rails apply the
same safety veto if Luna answers anyway, then Luna rewrites from remaining
facts.

Native OpenRouter tool calling is used when it works under production privacy.
A content-free probe on 2026-08-15 returned HTTP 200 with `finish_reason=tool_calls`
under ZDR + `data_collection=deny` (no `require_parameters`). The Ask path
therefore uses a bounded native tool loop. Offline tests and FakeProvider use a
deterministic heuristic/ActionPlan stand-in. If a future Luna endpoint 404s
under ZDR, the same rails still execute structured tool names from that
stand-in. That is still Luna-as-brain, not regex routing.

Later, consented review pairs and synthetic evals may distill or DPO/GRPO a
smaller student. Production Ask content is not persisted in this pass.

A model swap is a change to `FIRELENS_GENERATION_MODEL`. Tools, rails, and RAG
stay.

This supersedes ADR 0005’s rule that deterministic **topic** routing (live vs
related vs closest) must run before every paid call. ADR 0005 evidence modes
and exact-quote invariants remain. This supersedes ADR 0006’s planner-as-second
brain for Ask. ADR 0008 remains: no LangGraph / NeMo / Agent SDK runtime.

## Consequences

Ask latency and cost rise (tool loop plus write, plus at most one rewrite).
Question-type coverage is no longer a code change. Offline tests use a
deterministic ActionPlan stand-in; live Luna behaviour is characterized, not
treated as a frozen catalog. Leftover live regex in `plan_query` is only a
fail-closed hint so the static corpus path will not invent current conditions.
The app publishes geodesic kilometres it computed; Luna narrates the packet.
