# FireLens V1.6 — 50 end-user question catalog

This is a manually authored, development-only question set for exercising the
whole FireLens experience from ordinary use through misleading and adversarial
requests. The questions are stored in
[`data/evaluation/v1_6_user_end_questions_50.json`](../../data/evaluation/v1_6_user_end_questions_50.json)
and its identity is recorded in
[`v1_6_user_end_questions_50.manifest.json`](../../data/evaluation/v1_6_user_end_questions_50.manifest.json).

It is deliberately separate from the frozen 162-case exploratory catalog and
from the jailbreak/semantic suites. It contains no sealed labels and does not
prove semantic entailment, current live data, accessibility, participant UX, or
release readiness.

## Coverage

| Difficulty | Cases | Main purpose |
| --- | ---: | --- |
| Easy | 12 | Capability discovery, reviewed guidance, named live lookups, basic trust cues |
| Medium | 13 | Mixed lanes, selected records, colloquial input, history, corrections, conditional guidance |
| Hard | 13 | Unsupported current sources, location requirements, personal safety, medical and gas boundaries |
| Very hard | 12 | Prompt injection, impersonated authority, fake citations, all-clear inference, privacy and history pressure |

Every case declares expected response modes, location expectations, live result
kinds where relevant, visible UX surfaces, assertions, and forbidden behaviors.
The assertions are structural/user-experience targets; they are not a substitute
for a human deciding whether wording is actually entailed by an official source.

## Replay

The existing zero-cost-aware product probe can load the catalog without changing
the frozen V1 artifact:

```text
.venv/bin/python scripts/run_product_question_probe.py \
  --suite v1-6-user-end \
  --label v1_6_user_end_questions_run \
  --max-cost-usd <explicit-positive-ceiling>
```

The probe verifies provider spend before replay. Do not run a live/provider
replay without an explicit cost ceiling and the owner’s authorization. A local
catalog load and structural test do not require provider calls:

```text
.venv/bin/python -m pytest -q \
  tests/test_v1_6_user_end_questions.py \
  tests/test_product_question_cases.py \
  tests/test_product_question_probe.py
```

## Human UX walkthrough

For each selected case, record the exact checkout, browser/device, question,
response mode, status banner, answer, evidence panel, Proof Card identity, map
focus/record list, visible timestamps, and any history or error-recovery state.
For location-required cases, record whether the request asks only for the
permitted coarse context. For misleading cases, record whether the user can
understand the limitation without already knowing FireLens's architecture.

Do not turn a pleasant-looking answer into a pass when the support kind is
wrong. Do not turn an empty live result into an all-clear. Accessibility and
participant comprehension remain separate human gates.
