# Contributing to FireLens BC

These are the engineering standards every change to this repository follows.

Treat generated code and prose as untrusted proposals until repository evidence verifies them.

Before editing, inspect the active branch, relevant contracts, callers, configuration, tests, and pinned dependency versions. Freeze acceptance criteria before changing behavior. For refactors, add or run characterization tests first.

Do not invent endpoints, fields, environment variables, source authority, benchmark results, human-review outcomes, deployment state, or commands. Verify interfaces in the checkout or version-matched primary documentation. Never alter a test, label, threshold, or expected result merely to make a failing implementation pass.

Keep the deterministic authority boundary intact: models propose language; source contracts, validation, and humans decide. Production must require OpenRouter ZDR for embedding and generation, keep provider fallback disabled, send `data_collection=deny` on every OpenRouter request, and must not persist questions, answers, deterministic query hashes, or precise locations. Cohere reranking is a reviewed non-ZDR exception, not a claim of universal ZDR.

Run targeted checks after each coherent change and `make verify` before release claims. Report evidence as read, inspected, executed, reproduced, or not run. A passing local or synthetic check is not human or deployed evidence.

GitHub updates follow `docs/protocols/V1_6_GITHUB_UPDATE_STANDARD.md`: local-only by default; push, PR, or merge only when the human explicitly authorizes it; never deploy from an agent session. `README.md` and merge commits must read as Thomas's engineering record, not OpenAI or Codex output. No vendor `Co-authored-by` trailers.

Keep modules cohesive, scripts thin, public interfaces typed, and generated artifacts clearly separated. Preserve unrelated changes and historical evidence.
