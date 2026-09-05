# Core

Status: executable zero-cost engineering evidence.

`core` adapts ProductBench v2 offline, ClaimBench v2, the hard probe pinned to
`rc2.2`, and source-aware conversation. Its deterministic output belongs in a
complete run directory; raw evidence is required for diagnosis.

```bash
PYTHONPATH=src:tests python -m firelens_eval run --suite core
```

`CURRENT_DIAGNOSTIC.json` is a compact binding record for the latest campaign
smoke. It is not a substitute for the complete ephemeral artifact it hashes,
and it is not a baseline or qualification result.

`campaign_failure_records.jsonl` preserves the confirmed starting/production
regressions that drove this campaign. Their lifecycle remains `confirmed_fail`
with `fixed_in_sha: null` until a clean exact candidate is committed and rerun;
local repairs alone do not rewrite that history as fixed.
