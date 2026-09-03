"""Execution-backed, unsealed source-aware conversation evaluation.

The fixture is deliberately unsealed. This module builds a fresh local vector
index and runs the real agent against deterministic provider/live doubles; it
does not infer a result from the expected label.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import yaml

from firelens.contracts import LocationInput
from firelens.guidance_capabilities import (
    guided_catalogue_sha256,
    load_guided_question_registry,
)

ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT / "data/evaluation/source_aware_conversation.v1.yaml"
MANIFEST_PATH = ROOT / "data/evaluation/source_aware_conversation.v1.manifest.json"
SCHEMA_VERSION = "firelens.source_aware_conversation.v1"
REPORT_SCHEMA_VERSION = "firelens.source_aware_conversation.report.v1"
EXPECTED_SPECIAL_FAMILIES = {
    "safe_general",
    "official_context",
    "relative_clause",
    "deictic_followup",
    "mixed_lane",
    "adversarial",
    "empty",
    "provider_failure",
    "location_required",
}
VALID_MODES = {
    "grounded",
    "background",
    "capability",
    "scope_redirect",
    "abstention",
    "partial",
    "live",
    "mixed",
    "conflict",
    "requires_input",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(root: Path, *args: str) -> str | None:
    try:
        return (
            subprocess.run(
                ["git", *args], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_dataset(path: Path = DATASET_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "source-aware dataset must be an object")
    _require(
        payload.get("schema_version") == SCHEMA_VERSION,
        "source-aware dataset schema is invalid",
    )
    _require(
        payload.get("status") == "development_unsealed",
        "source-aware dataset must remain unsealed",
    )
    canonical = payload.get("canonical_cases")
    _require(
        isinstance(canonical, list) and len(canonical) == 24,
        "source-aware dataset must contain 24 canonical cases",
    )
    ids: set[str] = set()
    for case in canonical:
        _require(isinstance(case, dict), "canonical case must be an object")
        case_id = case.get("id")
        _require(
            isinstance(case_id, str) and case_id not in ids, "canonical case IDs must be unique"
        )
        ids.add(case_id)
        _require(
            case.get("source_lane") in {"official_live", "reviewed_guidance", "official_quote"},
            f"{case_id} has invalid source lane",
        )
        _require(
            case.get("expected_mode") in VALID_MODES, f"{case_id} has invalid expected mode"
        )
        paraphrases = case.get("paraphrases")
        _require(
            isinstance(paraphrases, list) and len(paraphrases) >= 3,
            f"{case_id} needs at least three paraphrases",
        )
        _require(
            all(isinstance(value, str) and value.strip() for value in paraphrases),
            f"{case_id} has invalid paraphrases",
        )
        _require(
            isinstance(case.get("question"), str) and case["question"].strip(),
            f"{case_id} has no canonical question",
        )
        if "{place}" in case["question"]:
            _require(
                case.get("location_mode") == "required",
                f"{case_id} location template must require a location",
            )
    conversations = payload.get("reproduced_conversations")
    _require(
        isinstance(conversations, list) and len(conversations) == 3,
        "source-aware dataset must contain three reproduced conversations",
    )
    _require(
        len({item.get("id") for item in conversations}) == 3,
        "reproduced conversation IDs must be unique",
    )
    specials = payload.get("special_cases")
    _require(isinstance(specials, list), "source-aware dataset special cases are missing")
    families = {item.get("family") for item in specials if isinstance(item, dict)}
    families.update(item.get("family") for item in conversations if isinstance(item, dict))
    _require(
        EXPECTED_SPECIAL_FAMILIES.issubset(families),
        "source-aware special-case families are incomplete",
    )
    acceptance = payload.get("acceptance")
    _require(isinstance(acceptance, dict), "source-aware acceptance metrics are missing")
    _require(
        acceptance.get("canonical_case_count") == 24,
        "source-aware canonical acceptance count is invalid",
    )
    _require(
        acceptance.get("minimum_paraphrases_per_canonical", 0) >= 3,
        "source-aware paraphrase floor is invalid",
    )
    _require(
        acceptance.get("minimum_canonical_pass_rate") == 1.0,
        "source-aware canonical pass threshold is invalid",
    )
    _require(
        acceptance.get("minimum_routing_recall") == 0.95,
        "source-aware routing threshold is invalid",
    )
    _require(
        acceptance.get("minimum_official_compliance") == 1.0,
        "source-aware official threshold is invalid",
    )
    _require(
        acceptance.get("maximum_unnecessary_handoff_rate") == 0.05,
        "source-aware handoff threshold is invalid",
    )
    _require(
        acceptance.get("maximum_authority_escalation") == 0,
        "source-aware escalation threshold is invalid",
    )
    _require(
        acceptance.get("minimum_safe_general_answer_rate") == 0.95,
        "source-aware safe-general threshold is invalid",
    )
    _require(
        acceptance.get("maximum_tier_a_b_generation_calls") == 0,
        "source-aware generation gate must be zero",
    )
    _require(
        acceptance.get("maximum_tier_a_b_generation_cost_usd") == 0.0,
        "source-aware generation cost gate must be zero",
    )
    return cast(dict[str, Any], payload)


def validate_registry_binding(dataset: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    registry = load_guided_question_registry(str(root))
    capability_payload = json.loads(
        (root / "data/capabilities/firelens.guidance_capabilities.v1.json").read_text(
            encoding="utf-8"
        )
    )
    _require(
        capability_payload.get("corpus_chunks_sha256")
        == file_sha256(root / "data/processed/firelens_static_corpus.chunks.jsonl"),
        "capability registry corpus hash does not match",
    )
    _require(
        capability_payload.get("corpus_manifest_sha256")
        == file_sha256(root / "data/processed/firelens_static_corpus.manifest.json"),
        "capability registry manifest hash does not match",
    )
    _require(
        capability_payload.get("typed_inventory_sha256")
        == file_sha256(root / "data/typed_claims/high_risk_v1.yaml"),
        "capability registry typed-inventory hash does not match",
    )
    capabilities = {
        question_id: binding
        for binding in capability_payload.get("capabilities", [])
        for question_id in binding.get("guided_question_ids", [])
    }
    by_id = {item.id: item for item in registry.questions}
    for case in dataset["canonical_cases"]:
        item = by_id.get(case["guided_question_id"])
        if item is None:
            raise ValueError(f"{case['id']} references an unknown guided question")
        _require(
            item.question == case["question"],
            f"{case['id']} question does not match the guided registry",
        )
        _require(
            item.source_lane == case["source_lane"],
            f"{case['id']} source lane does not match the guided registry",
        )
        binding = cast(dict[str, Any] | None, capabilities.get(case["guided_question_id"]))
        if binding is None or binding.get("guided_eligible") is not True:
            raise ValueError(f"{case['id']} lacks an eligible capability binding")
        expected_lane = (
            "official_live"
            if binding.get("source_mode") == "official_live" or binding.get("live_layers")
            else "official_quote"
            if binding.get("coverage_state") == "quote_ready"
            else "reviewed_guidance"
        )
        _require(
            item.source_lane == expected_lane,
            f"{case['id']} source lane does not match capability coverage",
        )
    return {
        "guided_registry_sha256": guided_catalogue_sha256(str(root)),
        "guided_question_count": len(registry.questions),
    }


def validate_manifest_binding(
    dataset_path: Path = DATASET_PATH,
    manifest_path: Path = MANIFEST_PATH,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Check the unsealed manifest before any runtime observation is scored."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(
        manifest.get("schema_version") == "firelens.source_aware_conversation.manifest.v1",
        "source-aware manifest schema is invalid",
    )
    _require(
        manifest.get("dataset_sha256") == file_sha256(dataset_path),
        "source-aware manifest dataset hash does not match",
    )
    _require(
        manifest.get("canonical_case_count") == 24,
        "source-aware manifest canonical count is invalid",
    )
    _require(
        manifest.get("paraphrase_count") == 72,
        "source-aware manifest paraphrase count is invalid",
    )
    _require(
        manifest.get("total_case_count") == 106, "source-aware manifest total count is invalid"
    )
    if root is not None:
        _require(
            manifest.get("guided_registry_sha256")
            == file_sha256(root / "data/capabilities/guided_questions.v1.json"),
            "source-aware manifest guided registry hash does not match",
        )
        _require(
            manifest.get("capability_registry_sha256")
            == file_sha256(root / "data/capabilities/firelens.guidance_capabilities.v1.json"),
            "source-aware manifest capability registry hash does not match",
        )
    return cast(dict[str, Any], manifest)


def _expand(question: str) -> tuple[str, LocationInput | None]:
    if "{place}" in question:
        return question.replace("{place}", "Kelowna, BC"), LocationInput(label="Kelowna, BC")
    return question, None


def score_observation(case: dict[str, Any], observed: dict[str, Any]) -> dict[str, bool]:
    """Closed predicates over observed runtime data; useful for mutation tests."""
    expected_mode = case.get("expected_mode")
    expected_lane = case.get("expected_source_lane", case.get("source_lane"))
    strict = bool(case.get("strict_source_lane", True))
    observed_mode = observed.get("response_mode")
    if strict or expected_mode not in {"grounded", "partial", "live", "mixed"}:
        mode_matches = observed_mode == expected_mode
    elif expected_mode in {"grounded", "partial"}:
        mode_matches = observed_mode in {"grounded", "partial"}
    elif expected_mode == "live":
        mode_matches = observed_mode in {"live", "mixed"}
    else:
        mode_matches = observed_mode == "mixed"
    if not strict and expected_lane in {"reviewed_guidance", "official_quote"}:
        lane_matches = observed.get("observed_source_lane") in {
            "reviewed_guidance",
            "official_quote",
        }
    else:
        lane_matches = observed.get("observed_source_lane") == expected_lane
    checks = {
        "request_valid": observed.get("request_valid", False)
        or case.get("require_nonempty_answer") is False,
        "expected_mode": mode_matches,
        "source_lane": expected_lane is None
        or expected_mode == "requires_input"
        or lane_matches,
        "has_answer": not case.get("require_nonempty_answer", True)
        or observed.get("has_answer", False),
        "tier_a_b_generation": int(observed.get("tier_a_b_generation_calls", 0)) == 0,
    }
    if expected_lane == "official_live" and expected_mode != "requires_input":
        checks["official_compliance"] = observed.get("live_result_count", 0) > 0 and bool(
            set(observed.get("tool_traces", []))
            & {"list_official_fires", "list_official_evacuations", "get_official_fire"}
        )
    elif expected_lane in {"reviewed_guidance", "official_quote"}:
        checks["reviewed_compliance"] = (
            observed.get("evidence_count", 0) > 0 and observed.get("claim_count", 0) > 0
        )
        if expected_lane == "official_quote" and strict:
            checks["quote_only"] = set(observed.get("publication_kinds", [])) == {
                "official_quote_only"
            }
    elif expected_lane == "mixed":
        checks["mixed_lane"] = observed.get("observed_source_lane") == "mixed"
    if case.get("require_no_source_implication"):
        checks["no_source_implication"] = (
            observed.get("observed_source_lane") in {None, "general"}
            and observed.get("live_result_count", 0) == 0
        )
    if case.get("require_no_map"):
        checks["no_map_tool"] = not any(
            "map" in value for value in observed.get("tool_traces", [])
        )
    if case.get("require_safety_handoff"):
        checks["safety_handoff"] = (
            observed.get("route") == "prohibited"
            or observed.get("response_mode") == "abstention"
        )
    if case.get("require_no_status_claim"):
        checks["no_status_claim"] = (
            observed.get("status") in {"error", "abstention"}
            and observed.get("claim_count", 0) == 0
        )
    checks["no_unnecessary_handoff"] = not (
        expected_mode in {"live", "grounded", "partial", "mixed"}
        and observed_mode in {"scope_redirect", "background", "abstention", "requires_input"}
    )
    checks["no_authority_escalation"] = not (
        (
            expected_lane == "reviewed_guidance"
            and "official_live_typed" in set(observed.get("publication_kinds", []))
        )
        or (
            strict
            and expected_lane == "official_quote"
            and bool(
                set(observed.get("publication_kinds", []))
                & {"structured_reviewed", "official_live_typed"}
            )
        )
    )
    return checks


async def execute_offline(
    dataset: dict[str, Any], *, root: Path = ROOT
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    from firelens.evaluation.source_aware_conversation_runtime import (
        execute_one,
        fixture_agent,
    )

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="firelens-source-aware-") as temp:
        agent, provider, fixture_identity = await fixture_agent(Path(temp))
        for case in dataset["canonical_cases"]:
            question, location = _expand(case["question"])
            for case_id, text, strict_source_lane in [
                (case["id"], question, True),
                *[
                    (f"{case['id']}-P{i}", _expand(value)[0], False)
                    for i, value in enumerate(case["paraphrases"], 1)
                ],
            ]:
                expanded, loc = _expand(text)
                observed = await execute_one(
                    agent, provider, case_id, expanded, location=location or loc
                )
                observed.update(
                    expected_mode=case["expected_mode"],
                    expected_source_lane=case["source_lane"],
                )
                scored_case = {**case, "strict_source_lane": strict_source_lane}
                observed["checks"] = score_observation(scored_case, observed)
                observed["passed"] = all(observed["checks"].values())
                results.append(observed)
        for conversation in dataset["reproduced_conversations"]:
            history, question = conversation["turns"][:-1], conversation["turns"][-1]["content"]
            location = (
                LocationInput(label="Kelowna, BC")
                if conversation["id"] == "SA-CONV-03"
                else None
            )
            observed = await execute_one(
                agent,
                provider,
                conversation["id"],
                question,
                location=location,
                history=history,
            )
            observed.update(
                expected_mode=conversation["expected_mode"],
                expected_source_lane=conversation["expected_source_lane"],
            )
            observed["checks"] = score_observation(
                {**conversation, "strict_source_lane": False}, observed
            )
            observed["passed"] = all(observed["checks"].values())
            results.append(observed)
        for case in dataset["special_cases"]:
            question, location = _expand(case["question"])
            if case["family"] == "location_required":
                question, location = "What official wildfire records are near my place?", None
            if case["family"] == "empty":
                question = ""
            case_agent, case_provider = agent, provider
            if case["family"] == "provider_failure":
                case_agent, case_provider, _ = await fixture_agent(
                    Path(temp) / "failure", failing_generation=True
                )
            observed = await execute_one(
                case_agent, case_provider, case["id"], question, location=location
            )
            observed.update(
                expected_mode=case["expected_mode"],
                expected_source_lane=case.get("expected_source_lane"),
            )
            observed["checks"] = score_observation(case, observed)
            observed["passed"] = all(observed["checks"].values())
            results.append(observed)
    return results, fixture_identity


async def build_report_async(
    dataset: dict[str, Any] | None = None, *, root: Path = ROOT
) -> dict[str, Any]:
    dataset = dataset or load_dataset(
        root / "data/evaluation/source_aware_conversation.v1.yaml"
    )
    validate_manifest_binding(
        root / "data/evaluation/source_aware_conversation.v1.yaml",
        root / "data/evaluation/source_aware_conversation.v1.manifest.json",
        root=root,
    )
    binding = validate_registry_binding(dataset, root=root)
    results, fixture_identity = await execute_offline(dataset, root=root)
    acceptance = dataset["acceptance"]
    generation_calls = sum(int(item.get("tier_a_b_generation_calls", 0)) for item in results)
    generation_cost = sum(
        float(item.get("tier_a_b_generation_cost_usd", 0.0)) for item in results
    )
    passed = sum(1 for item in results if item["passed"])
    routing = [item for item in results if item.get("expected_mode") is not None]
    official = [
        item
        for item in results
        if item.get("expected_source_lane")
        in {"official_live", "reviewed_guidance", "official_quote"}
        and item.get("expected_mode") != "requires_input"
    ]
    canonical = [
        item
        for item in results
        if item.get("id", "").startswith("SA-GQ-") and "-P" not in item.get("id", "")
    ]
    local_provider_calls = sum(
        sum(int(value) for value in item.get("provider_calls", {}).values()) for item in results
    )
    unnecessary_handoff_rate = (
        sum(not item.get("checks", {}).get("no_unnecessary_handoff", False) for item in results)
        / len(results)
        if results
        else 0.0
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_sha256": file_sha256(
            root / "data/evaluation/source_aware_conversation.v1.yaml"
        ),
        "guided_registry_sha256": binding["guided_registry_sha256"],
        "artifact_identity": {
            "dataset_sha256": file_sha256(
                root / "data/evaluation/source_aware_conversation.v1.yaml"
            ),
            "dataset_manifest_sha256": file_sha256(
                root / "data/evaluation/source_aware_conversation.v1.manifest.json"
            ),
            "runner_sha256": file_sha256(
                root / "src/firelens/evaluation/source_aware_conversation.py"
            ),
            "guided_registry_sha256": binding["guided_registry_sha256"],
            "guided_manifest_sha256": file_sha256(
                root / "data/capabilities/guided_questions.v1.manifest.json"
            ),
            "capability_registry_sha256": file_sha256(
                root / "data/capabilities/firelens.guidance_capabilities.v1.json"
            ),
            "corpus_sha256": fixture_identity["corpus_sha256"],
            "corpus_manifest_sha256": fixture_identity["corpus_manifest_sha256"],
            "vector_matrix_sha256": fixture_identity["vector_matrix_sha256"],
            "vector_manifest_sha256": fixture_identity["vector_manifest_sha256"],
            "typed_inventory_sha256": file_sha256(root / "data/typed_claims/high_risk_v1.yaml"),
            "commit": _git_value(root, "rev-parse", "HEAD"),
            "tree": _git_value(root, "rev-parse", "HEAD^{tree}"),
            "working_tree_status_sha256": hashlib.sha256(
                (_git_value(root, "status", "--porcelain") or "").encode()
            ).hexdigest(),
        },
        "execution": {
            "mode": "offline_deterministic_executed",
            "provider_boundary": "fake_provider_only",
            "external_network_calls": 0,
            "external_model_calls": 0,
            "local_fake_provider_calls": local_provider_calls,
            "local_fake_provider_cost_usd": 0.0,
        },
        "case_counts": {
            "canonical": len(dataset["canonical_cases"]),
            "paraphrase": sum(len(case["paraphrases"]) for case in dataset["canonical_cases"]),
            "reproduced_conversations": len(dataset["reproduced_conversations"]),
            "special": len(dataset["special_cases"]),
            "total": len(results),
        },
        "metrics": {
            "passed": passed,
            "failed": len(results) - passed,
            "case_pass_rate": passed / len(results) if results else 0.0,
            "canonical_pass_rate": sum(item["passed"] for item in canonical) / len(canonical)
            if canonical
            else 0.0,
            "routing_recall": sum(
                item.get("checks", {}).get("expected_mode", False) for item in routing
            )
            / len(routing)
            if routing
            else 0.0,
            "official_compliance": sum(
                item.get("checks", {}).get("source_lane", False)
                and item.get("checks", {}).get(
                    "official_compliance",
                    item.get("checks", {}).get("reviewed_compliance", False)
                    and item.get("checks", {}).get("quote_only", True),
                )
                for item in official
            )
            / len(official)
            if official
            else 0.0,
            "unnecessary_handoff": sum(
                not item.get("checks", {}).get("no_unnecessary_handoff", False)
                for item in results
            ),
            "unnecessary_handoff_rate": unnecessary_handoff_rate,
            "authority_escalation": sum(
                not item.get("checks", {}).get("no_authority_escalation", False)
                for item in results
            ),
            # An unrelated question is answered safely either as labelled general
            # knowledge or with the product scope note; never with source proof.
            "safe_general_answer_rate": sum(
                item.get("response_mode") in {"background", "capability"}
                and item.get("checks", {}).get("no_source_implication", False)
                for item in results
            )
            / max(1, sum(item.get("id") == "SA-SAFE-01" for item in results)),
            "tier_a_b_generation_calls": generation_calls,
            "tier_a_b_generation_cost_usd": generation_cost,
        },
        "acceptance": acceptance,
        "results": results,
    }
    report["passed"] = (
        report["metrics"]["canonical_pass_rate"] >= acceptance["minimum_canonical_pass_rate"]
        and report["metrics"]["routing_recall"] >= acceptance["minimum_routing_recall"]
        and report["metrics"]["official_compliance"]
        >= acceptance["minimum_official_compliance"]
        and report["metrics"]["unnecessary_handoff_rate"]
        <= acceptance["maximum_unnecessary_handoff_rate"]
        and report["metrics"]["authority_escalation"]
        <= acceptance["maximum_authority_escalation"]
        and report["metrics"]["safe_general_answer_rate"]
        >= acceptance["minimum_safe_general_answer_rate"]
        and generation_calls <= acceptance["maximum_tier_a_b_generation_calls"]
        and generation_cost <= acceptance["maximum_tier_a_b_generation_cost_usd"]
    )
    return report


def build_report(dataset: dict[str, Any] | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    return asyncio.run(build_report_async(dataset, root=root))


def run(output: Path, *, root: Path = ROOT) -> int:
    report = build_report(root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1
