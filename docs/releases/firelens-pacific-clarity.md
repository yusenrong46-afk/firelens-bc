# FireLens — Pacific Clarity release

## Identity
- Campaign: FireLens — Pacific Clarity
- Branch: `cursor/firelens-pacific-clarity`
- Base main SHA: `58eb80153358c82a5be1da095245e627b5c0ed05`
- Current production: deployment `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh`, build `40c4c970bf33192ce6a543a6b8dcf5b4799036bd`, release `1.6.4`
- Prior production (rollback for this increment): `dpl_6hi3MjUuxWwsCQejPqCv8EgyC6t9` @ `422d80dd346c0edf71eea41e144dcf2089dc2397`
- Older pre-Pacific production: `dpl_GYhPvwts3LkZoAqNQmpixLPeprwX` @ `b8e07eb`

## Product changes
Calm evidence-first shell with sidebar navigation, compact spatial map rail, stronger live-answer hierarchy and source proof, truthful readiness badge, and multi–Fire Centre clarification.

Follow-up increment (`40c4c97`): live badge stays honest when official layers are missing; follow-up composer sits below the answer; analysis keeps the sidebar beside the chat instead of stacking it.

## Safety / evidence
Authority invariants preserved. ClaimBench v2 floor held. Hard probe rc2.2 offline passed. No RAG/model architecture change.

## Performance
Initial JS gzip +2.55% (≤5% cap). CSS grew; map/charts remain lazy. No extra provider calls for UI.

## Deploy status

Production verified at https://firelens-bc.vercel.app/

- deployment_id: `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh`
- build_commit: `40c4c970bf33192ce6a543a6b8dcf5b4799036bd`
- Preview: `https://firelens-4lwvh4bsy-yusenrong46-9212s-projects.vercel.app` (`dpl_CyJvBfMTtfUU7cbSj3Ragrf8Y4QU`)
- Product Reality Gate: 16/16 on preview and production
- Follow-up UI: composer below the thread; guided analysis has no `pc-layout--solo`

Terminal state: FIRELENS_PACIFIC_CLARITY_PRODUCTION_VERIFIED
