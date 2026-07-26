# Learning note 00: Why the baseline comes first

The project began as a downloaded directory without Git history. Before changing
behavior, FireLens created a baseline only after proving that the local API key,
downloaded source bytes, vectors, traces, dependencies, and generated builds
were ignored. The baseline commit makes every later architecture and benchmark
claim reviewable as a concrete diff.

Executed evidence: backend `48 passed, 3 skipped`; frontend production build;
Sites packaging `4/4`. These results prove the existing paths execute. They do
not prove semantic answer correctness.
