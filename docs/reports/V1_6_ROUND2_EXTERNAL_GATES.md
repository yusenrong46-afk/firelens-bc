# FireLens V1.6 Round-2 external and packaging gates

These commands are prepared on the Round-2 candidate. Do not treat this file
as executed preview, rollback, firewall, or human evidence.

`.dockerignore` excludes `data/evaluation`, `docs`, `tests`, and `output`, so
sealed and benchmark files are not image contents by declaration. Staged Docker
and Vercel filesystem inventories remain unexecuted here because Docker and
Vercel CLIs are absent.

## Local packaging

| Gate | Status | Command |
| --- | --- | --- |
| Logical Docker/Vercel allowlist | READY_FOR_EXTERNAL_EXECUTION after `make v1-6-package-verify` | `make v1-6-package-verify` |
| Docker image build + in-container health | BLOCKED | `docker build --build-arg FIRELENS_BUILD_COMMIT=$(git rev-parse HEAD) --build-arg FIRELENS_RELEASE_VERSION=1.6.0-rc.1 -t firelens-bc:v1.6.0-rc.1 .` then `docker run --rm -p 10000:10000 firelens-bc:v1.6.0-rc.1` and `curl -fsS http://127.0.0.1:10000/health` plus `/ready` |
| Docker filesystem inspect | BLOCKED | `docker run --rm --entrypoint sh firelens-bc:v1.6.0-rc.1 -c 'ls /app/data /app/config /app/apps/web/dist/client; test ! -e /app/data/evaluation'` |
| Local Vercel output inspect | BLOCKED | Requires Vercel CLI / authorized preview |

## Preview, rollback, firewall, smoke

Status for each: READY_FOR_EXTERNAL_EXECUTION, not EXECUTED.

Preview:

```text
.venv/bin/python scripts/qualify_preview.py --base-url https://<preview-host> \
  --expected-version 1.6.0-rc.1 --expected-commit <full-release-commit> \
  --raw-evidence-output /absolute/private/v1_6_preview_raw.json
.venv/bin/python scripts/qualify_deployment_gates.py --base-url https://<preview-host>
.venv/bin/python scripts/probe_preview_ask_hard_v2.py --base-url https://<preview-host>
```

Rollback (documentation is not rollback proof):

```text
# Record candidate SHA, deploy SHA, and restored SHA. Rehearse on the authorized
# host, then verify /health, /ready, and runtime_candidate.v1.json match the
# restored commit. Keep the evidence JSON bound to those SHAs.
git rev-parse HEAD
# Platform rollback is host-specific (Vercel instant rollback or Render deploy).
.venv/bin/python scripts/qualify_deployment_gates.py --base-url https://<restored-host>
```

Firewall / rate-limit (do not publish from this tree):

```text
make prepare-firewall
# Review the rendered commands. Publish only with explicit authorization.
```

Production smoke:

```text
make live-smoke
.venv/bin/python scripts/qualify_deployment_gates.py --base-url https://<prod-host> --expect-production
```

Candidate identity:

```text
python -c "import json; from pathlib import Path; print(json.loads(Path('config/runtime_candidate.v1.json').read_text()) if Path('config/runtime_candidate.v1.json').is_file() else 'missing local candidate file')"
curl -fsS https://<host>/api/v1/meta
```

## Human accessibility and comprehension

Status: READY_FOR_EXTERNAL_EXECUTION.

VoiceOver script:

1. Open Ask. Confirm the skip link moves focus to the question field.
2. Enter a grab-and-go question. Confirm the status kicker, answer, limitations, then Proof Cards are in that order.
3. Move to a live Kelowna fires question. Confirm freshness is announced and coordinates are not spoken as raw numbers.
4. Trigger missing-location. Confirm the request for a BC community is spoken.
5. Trigger evacuate-now. Confirm the safety boundary is spoken without a personalized stay/leave decision.

Human comprehension script:

1. Participant asks the alert vs order difference and restates the distinction in their own words.
2. Participant asks live fires near a named BC city and identifies the authority named on the Proof Card.
3. Participant asks a personal “should I leave” question and recognizes that FireLens did not decide for them.
4. Participant sees a stale/cached live answer and does not describe it as current.

Do not mark these human gates EXECUTED until an authorized session produces bound notes.
