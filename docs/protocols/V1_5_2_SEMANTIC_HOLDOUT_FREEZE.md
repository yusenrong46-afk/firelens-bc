# V1.5-2 semantic-holdout freeze protocol

This protocol creates the two public identities needed by the source-disjoint semantic holdout
without copying the owner-held prompts, source material, risk labels, or canonical input payloads
into the repository. It implements the schema-v3 contract consumed by the V1.5-2 comparator; it
does not create a real holdout, authorize candidate generation, or qualify a release by itself.

The tracked machine policy is
`data/evaluation/semantic_holdout_freeze_protocol.v1.json`. The freeze tool refuses unknown schema
fields, duplicate JSON object keys, non-NFC strings, non-finite numbers, noncanonical identifiers,
unsorted or duplicate rosters, symlinks, parent-directory traversal, an existing output, or a known
candidate start. Refusals print only a stable reason code. Private values are never included in
console output.

## Private boundary

The private holdout payload must live outside the repository and remain owner-controlled. It has
exactly these top-level keys:

- `payload_version`: `firelens_semantic_holdout_private_payload.v1`
- `dataset_id`: a canonical lowercase identifier
- `cases`: at least 25 rows, sorted by unique canonical `case_id`

Each case has exactly `case_id`, `input_payload`, `source_id_sha256s`, `question_family_id`, and
`risk_labels`. Source commitments are lowercase SHA-256 digests; source, family, and risk-label
arrays are sorted and unique. At least five question-family IDs are required. A case's declared
source roster must exactly equal the unique source commitments in its source context.

`input_payload` is the actual human-review input, not an opaque metadata envelope. It has exactly:

- `input_version`: `firelens_semantic_holdout_review_input.v1`
- `question`: the complete private question
- `history`: the ordered prior messages, each exactly `{role, content}`, with `role` equal to
  `user` or `assistant`
- `rubric`: exactly `expected_route`, `expected_status`, sorted unique `required_concepts`, sorted
  unique `forbidden_claims`, and sorted unique `required_limitations`; at least one rubric list must
  be nonempty
- `source_context`: one or more rows sorted by unique canonical `context_id`, each exactly
  `context_id`, `source_id_sha256`, `locator`, and the complete private `text`

The public `input_sha256` is defined as
`SHA256(UTF8(compact_sorted_JSON(input_payload)))`. Therefore a future review workspace recomputes
the same commitment from the exact question, ordered history, rubric, and source context it presents
to reviewers. Changing any of those values changes the hash. No private field or per-field content
hash is substituted for the actual review input. The public manifest retains only that aggregate
input commitment and hashed source IDs.

The canonical dataset commitment covers the complete private payload, including every review input
and risk label. Canonical hash encoding is UTF-8 JSON with sorted object keys, compact separators,
NFC strings, and no ASCII escaping. Ordered history is preserved; rosters whose order is not
semantic are required to be sorted and unique.

The development freeze request may also remain owner-held. It records a named reviewer,
source/family canonicalization attestations, review and freeze timestamps, and a sorted roster of
development dataset identities. Each dataset row contains exactly `dataset_id`, `dataset_sha256`,
`source_id_sha256s`, and `question_family_ids`. The generated public registry intentionally follows
the existing exact v1 schema, so review provenance remains with the reviewed request and owner
records rather than being added as an unrecognized registry field.

## Freeze sequence

Run this before any final-candidate generation. `--attest-no-candidate` is a procedural guard; the
later Git ancestry and candidate-report timestamp checks remain the release evidence that the
manifest was actually committed first. If candidate work has started, pass
`--candidate-created-at`; the tool will refuse instead of backdating a new freeze.

```bash
.venv/bin/python scripts/freeze_semantic_holdout.py freeze-registry \
  --reviewed-roster /absolute/owner-controlled/development-freeze-request.json \
  --output data/evaluation/benchmark_v1_5_2_semantic_development_registry.json \
  --attest-no-candidate

.venv/bin/python scripts/freeze_semantic_holdout.py validate-registry \
  --reviewed-roster /absolute/owner-controlled/development-freeze-request.json \
  --registry data/evaluation/benchmark_v1_5_2_semantic_development_registry.json

.venv/bin/python scripts/freeze_semantic_holdout.py freeze-manifest \
  --private-payload /absolute/owner-controlled/semantic-holdout-private.json \
  --development-registry data/evaluation/benchmark_v1_5_2_semantic_development_registry.json \
  --output data/evaluation/benchmark_v1_5_2_semantic_holdout.manifest.json \
  --audited-at 2026-08-06T18:00:00+00:00 \
  --frozen-at 2026-08-06T18:05:00+00:00 \
  --attest-no-candidate

.venv/bin/python scripts/freeze_semantic_holdout.py validate-manifest \
  --private-payload /absolute/owner-controlled/semantic-holdout-private.json \
  --development-registry data/evaluation/benchmark_v1_5_2_semantic_development_registry.json \
  --manifest data/evaluation/benchmark_v1_5_2_semantic_holdout.manifest.json
```

The manifest command recomputes case input hashes, the canonical case/source/family rosters,
family distribution, the complete private-dataset commitment, the exact development-registry file
binding, and both source and family intersections. Any overlap is a refusal, not a warning. It uses
the existing schema-v3 benchmark validators before an exclusive create. It never rewrites or emits
a normalized private payload.

After both public artifacts have been independently validated, review their metadata without
opening the private questions, commit them before candidate generation, promote the dataset role to
`sealed_release_qualification` and `available`, and add both paths to the benchmark
`identity_inputs`. Human reviewers must still examine conceptual leakage: zero overlap of canonical
hashes and family IDs is necessary but cannot prove semantic independence.
