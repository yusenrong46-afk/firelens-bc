# EvalLab artifact index

This tree records the canonical locations and retention policy for FireLens
evaluation evidence. Runtime artifacts are written to `output/eval_lab/` by
default, or to an explicit `--output-dir`. Large raw reports are not copied into
Git merely to make a result look durable.

| Directory | Current disposition |
|---|---|
| `baseline/` | EvalLab core is `BLOCKED`; separate pre-fix observations are retained |
| `core/` | Executable zero-cost adapter; current evidence is diagnostic only |
| `rag/` | `BLOCKED` / `UNPROVEN` |
| `metamorphic/` | `NOT_RUN` / `UNPROVEN` outside ClaimBench v2 core coverage |
| `trajectory/` | `NOT_RUN` / `UNPROVEN` outside source-aware core coverage |
| `fault/` | `BLOCKED` / `UNPROVEN` |
| `ui/` | `NOT_RUN`; browser adapters require explicit execution |
| `performance/` | `BLOCKED`; historical runner is not safe for EvalLab v1 |
| `judge/` | `BLOCKED`; no provider-backed judge is authorized by EvalLab v1 |
| `comparisons/` | Empty until two compatible retained envelopes exist |

The registry and policy are the machine-readable authority:

- `data/evaluation/eval_lab_registry.v1.yaml`
- `data/evaluation/eval_lab_policy.v1.yaml`

No file in this tree is release approval.
