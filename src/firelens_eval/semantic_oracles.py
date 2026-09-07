"""Bounded diagnostics and versioned current acceptance; frozen rc2.2 is unchanged.

These checks use public evidence and explicit fixture truth, not production
classification helpers. Passing them proves only the enumerated invariants.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def provenance_issues(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    evidence = {row["evidence_id"]: row for row in payload.get("evidence", [])}
    records = payload.get("live_results", [])
    label = (payload.get("status_banner") or {}).get("availability_label", "").lower()
    if not evidence and not records and not payload.get("requested_layers"):
        if "sources required for this request were available" in label:
            issues.append("unestablished_source_availability")
    claims = {row["claim_id"]: row for row in payload.get("claims", [])}
    for claim in claims.values():
        background = claim.get("evidence_status") == "general_background"
        for support in claim.get("supports", []):
            item = evidence.get(support.get("evidence_id"))
            if item is None:
                issues.append("missing_support_reference")
            elif not support.get("quote") or support["quote"] not in item.get(
                "primary_text", ""
            ):
                issues.append("unsupported_quote")
        if not background and not claim.get("supports"):
            # Structured claims have a separate typed authority contract.
            kind = (claim.get("publication") or {}).get("kind")
            if kind not in {"structured_reviewed", "official_live_typed"}:
                issues.append("claim_without_support")
    for card in payload.get("proof_cards", []):
        claim = claims.get(card.get("claim_id"))
        if claim and claim.get("evidence_status") == "general_background":
            if "reviewed" in card.get("authority", "").lower():
                issues.append("background_claims_reviewed_authority")
    return issues


def unsupported_fixture_issues(payload: dict[str, Any], *, forbidden_fact: str) -> list[str]:
    """A label cannot excuse publishing a fact explicitly false in a fixture."""
    text = " ".join(
        [
            str(payload.get("answer") or ""),
            *[str(c.get("text", "")) for c in payload.get("claims", [])],
        ]
    ).casefold()
    return ["fabricated_fixture_fact"] if forbidden_fact.casefold() in text else []


# Versioned, reviewed acceptance of exact historical representation discrepancies.
# This does not alter any frozen row, profile, runner exit, or global PASS meaning.
CURRENT_DISPOSITIONS = Path("data/evaluation/hard_probe_current_dispositions.v1.json")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def reviewed_row_projection(row: dict[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(row)
    projected.pop("latency_ms", None)
    projected["response"].pop("trace_id", None)
    for stage in projected.get("provider_stages", []):
        stage.pop("latency_ms", None)
    return projected


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("trace_id", None)
    result.pop("http_status", None)
    return result


async def current_i08_trajectory() -> list[dict[str, Any]]:
    from firelens.contracts import ConversationTurn, QueryRequest
    from firelens.evaluation.source_aware_conversation_runtime import fixture_agent

    turns = []
    history: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="firelens-i08-") as temporary:
        agent, provider, _ = await fixture_agent(Path(temporary))
        for question in ["...", "order?"]:
            before = provider.generate_calls
            execution = await agent.answer(
                QueryRequest(
                    question=question,
                    history=[ConversationTurn.model_validate(t) for t in history],
                )
            )
            response = execution.response.model_dump(mode="json")
            turns.append(
                {
                    "question": question,
                    "request_history": list(history),
                    "generation_calls": provider.generate_calls - before,
                    "response": response,
                }
            )
            history.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": response["history_text"]},
                ]
            )
    return turns


def current_disposition_issues(report: dict[str, Any], *, root: Path) -> list[str]:
    """Fail closed on changed meaning, missing proof, or stale qualification inputs.

    Historical mode failures stay FAIL. Current acceptance additionally requires
    the independently reviewed exact response and obligation-specific evidence.
    No natural-language inference or case-ID-only exemption is performed here.
    """
    from firelens.contracts import AskResponse
    from firelens.evaluation import hard_probe_cli
    from firelens.evaluation.j01_current_acceptance import validate_current_j01

    issues = []
    try:
        evidence = json.loads((root / CURRENT_DISPOSITIONS).read_text())
        if evidence["schema_version"] != "firelens.hard_probe.current_dispositions.v1":
            raise ValueError("unsupported current disposition schema")
        for group in ["frozen_materials", "runtime_materials"]:
            if not evidence[group]:
                raise ValueError(f"missing {group}")
            for name, expected in evidence[group].items():
                if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                    issues.append(f"current disposition {group} changed: {name}")
        tracked = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
        runtime_paths = {
            name
            for name in tracked
            if (
                name.startswith("src/firelens/")
                and not name.startswith("src/firelens/evaluation/")
            )
            or (name.startswith("data/") and not name.startswith("data/evaluation/"))
            or name in {"pyproject.toml", "requirements.lock", "uv.lock"}
        }
        if runtime_paths != set(evidence["runtime_materials"]):
            issues.append("current disposition runtime material set changed")
        dispositions = evidence["dispositions"]
        expected_ids = {"F06", "F07", "F09", "I04", "K03", "K09", "I08", "J01", "L05"}
        if set(dispositions) != expected_ids:
            issues.append("current dispositions incomplete")
        failed = {row["id"]: row for row in report["results"] if row["passed"] is not True}
        if set(failed) != expected_ids:
            issues.append("historical failures differ from reviewed discrepancies")
        for case_id, disposition in dispositions.items():
            row = failed.get(case_id)
            if not row:
                continue
            if disposition["classification"] != "A" or not disposition["current_obligation"]:
                issues.append(f"{case_id}: missing reviewed disposition")
            if _digest(reviewed_row_projection(row)) != disposition["historical_row_sha256"]:
                issues.append(f"{case_id}: changed historical semantic payload or diagnostics")
            response = row["response"]
            AskResponse.model_validate(
                {k: v for k, v in response.items() if k != "http_status"}
            )
            issues.extend(f"{case_id}: {issue}" for issue in provenance_issues(response))
            if case_id == "J01":
                with tempfile.TemporaryDirectory(prefix="firelens-current-j01-") as temporary:
                    output = Path(temporary) / "j01.json"
                    args = hard_probe_cli.parse_args(
                        [
                            "--mode",
                            "offline",
                            "--expectation-profile",
                            "rc2.3",
                            "--case-id",
                            "J01",
                            "--output",
                            str(output),
                        ]
                    )
                    with contextlib.redirect_stdout(io.StringIO()):
                        native_exit = asyncio.run(hard_probe_cli.run(args))
                    current_report = json.loads(output.read_text())
                    if native_exit != 0 or len(current_report["results"]) != 1:
                        raise ValueError("current J01 execution failed or incomplete")
                    current = current_report["results"][0]
                    validate_current_j01(current, root=root)
                    if _public_payload(current["response"]) != _public_payload(response):
                        issues.append("current J01 differs from historical response")
        # Exact full public response binding protects meaning, including history,
        # source revision, quotes, personal-action surfaces and authority labels.
        observed_turns = asyncio.run(current_i08_trajectory())
        required_turns = evidence["i08_trajectory"]
        if len(required_turns) != 2:
            raise ValueError("I08 trajectory incomplete")
        for observed, expected in zip(observed_turns, required_turns, strict=True):
            AskResponse.model_validate(observed["response"])
            for turn in [observed, expected]:
                turn["response"] = _public_payload(turn["response"])
            if observed != expected or observed["generation_calls"] != 0:
                issues.append("I08 successive-turn current response changed")
            issues.extend(provenance_issues(observed["response"]))
        l05 = evidence["l05_current_provider_observation"]
        if (
            l05["http_status"] != 200
            or l05["request"]["question"] != dispositions["L05"]["question"]
        ):
            issues.append("L05 current provider observation missing or wrong request")
        AskResponse.model_validate(l05["response"])
        issues.extend(provenance_issues(l05["response"]))
        # The evidence itself is pinned by the versioned policy file. It contains
        # the reviewed complete output, not the deliberately generic fake answer.
    except (KeyError, ValueError, TypeError, OSError) as exc:
        issues.append(f"current disposition evidence invalid: {exc}")
    return issues
