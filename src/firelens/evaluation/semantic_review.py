"""Blind semantic-review randomization and presentation-history validation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from firelens.evaluation.common import (
    require_digest as _require_digest,
)
from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    require_timestamp as _require_timestamp,
)
from firelens.evaluation.common import (
    sha256_json as _sha256_json,
)
from firelens.evaluation.common import (
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)


def _semantic_randomization_context_sha256(
    *,
    candidate_report_sha256: str,
    candidate_identity_sha256: str,
    dataset_manifest_sha256: str,
    development_registry_sha256: str,
) -> str:
    return _sha256_json(
        {
            "algorithm": "sha256_identity_bound_sort.v1",
            "candidate_report_sha256": candidate_report_sha256,
            "candidate_identity_sha256": candidate_identity_sha256,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "development_registry_sha256": development_registry_sha256,
        }
    )


def _semantic_actor_case_order(
    case_ids: list[str],
    *,
    randomization_context_sha256: str,
    actor_role: str,
    actor_id: str,
) -> list[str]:
    def key(case_id: str) -> tuple[str, str]:
        payload = (
            f"{randomization_context_sha256}\0{actor_role}\0{actor_id}\0{case_id}"
        ).encode()
        return hashlib.sha256(payload).hexdigest(), case_id

    return sorted(case_ids, key=key)


def _semantic_claim_roster_sha256(candidate_case: dict[str, Any]) -> str:
    return _sha256_json(
        [
            {"claim_id": claim["claim_id"], "text_sha256": claim["text_sha256"]}
            for claim in candidate_case["claims"]
        ]
    )


def _semantic_displayed_payload_sha256(event: dict[str, Any]) -> str:
    return _sha256_json(
        {
            "event_type": event["event_type"],
            "actor_role": event["actor_role"],
            "actor_id": event["actor_id"],
            "case_id": event["case_id"],
            "case_position": event["case_position"],
            "blinded_candidate_label": event["blinded_candidate_label"],
            "candidate_position": event["candidate_position"],
            "input_sha256": event["input_sha256"],
            "response_sha256": event["response_sha256"],
            "claim_roster_sha256": event["claim_roster_sha256"],
            "review_material_sha256": event["review_material_sha256"],
        }
    )


def _semantic_presentation_event_sha256(event: dict[str, Any]) -> str:
    return _sha256_json({key: value for key, value in event.items() if key != "event_sha256"})


def _semantic_presentation_history(
    presentation: dict[str, Any],
    presentation_log: dict[str, Any],
    *,
    report: dict[str, Any],
    expected_case_ids: list[str],
    reviewers: dict[str, str],
    adjudicator_id: str,
    candidate_report_sha256: str,
    dataset_manifest_sha256: str,
    development_registry_sha256: str,
    report_generated_at: datetime,
    bundle_generated_at: datetime,
) -> dict[str, Any]:
    _require_exact_keys(
        presentation,
        {
            "candidate_identity_blinded",
            "reviewers_blinded_to_each_other",
            "randomized",
            "randomization_algorithm",
            "randomization_context_sha256",
            "blinded_candidate_label",
            "actor_orders",
            "presentation_log_sha256",
        },
        context="semantic holdout presentation evidence",
    )
    for key in (
        "candidate_identity_blinded",
        "reviewers_blinded_to_each_other",
        "randomized",
    ):
        if not _strict_bool(presentation, key, "semantic holdout presentation"):
            raise ValueError(f"semantic holdout presentation requires {key}")
    if presentation.get("randomization_algorithm") != "sha256_identity_bound_sort.v1":
        raise ValueError("semantic holdout presentation randomization algorithm is invalid")
    randomization_context = _semantic_randomization_context_sha256(
        candidate_report_sha256=candidate_report_sha256,
        candidate_identity_sha256=report["candidate_identity_sha256"],
        dataset_manifest_sha256=dataset_manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    _require_digest(
        presentation.get("randomization_context_sha256"),
        context="semantic holdout randomization-context digest",
    )
    if presentation["randomization_context_sha256"] != randomization_context:
        raise ValueError("semantic holdout randomization context is inconsistent")
    blinded_label = _require_nonempty_string(
        presentation.get("blinded_candidate_label"),
        context="semantic holdout blinded candidate label",
    )
    if blinded_label.casefold() == str(report["candidate_id"]).casefold():
        raise ValueError("semantic holdout presentation exposes the candidate identity")

    expected_actors = [("reviewer", reviewer_id) for reviewer_id in reviewers] + [
        ("adjudicator", adjudicator_id)
    ]
    actor_orders = presentation.get("actor_orders")
    if not isinstance(actor_orders, list) or len(actor_orders) != len(expected_actors):
        raise ValueError("semantic holdout presentation requires every exact review actor")
    expected_orders: dict[tuple[str, str], list[str]] = {}
    for index, ((expected_role, expected_actor), actor_order) in enumerate(
        zip(expected_actors, actor_orders, strict=True)
    ):
        if not isinstance(actor_order, dict):
            raise ValueError(f"semantic holdout actor order {index} must be an object")
        _require_exact_keys(
            actor_order,
            {"actor_role", "actor_id", "case_ids", "case_order_sha256"},
            context=f"semantic holdout actor order {index}",
        )
        if (actor_order.get("actor_role"), actor_order.get("actor_id")) != (
            expected_role,
            expected_actor,
        ):
            raise ValueError("semantic holdout presentation actor roster is not canonical")
        expected_order = _semantic_actor_case_order(
            expected_case_ids,
            randomization_context_sha256=randomization_context,
            actor_role=expected_role,
            actor_id=expected_actor,
        )
        if actor_order.get("case_ids") != expected_order:
            raise ValueError("semantic holdout actor presentation order is not reproducible")
        _require_digest(
            actor_order.get("case_order_sha256"),
            context=f"semantic holdout actor order {index} digest",
        )
        if actor_order["case_order_sha256"] != _sha256_json(expected_order):
            raise ValueError("semantic holdout actor presentation-order digest is inconsistent")
        expected_orders[(expected_role, expected_actor)] = expected_order

    _require_exact_keys(
        presentation_log,
        {
            "log_version",
            "log_id",
            "append_only",
            "created_at",
            "finalized_at",
            "candidate_identity_sha256",
            "candidate_report_sha256",
            "dataset_manifest_sha256",
            "development_registry_sha256",
            "randomization_context_sha256",
            "event_count",
            "events",
            "head_event_sha256",
        },
        context="semantic holdout presentation log",
    )
    if presentation_log.get("log_version") != "firelens_semantic_holdout_presentation_log.v1":
        raise ValueError("semantic holdout presentation log uses an unsupported version")
    _require_nonempty_string(
        presentation_log.get("log_id"), context="semantic holdout presentation log ID"
    )
    if not _strict_bool(presentation_log, "append_only", "semantic presentation log"):
        raise ValueError("semantic holdout presentation log must be append-only")
    created_at = _require_timestamp(
        presentation_log.get("created_at"), context="semantic presentation log created_at"
    )
    finalized_at = _require_timestamp(
        presentation_log.get("finalized_at"), context="semantic presentation log finalized_at"
    )
    if created_at <= report_generated_at or finalized_at < created_at:
        raise ValueError("semantic holdout presentation-log timestamps are out of order")
    if finalized_at > bundle_generated_at:
        raise ValueError("semantic holdout presentation log postdates its review bundle")
    expected_log_bindings = {
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "randomization_context_sha256": randomization_context,
    }
    for key, expected in expected_log_bindings.items():
        _require_digest(presentation_log.get(key), context=f"semantic presentation log {key}")
        if presentation_log[key] != expected:
            raise ValueError(f"semantic holdout presentation log has the wrong {key}")

    events = presentation_log.get("events")
    event_count = _strict_int(
        presentation_log, "event_count", "semantic presentation log", minimum=0
    )
    expected_event_count = len(expected_case_ids) * len(expected_actors)
    if not isinstance(events, list) or event_count != expected_event_count:
        raise ValueError("semantic holdout presentation log has an incomplete event roster")
    if len(events) != event_count:
        raise ValueError("semantic holdout presentation event_count differs from events")
    event_keys = {
        "sequence",
        "event_id",
        "event_type",
        "actor_role",
        "actor_id",
        "case_id",
        "case_position",
        "blinded_candidate_label",
        "candidate_position",
        "candidate_identity_sha256",
        "candidate_report_sha256",
        "input_sha256",
        "response_sha256",
        "claim_roster_sha256",
        "review_material_sha256",
        "displayed_payload_sha256",
        "presented_at",
        "previous_event_sha256",
        "event_sha256",
    }
    report_cases = {case["case_id"]: case for case in report["cases"]}
    events_by_exposure: dict[tuple[str, str, str], dict[str, Any]] = {}
    prior_digest: str | None = None
    prior_timestamp: datetime | None = None
    event_ids: set[str] = set()
    observed_actor_orders: dict[tuple[str, str], list[str]] = {
        actor: [] for actor in expected_actors
    }
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"semantic presentation event {index} must be an object")
        _require_exact_keys(event, event_keys, context=f"semantic presentation event {index}")
        if (
            _strict_int(event, "sequence", f"semantic presentation event {index}", minimum=1)
            != index
        ):
            raise ValueError("semantic holdout presentation event sequence is not contiguous")
        event_id = _require_nonempty_string(
            event.get("event_id"), context=f"semantic presentation event {index} ID"
        )
        if event_id in event_ids:
            raise ValueError("semantic holdout presentation event IDs must be unique")
        event_ids.add(event_id)
        actor_key = (event.get("actor_role"), event.get("actor_id"))
        if actor_key not in expected_orders:
            raise ValueError("semantic holdout presentation event uses an unknown actor")
        expected_event_type = (
            "independent_review_presentation"
            if actor_key[0] == "reviewer"
            else "adjudication_presentation"
        )
        if event.get("event_type") != expected_event_type:
            raise ValueError("semantic holdout presentation event has the wrong event_type")
        case_id = event.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("semantic holdout presentation event case_id is invalid")
        candidate_case = report_cases.get(case_id)
        if candidate_case is None:
            raise ValueError("semantic holdout presentation event uses an unknown case")
        observed_actor_orders[actor_key].append(case_id)
        expected_position = len(observed_actor_orders[actor_key])
        if (
            _strict_int(
                event, "case_position", f"semantic presentation event {index}", minimum=1
            )
            != expected_position
        ):
            raise ValueError("semantic holdout presentation case positions are not contiguous")
        if event.get("blinded_candidate_label") != blinded_label:
            raise ValueError("semantic holdout presentation event exposes the wrong candidate")
        if (
            _strict_int(
                event, "candidate_position", f"semantic presentation event {index}", minimum=1
            )
            != 1
        ):
            raise ValueError(
                "semantic holdout final qualification presents exactly one candidate"
            )
        for key, expected in {
            "candidate_identity_sha256": report["candidate_identity_sha256"],
            "candidate_report_sha256": candidate_report_sha256,
            "input_sha256": candidate_case["input_sha256"],
            "response_sha256": candidate_case["response_sha256"],
            "claim_roster_sha256": _semantic_claim_roster_sha256(candidate_case),
        }.items():
            _require_digest(
                event.get(key), context=f"semantic presentation event {index} {key}"
            )
            if event[key] != expected:
                raise ValueError(f"semantic holdout presentation event has the wrong {key}")
        if actor_key[0] == "reviewer":
            if event.get("review_material_sha256") is not None:
                raise ValueError("independent reviewer presentation exposes review material")
        else:
            _require_digest(
                event.get("review_material_sha256"),
                context=f"semantic presentation event {index} review material",
            )
        _require_digest(
            event.get("displayed_payload_sha256"),
            context=f"semantic presentation event {index} displayed payload",
        )
        if event["displayed_payload_sha256"] != _semantic_displayed_payload_sha256(event):
            raise ValueError("semantic holdout displayed-payload digest is inconsistent")
        presented_at = _require_timestamp(
            event.get("presented_at"),
            context=f"semantic presentation event {index} timestamp",
        )
        if presented_at < created_at or presented_at > finalized_at:
            raise ValueError("semantic holdout presentation event is outside the log window")
        if prior_timestamp is not None and presented_at <= prior_timestamp:
            raise ValueError(
                "semantic holdout presentation timestamps are not strictly ordered"
            )
        prior_timestamp = presented_at
        if event.get("previous_event_sha256") != prior_digest:
            raise ValueError("semantic holdout presentation hash chain is broken")
        _require_digest(
            event.get("event_sha256"),
            context=f"semantic presentation event {index} digest",
        )
        recomputed_event_digest = _semantic_presentation_event_sha256(event)
        if event["event_sha256"] != recomputed_event_digest:
            raise ValueError("semantic holdout presentation event digest is inconsistent")
        prior_digest = recomputed_event_digest
        exposure_key = (actor_key[0], actor_key[1], case_id)
        if exposure_key in events_by_exposure:
            raise ValueError("semantic holdout presentation repeats an actor/case exposure")
        events_by_exposure[exposure_key] = {
            "event": event,
            "presented_at": presented_at,
        }
    for actor_key, expected_order in expected_orders.items():
        if observed_actor_orders[actor_key] != expected_order:
            raise ValueError("semantic holdout presentation log differs from actor order")
    _require_digest(
        presentation_log.get("head_event_sha256"),
        context="semantic holdout presentation-log head digest",
    )
    if presentation_log["head_event_sha256"] != prior_digest:
        raise ValueError("semantic holdout presentation-log head is inconsistent")
    presentation_log_digest = _sha256_json(presentation_log)
    _require_digest(
        presentation.get("presentation_log_sha256"),
        context="semantic holdout presentation-log digest",
    )
    if presentation["presentation_log_sha256"] != presentation_log_digest:
        raise ValueError("semantic holdout presentation-log digest is inconsistent")
    return {
        "events_by_exposure": events_by_exposure,
        "actor_orders": expected_orders,
        "event_count": event_count,
        "head_event_sha256": prior_digest,
        "presentation_log_sha256": presentation_log_digest,
        "randomization_context_sha256": randomization_context,
    }
