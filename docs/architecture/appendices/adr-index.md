# Appendix — Architecture Decision Record Index

ADR status below preserves each record’s own status and adds a current-reading note. “Accepted” does not mean release-qualified.

| ADR | Recorded status | Current reading |
| --- | --- | --- |
| [0001 — Static evidence boundary](../../adr/0001-static-evidence-boundary.md) | Accepted | Current foundational boundary |
| [0002 — Versioned single-turn API](../../adr/0002-versioned-single-turn-api.md) | Accepted | Versioned API remains; “single-turn” is superseded in part by bounded conversation |
| [0003 — Packet-specific quote-ID schema](../../adr/0003-packet-specific-quote-schema.md) | Accepted | Current |
| [0004 — Development-only retrieval tuning](../../adr/0004-development-only-retrieval-tuning.md) | Accepted | Current experiment/qualification boundary |
| [0005 — Bounded conversation with explicit evidence modes](../../adr/0005-conversational-evidence-modes.md) | Accepted | Current |
| [0006 — Bounded structured planner after safety routing](../../adr/0006-bounded-structured-planner.md) | Superseded in part by 0011 | Historical foundation; current executable authority is 0017/0018 |
| [0007 — Versioned deterministic contextual retrieval](../../adr/0007-versioned-contextual-retrieval.md) | Accepted as experiment | Not default promotion evidence |
| [0008 — Custom pipeline over framework](../../adr/0008-custom-pipeline-over-framework.md) | Accepted | Current |
| [0009 — Bounded grounded-answer repair](../../adr/0009-bounded-grounded-answer-repair.md) | Accepted | Current one-repair bound |
| [0010 — Evaluation dataset roles and sealed gates](../../adr/0010-evaluation-dataset-roles-and-sealed-gates.md) | Accepted; V2 retired, V3 required | Current qualification principle |
| [0011 — Luna brain over thin app](../../adr/0011-luna-brain-thin-app.md) | Accepted; superseded in part by 0017 | Historical model-orchestration framing; deterministic plan now owns tools |
| [0012 — OSM Carto basemap](../../adr/0012-osm-street-basemap.md) | Accepted | Current UI choice; not map/data qualification |
| [0013 — V1.6 evidence-efficient agent](../../adr/0013-v1-6-evidence-efficient-agent.md) | Accepted; superseded in part by 0017 | Current budgets in part; plan authority supersedes model choice |
| [0014 — Mandatory structured publication](../../adr/0014-mandatory-structured-publication.md) | Accepted | Current |
| [0015 — RC2 hard-probe profile](../../adr/0015-rc2-hard-probe-expectation-profile.md) | Accepted | Frozen historical profile |
| [0016 — RC2.1 hard-probe profile](../../adr/0016-rc2-1-hard-probe-expectation-profile.md) | Accepted | Frozen historical profile |
| [0017 — Deterministic AgentQueryPlan ownership](../../adr/0017-deterministic-agent-query-plan.md) | Accepted | Current executable authority |
| [0018 — Typed deterministic intent automaton](../../adr/0018-typed-intent-automaton.md) | Accepted | Current request-shape target; downstream re-parsing remains debt |
| [0019 — RC2.2 hard-probe profile](../../adr/0019-rc2-2-hard-probe-expectation-profile.md) | Accepted | Active named profile; offline result still not release proof |
| [0020 — Source-aware conversation evaluation](../../adr/0020-source-aware-conversation-evaluation.md) | Proposed | Implemented development-unsealed surface; ADR status has not been promoted |

When a new decision changes semantic ownership, update the owning chapter and [module map](module-map.md) in the same candidate. Do not rewrite historical ADR evidence to make current behavior look continuous.

