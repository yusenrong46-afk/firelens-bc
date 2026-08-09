"""Prepare, serve, export, or verify a FireLens blind human-review workspace."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import uvicorn
import yaml

from firelens.evaluation.common import file_sha256
from firelens.evaluation.frontend_manual_protocol import _frontend_manual_review_protocol
from firelens.evaluation.frontend_manual_review import validate_frontend_manual_review
from firelens.evaluation.release_surfaces import _write_ux_template
from firelens.evaluation.upgrade_cli import (
    DEFAULT_SPEC,
    FRONTEND_MANUAL_REVIEW_PROTOCOL,
    load_spec,
)
from firelens.evaluation.ux import _named_frontend_reviewer, _ux
from firelens.review_workspace.analysis import (
    verify_review_analysis,
    write_review_analysis,
)
from firelens.review_workspace.api import create_review_workspace_app
from firelens.review_workspace.exports import (
    verify_finalized_evidence_export,
    write_finalized_evidence_export,
)
from firelens.review_workspace.preparation import (
    ReviewInputRecipe,
    prepare_review_session,
    resume_prepared_review,
)
from firelens.review_workspace.qualification import (
    build_review_qualification,
    verify_review_qualification_package,
    write_storage_attestation_template,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "docs/protocols/V1_5_2_HUMAN_REVIEW_RUNBOOK.md"


def _absolute(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _new_workspace(value: str) -> Path:
    path = _absolute(value)
    lexical = path.parent.resolve(strict=True) / path.name
    if ROOT == lexical or ROOT in lexical.parents:
        raise argparse.ArgumentTypeError("review workspaces must live outside the repository")
    if lexical.exists() or lexical.is_symlink():
        raise argparse.ArgumentTypeError("new review workspace path must not already exist")
    return lexical


def _existing_workspace(value: str) -> Path:
    path = _absolute(value).resolve(strict=True)
    if ROOT == path or ROOT in path.parents:
        raise argparse.ArgumentTypeError("review workspaces must live outside the repository")
    return path


def _new_review_file(value: str) -> Path:
    path = _absolute(value)
    lexical = path.parent.resolve(strict=True) / path.name
    if ROOT == lexical or ROOT in lexical.parents:
        raise argparse.ArgumentTypeError(
            "human-review evidence must live outside the repository"
        )
    if lexical.exists() or lexical.is_symlink():
        raise argparse.ArgumentTypeError("new human-review file must not already exist")
    return lexical


def _existing_review_file(value: str) -> Path:
    path = _absolute(value).resolve(strict=True)
    if ROOT == path or ROOT in path.parents:
        raise argparse.ArgumentTypeError(
            "human-review evidence must live outside the repository"
        )
    if not path.is_file():
        raise argparse.ArgumentTypeError("human-review evidence must be a regular file")
    return path


def _full_commit(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", value):
        raise argparse.ArgumentTypeError("commit must be a full lowercase Git SHA")
    return value


def _canonical_target_url(value: str) -> str:
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("target URL must be a canonical HTTP(S) origin")
    return normalized


def _common_prepare(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=_new_workspace, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--protocol", type=_absolute, default=DEFAULT_PROTOCOL)
    parser.add_argument("--reviewer-a-name", required=True)
    parser.add_argument("--reviewer-b-name", required=True)
    parser.add_argument("--adjudicator-name", required=True)
    parser.add_argument("--origin", default="http://127.0.0.1:8765")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    conversation = commands.add_parser("prepare-conversation")
    _common_prepare(conversation)
    conversation.add_argument("--report", type=_absolute, required=True)
    conversation.add_argument("--nonqualifying-dry-run", action="store_true")

    retrieval = commands.add_parser("prepare-retrieval")
    _common_prepare(retrieval)
    retrieval.add_argument("--dataset", type=_absolute, required=True)
    retrieval.add_argument("--corpus", type=_absolute, required=True)
    retrieval.add_argument("--corpus-manifest", type=_absolute, required=True)

    holdout = commands.add_parser("prepare-semantic-holdout")
    _common_prepare(holdout)
    holdout.add_argument("--private-payload", type=_absolute, required=True)
    holdout.add_argument("--manifest", type=_absolute, required=True)
    holdout.add_argument("--candidate-report", type=_absolute, required=True)

    frontend = commands.add_parser("prepare-frontend-manual")
    frontend.add_argument("--workspace", type=_new_workspace, required=True)
    frontend.add_argument("--commit", type=_full_commit, required=True)
    frontend.add_argument("--target-url", type=_canonical_target_url, required=True)
    frontend.add_argument("--accessibility-reviewer-id", required=True)
    frontend.add_argument("--accessibility-reviewer-name", required=True)
    frontend.add_argument("--accessibility-credentials", required=True)
    frontend.add_argument("--safety-reviewer-id", required=True)
    frontend.add_argument("--safety-reviewer-name", required=True)
    frontend.add_argument("--safety-credentials", required=True)
    frontend.add_argument("--release-adjudicator-id", required=True)
    frontend.add_argument("--release-adjudicator-name", required=True)
    frontend.add_argument("--release-adjudicator-credentials", required=True)

    ux = commands.add_parser("prepare-ux-template")
    ux.add_argument("--output", type=_new_review_file, required=True)
    ux.add_argument("--label", choices=("before", "after"), required=True)
    ux.add_argument("--spec", type=_absolute, default=DEFAULT_SPEC)

    verify_frontend = commands.add_parser("verify-frontend-manual")
    verify_frontend.add_argument("--bundle", type=_existing_review_file, required=True)
    verify_frontend.add_argument("--commit", type=_full_commit, required=True)

    verify_ux = commands.add_parser("verify-ux-report")
    verify_ux.add_argument("--report", type=_existing_review_file, required=True)
    verify_ux.add_argument("--spec", type=_absolute, default=DEFAULT_SPEC)

    serve = commands.add_parser("serve")
    serve.add_argument("--workspace", type=_existing_workspace, required=True)
    serve.add_argument("--host", choices=("127.0.0.1", "::1", "localhost"), default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    status = commands.add_parser("session-status")
    status.add_argument("--workspace", type=_existing_workspace, required=True)

    storage_attestation = commands.add_parser("prepare-storage-attestation")
    storage_attestation.add_argument("--workspace", type=_existing_workspace, required=True)
    storage_attestation.add_argument("--output", type=_new_review_file, required=True)

    qualify = commands.add_parser("qualify-finalized")
    qualify.add_argument("--workspace", type=_existing_workspace, required=True)
    qualify.add_argument("--storage-attestation", type=_existing_review_file, required=True)
    qualify.add_argument("--output-dir", type=_new_workspace, required=True)

    verify_qualification = commands.add_parser("verify-qualification")
    verify_qualification.add_argument("--manifest", type=_existing_review_file, required=True)
    verify_qualification.add_argument("--source", type=_existing_review_file, required=True)
    verify_qualification.add_argument("--sidecar", type=_existing_review_file, required=True)
    verify_qualification.add_argument("--summary", type=_existing_review_file, required=True)
    verify_qualification.add_argument(
        "--storage-attestation", type=_existing_review_file, required=True
    )
    verify_qualification.add_argument(
        "--suite-kind", choices=("conversation", "retrieval"), required=True
    )
    verify_qualification.add_argument("--case-count", type=int, required=True)

    export = commands.add_parser("export-finalized")
    export.add_argument("--workspace", type=_existing_workspace, required=True)

    verify = commands.add_parser("verify-export")
    verify.add_argument("--workspace", type=_existing_workspace, required=True)

    analyze = commands.add_parser("analyze-finalized")
    analyze.add_argument("--workspace", type=_existing_workspace, required=True)

    verify_analysis = commands.add_parser("verify-analysis")
    verify_analysis.add_argument("--workspace", type=_existing_workspace, required=True)
    return parser


def _recipe(
    args: argparse.Namespace,
) -> tuple[Literal["semantic", "retrieval"], ReviewInputRecipe]:
    if args.command == "prepare-conversation":
        return "semantic", ReviewInputRecipe(
            suite_kind="conversation",
            conversation_report=str(args.report),
            nonqualifying_dry_run=args.nonqualifying_dry_run,
        )
    if args.command == "prepare-retrieval":
        return "retrieval", ReviewInputRecipe(
            suite_kind="retrieval",
            retrieval_dataset=str(args.dataset),
            corpus_chunks=str(args.corpus),
            corpus_manifest=str(args.corpus_manifest),
        )
    if args.command == "prepare-semantic-holdout":
        return "semantic", ReviewInputRecipe(
            suite_kind="semantic_holdout",
            private_holdout_payload=str(args.private_payload),
            holdout_manifest=str(args.manifest),
            holdout_candidate_report=str(args.candidate_report),
        )
    raise ValueError("command does not prepare a review")


def _safe_summary(value: dict[str, object]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _prepare(args: argparse.Namespace) -> int:
    review_kind, recipe = _recipe(args)
    coordinator, capability_paths = prepare_review_session(
        args.workspace,
        session_id=args.session_id,
        review_kind=review_kind,
        input_recipe=recipe,
        protocol_path=args.protocol,
        reviewer_a_name=args.reviewer_a_name,
        reviewer_b_name=args.reviewer_b_name,
        adjudicator_name=args.adjudicator_name,
        allowed_origin=args.origin,
    )
    _safe_summary(
        {
            "status": "prepared_nonqualifying_review_workspace",
            "qualification_eligible": False,
            "workspace": str(args.workspace),
            "session_id": coordinator.session.session_id,
            "suite_sha256": coordinator.suite.suite_sha256,
            "case_count": len(coordinator.suite.cases),
            "capability_files": {
                actor_id: str(path) for actor_id, path in sorted(capability_paths.items())
            },
            "next_command": (
                f"{sys.executable} {Path(__file__).resolve()} serve "
                f"--workspace {args.workspace}"
            ),
        }
    )
    return 0


def _frontend_reviewer(
    *, role: str, reviewer_id: str, reviewer_name: str, credentials: str
) -> dict[str, object]:
    normalized_id = reviewer_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{2,127}", normalized_id):
        raise ValueError(f"{role} reviewer ID is not canonical")
    normalized_name = _named_frontend_reviewer(reviewer_name, context=f"{role} reviewer name")
    normalized_credentials = credentials.strip()
    if not normalized_credentials:
        raise ValueError(f"{role} reviewer credentials must not be blank")
    return {
        "role": role,
        "reviewer_id": normalized_id,
        "reviewer_name": normalized_name,
        "credentials": normalized_credentials,
        "assigned_at": None,
        "attested_at": None,
        "attestation": "",
    }


def _prepare_frontend_manual(args: argparse.Namespace) -> int:
    protocol = _frontend_manual_review_protocol(FRONTEND_MANUAL_REVIEW_PROTOCOL)
    assignments = [
        _frontend_reviewer(
            role="accessibility_specialist",
            reviewer_id=args.accessibility_reviewer_id,
            reviewer_name=args.accessibility_reviewer_name,
            credentials=args.accessibility_credentials,
        ),
        _frontend_reviewer(
            role="wildfire_product_safety_reviewer",
            reviewer_id=args.safety_reviewer_id,
            reviewer_name=args.safety_reviewer_name,
            credentials=args.safety_credentials,
        ),
        _frontend_reviewer(
            role="release_adjudicator",
            reviewer_id=args.release_adjudicator_id,
            reviewer_name=args.release_adjudicator_name,
            credentials=args.release_adjudicator_credentials,
        ),
    ]
    reviewer_ids = [str(row["reviewer_id"]).casefold() for row in assignments]
    reviewer_names = [str(row["reviewer_name"]).casefold() for row in assignments]
    if len(set(reviewer_ids)) != 3 or len(set(reviewer_names)) != 3:
        raise ValueError("frontend manual roles require three distinct named humans")
    assignment_by_role = {str(row["role"]): row for row in assignments}

    environments = []
    for profile in protocol["test_profiles"]:
        reviewer = assignment_by_role[str(profile["required_role"])]
        environments.append(
            {
                "profile_id": profile["id"],
                "reviewer_id": reviewer["reviewer_id"],
                "os_name": profile["os_name"],
                "os_version": None,
                "browser_name": profile["browser_name"],
                "browser_version": None,
                "assistive_technology": profile["assistive_technology"],
                "assistive_technology_version": None,
                "input_methods": profile["input_methods"],
                "viewport": profile["viewport"],
                "zoom_percentages": profile["zoom_percentages"],
                "reflow_widths_css_px": profile["reflow_widths_css_px"],
                "reduced_motion": profile["reduced_motion"],
                "verified_at": None,
            }
        )

    coverage = []
    for profile in protocol["test_profiles"]:
        reviewer = assignment_by_role[str(profile["required_role"])]
        for state_id in protocol["state_roster"]:
            coverage.append(
                {
                    "profile_id": profile["id"],
                    "state_id": state_id,
                    "status": None,
                    "reviewer_id": reviewer["reviewer_id"],
                    "observed_at": None,
                    "evidence_ids": [],
                    "notes": "",
                }
            )

    criteria = []
    atomic_check_ids = []
    for criterion in protocol["criteria"]:
        reviewer = assignment_by_role[str(criterion["required_role"])]
        checks = []
        for check in criterion["atomic_checks"]:
            atomic_check_ids.append(check["id"])
            checks.append(
                {
                    "check_id": check["id"],
                    "status": None,
                    "reviewer_id": reviewer["reviewer_id"],
                    "reviewed_at": None,
                    "evidence_ids": [],
                    "notes": "",
                }
            )
        criteria.append({"criterion_id": criterion["id"], "atomic_checks": checks})

    coverage_ids = [
        f"{profile['id']}/{state_id}"
        for profile in protocol["test_profiles"]
        for state_id in protocol["state_roster"]
    ]
    commit = args.commit
    payload = {
        "schema_version": protocol["bundle_schema_version"],
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": file_sha256(FRONTEND_MANUAL_REVIEW_PROTOCOL),
        },
        "candidate": {
            "candidate_id": f"{protocol['candidate_contract']['candidate_id_prefix']}{commit}",
            "commit": commit,
            "target_url": args.target_url,
            "build_verified_at": None,
            "identity_evidence_id": "EV-001",
        },
        "review_window": {"started_at": None, "completed_at": None},
        "role_assignments": assignments,
        "test_environments": environments,
        "evidence": [],
        "coverage": coverage,
        "criteria": criteria,
        "findings": [],
        "adjudication": {
            "adjudicator_id": assignment_by_role["release_adjudicator"]["reviewer_id"],
            "decision": None,
            "decided_at": None,
            "accessibility_qualified": None,
            "product_safety_qualified": None,
            "open_finding_count": None,
            "criterion_ids": [row["id"] for row in protocol["criteria"]],
            "atomic_check_ids": atomic_check_ids,
            "test_profile_ids": [row["id"] for row in protocol["test_profiles"]],
            "state_ids": protocol["state_roster"],
            "coverage_ids": coverage_ids,
            "evidence_ids": [],
            "attestation": "",
        },
        "generated_at": None,
    }

    args.workspace.mkdir(mode=0o700)
    evidence_dir = args.workspace / "evidence"
    evidence_dir.mkdir(mode=0o700)
    bundle_path = args.workspace / "frontend_manual_review.template.yaml"
    bundle_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    bundle_path.chmod(0o600)
    instructions_path = args.workspace / "INSTRUCTIONS.md"
    instructions_path.write_text(
        "# FireLens manual frontend review packet\n\n"
        "This packet contains no review outcomes. Complete every null/blank field only from "
        "direct human observation of the bound candidate. Retain each evidence file under "
        "`evidence/`, record its SHA-256 and byte count, and do not reuse evidence across "
        "distinct observations. The release adjudicator acts only after the accessibility "
        "and wildfire product-safety reviews are complete. Validate the completed bundle "
        "with `scripts/upgrade_benchmark.py` during the after capture.\n",
        encoding="utf-8",
    )
    instructions_path.chmod(0o600)
    _safe_summary(
        {
            "status": "prepared_unscored_frontend_manual_packet",
            "qualification_eligible": False,
            "workspace": str(args.workspace),
            "bundle": str(bundle_path),
            "candidate_commit": commit,
            "profile_count": len(environments),
            "coverage_cell_count": len(coverage),
            "atomic_check_count": len(atomic_check_ids),
        }
    )
    return 0


def _prepare_ux_template(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    _write_ux_template(args.output, args.label, spec)
    args.output.chmod(0o600)
    _safe_summary(
        {
            "status": "prepared_unscored_ux_template",
            "qualification_eligible": False,
            "output": str(args.output),
            "label": args.label,
            "participant_slots": 12,
            "attempt_slots": 12 * len(spec.ux_tasks),
        }
    )
    return 0


def _verify_frontend_manual(args: argparse.Namespace) -> int:
    result = validate_frontend_manual_review(args.bundle, expected_commit=args.commit)
    _safe_summary(
        {
            "status": "verified_frontend_manual_review",
            "qualification_eligible": result["qualified"],
            "candidate_commit": args.commit,
            "accessibility_qualified": result["accessibility_qualified"],
            "product_safety_qualified": result["product_safety_qualified"],
            "open_finding_count": result["open_finding_count"],
        }
    )
    return 0


def _verify_ux_report(args: argparse.Namespace) -> int:
    try:
        raw = yaml.safe_load(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError("UX report is not readable UTF-8 YAML/JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("UX report must be an object")
    result = _ux(raw, load_spec(args.spec))
    _safe_summary(
        {
            "status": "verified_ux_report",
            "qualification_eligible": False,
            "qualification_note": "paired benchmark comparison is still required",
            "label": result["label"],
            "candidate_commit": result["commit"],
            "participant_count": result["participant_count"],
            "task_completion_rate": result["task_completion_rate"],
            "critical_error_count": result["critical_error_count"],
            "near_me_median_seconds": result["near_me_median_seconds"],
            "worst_core_cohort_completion_rate": result["worst_core_cohort_completion_rate"],
            "worst_device_class_completion_rate": result["worst_device_class_completion_rate"],
            "bootstrap": result["bootstrap"],
        }
    )
    return 0


def _serve(args: argparse.Namespace) -> int:
    if not 1024 <= args.port <= 65535:
        raise ValueError("review server port must be between 1024 and 65535")
    coordinator, launch, tokens = resume_prepared_review(args.workspace)
    origin = urlsplit(launch.allowed_origin)
    if origin.port != args.port or origin.hostname != args.host:
        raise ValueError("serve host and port must exactly match the frozen review origin")
    app = create_review_workspace_app(
        coordinator,
        actor_tokens=tokens,
        allowed_origins=(launch.allowed_origin,),
        allowed_hosts=(args.host,),
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
        date_header=False,
    )
    return 0


def _session_status(args: argparse.Namespace) -> int:
    coordinator, launch, _tokens = resume_prepared_review(args.workspace)
    actors = []
    session_state = None
    for actor in launch.session.actors:
        progress = coordinator.progress(actor.actor_id)
        session_state = progress.session_state
        actors.append(
            {
                "actor_id": actor.actor_id,
                "role": actor.role,
                "actor_state": progress.actor_state,
                "completed_case_count": progress.completed_case_count,
                "case_count": progress.case_count,
                "next_case_position": progress.next_case_position,
            }
        )
    _safe_summary(
        {
            "status": "verified_nonqualifying_review_session_status",
            "qualification_eligible": False,
            "input_integrity_rechecked": True,
            "session_id": launch.session.session_id,
            "suite_kind": launch.input_recipe.suite_kind,
            "suite_sha256": coordinator.suite.suite_sha256,
            "session_state": session_state,
            "allowed_origin": launch.allowed_origin,
            "actors": actors,
        }
    )
    return 0


def _prepare_storage_attestation(args: argparse.Namespace) -> int:
    write_storage_attestation_template(args.workspace, args.output)
    _safe_summary(
        {
            "status": "prepared_unapproved_storage_attestation",
            "qualification_eligible": False,
            "workspace": str(args.workspace),
            "output": str(args.output),
            "next_action": (
                "An independent named human must inspect storage and external-anchor controls, "
                "then complete every false/null field without changing the bound hashes."
            ),
        }
    )
    return 0


def _qualify_finalized(args: argparse.Namespace) -> int:
    manifest = build_review_qualification(
        args.workspace,
        args.storage_attestation,
        args.output_dir,
    )
    _safe_summary(
        {
            "status": "qualified_blind_human_review",
            "qualification_eligible": True,
            "session_id": manifest.session_id,
            "suite_kind": manifest.suite_kind,
            "case_count": manifest.case_count,
            "initial_disagreement_case_count": (manifest.initial_disagreement_case_count),
            "output_directory": str(args.output_dir),
        }
    )
    return 0


def _verify_qualification(args: argparse.Namespace) -> int:
    manifest = verify_review_qualification_package(
        args.manifest,
        source_path=args.source,
        sidecar_path=args.sidecar,
        summary_path=args.summary,
        attestation_path=args.storage_attestation,
        expected_suite_kind=args.suite_kind,
        expected_case_count=args.case_count,
    )
    _safe_summary(
        {
            "status": "verified_blind_human_review_qualification",
            "qualification_eligible": True,
            "session_id": manifest.session_id,
            "suite_kind": manifest.suite_kind,
            "case_count": manifest.case_count,
            "storage_reviewer": manifest.independent_storage_reviewer_name,
        }
    )
    return 0


def _export(args: argparse.Namespace) -> int:
    coordinator, _launch, _tokens = resume_prepared_review(args.workspace)
    receipt = write_finalized_evidence_export(coordinator)
    _safe_summary(
        {
            "status": "exported_nonqualifying_review_evidence",
            "qualification_eligible": False,
            "session_id": receipt.session_id,
            "evidence_sha256": receipt.evidence_sha256,
            "evidence_byte_count": receipt.evidence_byte_count,
        }
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    evidence, receipt = verify_finalized_evidence_export(args.workspace)
    _safe_summary(
        {
            "status": "verified_nonqualifying_review_evidence",
            "qualification_eligible": False,
            "session_id": evidence.session.session_id,
            "suite_kind": evidence.suite_kind,
            "case_count": len(evidence.session.case_ids),
            "evidence_sha256": receipt.evidence_sha256,
        }
    )
    return 0


def _analyze(args: argparse.Namespace) -> int:
    receipt = write_review_analysis(args.workspace)
    analysis, _verified = verify_review_analysis(args.workspace)
    _safe_summary(
        {
            "status": "analyzed_nonqualifying_review_evidence",
            "qualification_eligible": False,
            "session_id": analysis.session_id,
            "suite_kind": analysis.suite_kind,
            "case_count": analysis.case_count,
            "initial_disagreement_case_count": analysis.initial_disagreement_case_count,
            "adjudicated_finding_case_count": analysis.adjudicated_finding_case_count,
            "analysis_sha256": receipt.analysis_sha256,
        }
    )
    return 0


def _verify_analysis(args: argparse.Namespace) -> int:
    analysis, receipt = verify_review_analysis(args.workspace)
    _safe_summary(
        {
            "status": "verified_nonqualifying_review_analysis",
            "qualification_eligible": False,
            "session_id": analysis.session_id,
            "suite_kind": analysis.suite_kind,
            "case_count": analysis.case_count,
            "analysis_sha256": receipt.analysis_sha256,
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _command_handler(args.command)(args)
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        print(f"human review workspace refused: {exc}", file=sys.stderr)
        return 2


def _command_handler(command: str) -> Callable[[argparse.Namespace], int]:
    if command in {
        "prepare-conversation",
        "prepare-retrieval",
        "prepare-semantic-holdout",
    }:
        return _prepare
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "prepare-frontend-manual": _prepare_frontend_manual,
        "prepare-ux-template": _prepare_ux_template,
        "verify-frontend-manual": _verify_frontend_manual,
        "verify-ux-report": _verify_ux_report,
        "serve": _serve,
        "session-status": _session_status,
        "prepare-storage-attestation": _prepare_storage_attestation,
        "qualify-finalized": _qualify_finalized,
        "verify-qualification": _verify_qualification,
        "export-finalized": _export,
        "verify-export": _verify,
        "analyze-finalized": _analyze,
        "verify-analysis": _verify_analysis,
    }
    try:
        return handlers[command]
    except KeyError as error:
        raise AssertionError("unreachable command") from error


if __name__ == "__main__":
    raise SystemExit(main())
