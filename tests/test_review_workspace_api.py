from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from firelens.review_workspace.api import create_review_workspace_app
from firelens.review_workspace.inputs import (
    BlindCasePayload,
    BlindClaim,
    BlindRubric,
    ImportedReviewCase,
    InputFileIdentity,
    _build_suite,
    canonical_sha256,
)
from firelens.review_workspace.models import ReviewActor, ReviewSession
from firelens.review_workspace.session import BlindReviewSession

START = datetime(2026, 8, 8, 17, 0, tzinfo=UTC)
TOKENS = {
    "reviewer-a": "a" * 43,
    "reviewer-b": "b" * 43,
    "adjudicator": "c" * 43,
}
ORIGIN = "http://127.0.0.1:8765"


def _coordinator(tmp_path: Path) -> BlindReviewSession:
    source = tmp_path / "bound-input.json"
    source.write_text('{"fixture":true}\n', encoding="utf-8")
    metadata = source.stat()
    identity = InputFileIdentity(
        label="fixture",
        absolute_path=str(source.resolve()),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        size=metadata.st_size,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    payload = BlindCasePayload(
        question="What does the evidence establish?",
        history=(),
        rubric=BlindRubric(
            required_concepts=("scope",),
            forbidden_claims=("certainty",),
            required_limitations=("investigative only",),
        ),
        answer="A scoped conclusion.",
        claims=(BlindClaim(claim_id="claim-1", text="Scoped conclusion"),),
        supports=(),
        local_source_context=(),
    )
    case = ImportedReviewCase(
        case_id="case-001",
        payload=payload,
        payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
        source_id_sha256s=(),
    )
    suite = _build_suite(
        suite_kind="semantic_holdout",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256="d" * 64,
        input_files=(identity,),
        cases=(case,),
    )
    review_session = ReviewSession(
        session_version="firelens_review_session.v1",
        session_id="api-session-001",
        review_kind="semantic",
        artifact_sha256=suite.suite_sha256,
        protocol_sha256="e" * 64,
        created_at=START,
        case_ids=("case-001",),
        actors=(
            ReviewActor(actor_id="reviewer-a", display_name="Human A", role="reviewer"),
            ReviewActor(actor_id="reviewer-b", display_name="Human B", role="reviewer"),
            ReviewActor(
                actor_id="adjudicator",
                display_name="Human Adjudicator",
                role="adjudicator",
            ),
        ),
    )
    ticks = iter(START + timedelta(seconds=value) for value in range(1, 40))
    return BlindReviewSession.create(
        tmp_path / "workspace",
        session=review_session,
        suite=suite,
        clock=lambda: next(ticks),
    )


def _app(tmp_path: Path):
    return create_review_workspace_app(
        _coordinator(tmp_path),
        actor_tokens=TOKENS,
        allowed_origins=(ORIGIN,),
        allowed_hosts=("127.0.0.1",),
    )


def _auth(actor_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[actor_id]}"}


def test_api_requires_actor_capability_and_never_accepts_actor_selection(
    tmp_path: Path,
) -> None:
    asyncio.run(_api_requires_actor_capability(tmp_path))


async def _api_requires_actor_capability(tmp_path: Path) -> None:
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        reviewer_client = await client.get("/review")
        assert reviewer_client.status_code == 200
        assert "Load your private capability" in reviewer_client.text
        assert "script-src 'self'" in reviewer_client.headers["content-security-policy"]
        assert reviewer_client.headers["cache-control"].startswith("no-store")
        assert (await client.get("/review/review.js")).status_code == 200
        assert (await client.get("/review/review.css")).status_code == 200

        missing = await client.get("/api/v1/review/progress")
        assert missing.status_code == 401
        assert missing.headers["cache-control"].startswith("no-store")
        assert "www-authenticate" in missing.headers

        own = await client.get("/api/v1/review/progress", headers=_auth("reviewer-a"))
        assert own.status_code == 200
        assert own.json()["actor_id"] == "reviewer-a"

        context = await client.get("/api/v1/review/context", headers=_auth("reviewer-a"))
        assert context.status_code == 200
        assert context.json()["qualification_eligible"] is False
        assert context.json()["actor_display_name"] == "Human A"

        attempted_override = await client.get(
            "/api/v1/review/progress?actor_id=reviewer-b",
            headers=_auth("reviewer-a"),
        )
        assert attempted_override.status_code == 200
        assert attempted_override.json()["actor_id"] == "reviewer-a"


def test_api_refuses_nonloopback_bad_host_and_cross_origin(tmp_path: Path) -> None:
    asyncio.run(_api_refuses_nonloopback_bad_host_and_cross_origin(tmp_path))


async def _api_refuses_nonloopback_bad_host_and_cross_origin(tmp_path: Path) -> None:
    app = _app(tmp_path)
    remote_transport = httpx.ASGITransport(app=app, client=("198.51.100.20", 54000))
    async with httpx.AsyncClient(
        transport=remote_transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get("/api/v1/review/progress", headers=_auth("reviewer-a"))
        assert response.status_code == 403
        assert response.json()["error"] == "local_only"

    local_transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54000))
    async with httpx.AsyncClient(
        transport=local_transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get(
            "/api/v1/review/progress",
            headers={**_auth("reviewer-a"), "Host": "evil.local"},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "invalid_host"

    async with httpx.AsyncClient(
        transport=local_transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post(
            "/api/v1/review/present",
            headers={**_auth("reviewer-a"), "Origin": "http://attacker.test"},
            json={},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "invalid_origin"


def test_api_exposes_blind_payload_and_receipt_bound_transition(tmp_path: Path) -> None:
    asyncio.run(_api_exposes_blind_payload_and_receipt_bound_transition(tmp_path))


async def _api_exposes_blind_payload_and_receipt_bound_transition(tmp_path: Path) -> None:
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54000))
    headers = {**_auth("reviewer-a"), "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        opened = await client.post("/api/v1/review/present", headers=headers, json={})
        assert opened.status_code == 200
        presentation = opened.json()
        serialized = opened.text.casefold()
        assert presentation["actor_id"] == "reviewer-a"
        assert presentation["review_material"] == []
        assert "ranking" not in serialized
        assert "model_id" not in serialized
        assert opened.headers["x-frame-options"] == "DENY"

        recovered = await client.get(
            "/api/v1/review/current",
            headers=_auth("reviewer-a"),
        )
        assert recovered.status_code == 200
        assert recovered.json() == presentation

        other_actor = await client.get(
            "/api/v1/review/current",
            headers=_auth("reviewer-b"),
        )
        assert other_actor.status_code == 409

        acknowledged = await client.post(
            "/api/v1/review/acknowledge",
            headers=headers,
            json={"presentation_id": presentation["presentation_id"]},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["event_type"] == "presentation.display_acknowledged"

        decision = await client.post(
            "/api/v1/review/decision",
            headers=headers,
            json={
                "presentation_id": presentation["presentation_id"],
                "decision": {
                    "disposition": "approve",
                    "required_concepts_present": True,
                    "forbidden_claims_absent": True,
                    "required_limitations_present": True,
                    "question_is_independent": None,
                    "answerability_correct": None,
                    "acceptable_evidence_correct": None,
                    "claims": [{"claim_id": "claim-1", "decision": "supported", "notes": ""}],
                    "notes": "",
                },
            },
        )
        assert decision.status_code == 200
        assert decision.json()["event_type"] == "case.decision.recorded"

        progress = await client.get("/api/v1/review/progress", headers=_auth("reviewer-a"))
        assert progress.json()["actor_state"] == "complete_pending_lock"


def test_api_bounds_json_body_and_sanitizes_invalid_transition(tmp_path: Path) -> None:
    asyncio.run(_api_bounds_json_body_and_sanitizes_invalid_transition(tmp_path))


async def _api_bounds_json_body_and_sanitizes_invalid_transition(tmp_path: Path) -> None:
    app = create_review_workspace_app(
        _coordinator(tmp_path),
        actor_tokens=TOKENS,
        allowed_origins=(ORIGIN,),
        allowed_hosts=("127.0.0.1",),
        max_body_bytes=128,
    )
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54000))
    headers = {
        **_auth("reviewer-a"),
        "Origin": ORIGIN,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        too_large = await client.post(
            "/api/v1/review/present",
            headers=headers,
            content=b"{" + (b'"padding":"' + b"x" * 200 + b'"}'),
        )
        assert too_large.status_code == 413

        invalid = await client.post("/api/v1/review/lock", headers=headers, json={})
        assert invalid.status_code == 409
        assert invalid.json() == {
            "error": "invalid_transition",
            "message": "The review transition is not permitted.",
        }
