# Pacific Clarity — production verification

## Identities

| Item | Value |
|------|-------|
| Starting main SHA | `58eb80153358c82a5be1da095245e627b5c0ed05` |
| Candidate SHA (app fix) | `26fdd8374ce6b3af1ef34709296a2dbb024f1837` |
| Final deployed SHA | `422d80dd346c0edf71eea41e144dcf2089dc2397` |
| Preview deployment | `dpl_BWHCVg8s1aPmW63UvKcs1GQPBtrA` |
| Production deployment | `dpl_6hi3MjUuxWwsCQejPqCv8EgyC6t9` |
| Production URL | https://firelens-bc.vercel.app/ |
| Release version | 1.6.4 |

## Rollback target (pre-change production)

- deployment_id: `dpl_GYhPvwts3LkZoAqNQmpixLPeprwX`
- build_commit: `b8e07ebffc730fab654207e643155b1d78e74816`
- main SHA: `58eb80153358c82a5be1da095245e627b5c0ed05`

## Ready response (production post-deploy)

- status: ready
- build_commit: `422d80dd346c0edf71eea41e144dcf2089dc2397`
- deployment_id: `dpl_6hi3MjUuxWwsCQejPqCv8EgyC6t9`
- provider: openai/gpt-5.6-luna
- retrieval_text_strategy: metadata_context_v1

## Gates

- Preview Reality Gate: 16/16 passed against `firelens-gna5ylf7z-...`
- Production Reality Gate: 16/16 passed against `https://firelens-bc.vercel.app`
- Local Vitest: 173/173
- ClaimBench v2: pass (unsafe_false_accept_rate 0.0)
- Hard probe rc2.2 offline: exit 0
- Source-aware conversation: pass

## Screenshots

- `evals/pacific_clarity/screenshots/production/idle-1536x1024.png`
- `evals/pacific_clarity/screenshots/production/idle-390x844.png`
- `evals/pacific_clarity/screenshots/production/idle-320w.png`
- `evals/pacific_clarity/screenshots/production/spatial-kelowna-1536x1024.png`

## Verdict

FIRELENS_PACIFIC_CLARITY_PRODUCTION_VERIFIED
