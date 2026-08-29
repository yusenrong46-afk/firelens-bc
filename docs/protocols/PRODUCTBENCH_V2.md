# ProductBench v2

ProductBench is a public, development-unsealed journey catalog. It is not a
ClaimBench replacement, a hard-probe replacement, or release evidence.

`data/evaluation/productbench_journeys_50.json` is the current unsealed raw
journey catalog. The v2 manifest snapshot-binds its current bytes; it does not
claim that the catalog was immutable before v2 or provide a historical anchor.
The v2 executable catalog is a derived internal contract, not a replacement
question set: its schema and SHA-256 are separately bound in
`data/evaluation/productbench_v2.manifest.json` along with the raw-source hash,
exact ordered IDs, unsealed status, 31/19 tier split, and executable contract
hash. The current v2 snapshot retains all 50 IDs and intentionally states PB-12
as “Tell me about the Bald Range Fire” to avoid treating a bare topic phrase as
a live-incident request. The manifest freezes the current unsealed catalog; it
does not claim an unverifiable pre-v2 text diff or historical anchor.

The closed executable vocabulary maps each catalog assertion and forbidden
behavior to predicate IDs and a closed tool contract. Unknown behavior labels,
predicate IDs, tools, catalog hashes, missing IDs, or tier changes reject the
run before execution.

Run the deterministic zero-cost tier locally or in CI:

```bash
.venv/bin/python scripts/run_productbench.py --mode offline \
  --output output/productbench/offline.json
```

It runs exactly the 31 `offline_fake` cases through the actual in-process
FireLens ASGI app and runtime. The only doubles are a network-free official
record fixture and `FakeProvider`; the evaluator scores the app's own response
payload and operational tool trace. The report records a case ID, trace ID,
tool names, response hash, catalog/manifest/contract identities, fake-provider
call counts, and zero cost.

The 19 `provider_manual` cases are never run by CI. An operator may run all of
them with a positive ceiling:

```bash
make productbench-provider MAX_COST_USD=0.75
```

Provider mode refuses a missing or insufficient provider-enforced key cap, a
non-positive ceiling, missing transaction receipts, an incomplete case sequence,
or spend above the ceiling. The report binds the provider boundary, commit/tree,
input identities, traces, and receipt-backed returned costs. A passing provider
report remains development evidence only.
