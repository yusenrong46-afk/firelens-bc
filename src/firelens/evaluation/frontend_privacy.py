"""Frontend privacy and functional-journey evidence validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)
from firelens.evaluation.frontend_browser import _frontend_runtime
from firelens.evaluation.frontend_protocol import (
    _require_object_list,
    _require_string_list,
)


def _privacy_token_matches(value: Any, tokens: list[str]) -> list[str]:
    text = str(value) if value is not None else ""
    return [token for token in tokens if token in text]


def _privacy_token_findings(value: Any, path: tuple[str, ...] = ()) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_privacy_token_findings(item, (*path, str(index))))
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if key.endswith("_token_matches") and isinstance(child, list):
                findings.extend(
                    {"path": ".".join(child_path), "token": token} for token in child
                )
            else:
                findings.extend(_privacy_token_findings(child, child_path))
    return findings


def _validate_privacy_browser_surfaces(
    surfaces: Any, *, tokens: list[str], context: str
) -> dict[str, Any]:
    if not isinstance(surfaces, dict):
        raise ValueError(f"{context} browser surfaces must be an object")
    _require_exact_keys(
        surfaces,
        {
            "current_url",
            "current_url_token_matches",
            "history",
            "local_storage",
            "session_storage",
            "cookies",
            "indexed_db",
            "cache_storage",
            "service_workers",
        },
        context=f"{context} browser surfaces",
    )

    def token_list(value: Any, *, item_context: str) -> list[str]:
        observed = _require_string_list(value, context=item_context, unique=True)
        if any(token not in tokens for token in observed):
            raise ValueError(f"{item_context} contains an unknown probe token")
        return observed

    current_url = _require_nonempty_string(
        surfaces.get("current_url"), context=f"{context} current URL"
    )
    current_matches = token_list(
        surfaces.get("current_url_token_matches"),
        item_context=f"{context} current URL token matches",
    )
    if current_matches != _privacy_token_matches(current_url, tokens):
        raise ValueError(f"{context} current URL token matches are inconsistent")

    history = surfaces.get("history")
    if not isinstance(history, dict):
        raise ValueError(f"{context} history evidence must be an object")
    _require_exact_keys(
        history,
        {"length", "state_type", "state_serialized_length", "state_token_matches"},
        context=f"{context} history evidence",
    )
    _strict_int(history, "length", f"{context} history evidence", minimum=0)
    _require_nonempty_string(history.get("state_type"), context=f"{context} history state type")
    _strict_int(
        history,
        "state_serialized_length",
        f"{context} history evidence",
        minimum=0,
    )
    token_list(
        history.get("state_token_matches"),
        item_context=f"{context} history token matches",
    )

    def validate_storage_entries(value: Any, *, item_context: str) -> list[dict[str, Any]]:
        rows = _require_object_list(value, context=item_context)
        for index, row in enumerate(rows):
            row_context = f"{item_context} {index}"
            _require_exact_keys(
                row,
                {"key", "key_token_matches", "value_length", "value_token_matches"},
                context=row_context,
            )
            key = _require_nonempty_string(row.get("key"), context=f"{row_context} key")
            key_matches = token_list(
                row.get("key_token_matches"),
                item_context=f"{row_context} key token matches",
            )
            if key_matches != _privacy_token_matches(key, tokens):
                raise ValueError(f"{row_context} key token matches are inconsistent")
            _strict_int(row, "value_length", row_context, minimum=0)
            token_list(
                row.get("value_token_matches"),
                item_context=f"{row_context} value token matches",
            )
        return rows

    validate_storage_entries(
        surfaces.get("local_storage"), item_context=f"{context} local storage"
    )
    validate_storage_entries(
        surfaces.get("session_storage"), item_context=f"{context} session storage"
    )

    cookies = _require_object_list(surfaces.get("cookies"), context=f"{context} cookies")
    for index, cookie in enumerate(cookies):
        cookie_context = f"{context} cookie {index}"
        _require_exact_keys(
            cookie,
            {"name", "name_token_matches", "value_length", "value_token_matches"},
            context=cookie_context,
        )
        name = _require_nonempty_string(cookie.get("name"), context=f"{cookie_context} name")
        name_matches = token_list(
            cookie.get("name_token_matches"),
            item_context=f"{cookie_context} name token matches",
        )
        if name_matches != _privacy_token_matches(name, tokens):
            raise ValueError(f"{cookie_context} name token matches are inconsistent")
        _strict_int(cookie, "value_length", cookie_context, minimum=0)
        token_list(
            cookie.get("value_token_matches"),
            item_context=f"{cookie_context} value token matches",
        )

    indexed_db = surfaces.get("indexed_db")
    if not isinstance(indexed_db, dict):
        raise ValueError(f"{context} IndexedDB evidence must be an object")
    _require_exact_keys(
        indexed_db, {"supported", "databases"}, context=f"{context} IndexedDB evidence"
    )
    _strict_bool(indexed_db, "supported", f"{context} IndexedDB evidence")
    databases = _require_object_list(
        indexed_db.get("databases"), context=f"{context} IndexedDB databases"
    )
    for database_index, database in enumerate(databases):
        database_context = f"{context} IndexedDB database {database_index}"
        _require_exact_keys(
            database,
            {"name", "version", "name_token_matches", "object_stores"},
            context=database_context,
        )
        name = _require_nonempty_string(
            database.get("name"), context=f"{database_context} name"
        )
        if token_list(
            database.get("name_token_matches"),
            item_context=f"{database_context} name token matches",
        ) != _privacy_token_matches(name, tokens):
            raise ValueError(f"{database_context} name token matches are inconsistent")
        version = database.get("version")
        if version is not None and (
            isinstance(version, bool) or not isinstance(version, int) or version < 0
        ):
            raise ValueError(f"{database_context} version is invalid")
        stores = _require_object_list(
            database.get("object_stores"), context=f"{database_context} object stores"
        )
        for store_index, store in enumerate(stores):
            store_context = f"{database_context} object store {store_index}"
            _require_exact_keys(
                store,
                {
                    "name",
                    "name_token_matches",
                    "record_count",
                    "serialized_length",
                    "value_token_matches",
                },
                context=store_context,
            )
            store_name = _require_nonempty_string(
                store.get("name"), context=f"{store_context} name"
            )
            if token_list(
                store.get("name_token_matches"),
                item_context=f"{store_context} name token matches",
            ) != _privacy_token_matches(store_name, tokens):
                raise ValueError(f"{store_context} name token matches are inconsistent")
            _strict_int(store, "record_count", store_context, minimum=0)
            _strict_int(store, "serialized_length", store_context, minimum=0)
            token_list(
                store.get("value_token_matches"),
                item_context=f"{store_context} value token matches",
            )

    cache_storage = surfaces.get("cache_storage")
    if not isinstance(cache_storage, dict):
        raise ValueError(f"{context} cache evidence must be an object")
    _require_exact_keys(
        cache_storage, {"supported", "caches"}, context=f"{context} cache evidence"
    )
    _strict_bool(cache_storage, "supported", f"{context} cache evidence")
    caches = _require_object_list(cache_storage.get("caches"), context=f"{context} caches")
    for cache_index, cache in enumerate(caches):
        cache_context = f"{context} cache {cache_index}"
        _require_exact_keys(
            cache, {"name", "name_token_matches", "entries"}, context=cache_context
        )
        cache_name = _require_nonempty_string(
            cache.get("name"), context=f"{cache_context} name"
        )
        if token_list(
            cache.get("name_token_matches"),
            item_context=f"{cache_context} name token matches",
        ) != _privacy_token_matches(cache_name, tokens):
            raise ValueError(f"{cache_context} name token matches are inconsistent")
        entries = _require_object_list(cache.get("entries"), context=f"{cache_context} entries")
        for entry_index, entry in enumerate(entries):
            entry_context = f"{cache_context} entry {entry_index}"
            _require_exact_keys(
                entry,
                {
                    "request_url",
                    "request_url_token_matches",
                    "response_body_length",
                    "response_body_token_matches",
                },
                context=entry_context,
            )
            request_url = _require_nonempty_string(
                entry.get("request_url"), context=f"{entry_context} request URL"
            )
            if token_list(
                entry.get("request_url_token_matches"),
                item_context=f"{entry_context} request URL token matches",
            ) != _privacy_token_matches(request_url, tokens):
                raise ValueError(f"{entry_context} request URL token matches are inconsistent")
            _strict_int(entry, "response_body_length", entry_context, minimum=0)
            token_list(
                entry.get("response_body_token_matches"),
                item_context=f"{entry_context} response token matches",
            )

    service_workers = surfaces.get("service_workers")
    if not isinstance(service_workers, dict):
        raise ValueError(f"{context} service-worker evidence must be an object")
    _require_exact_keys(
        service_workers,
        {"supported", "registrations"},
        context=f"{context} service-worker evidence",
    )
    _strict_bool(service_workers, "supported", f"{context} service-worker evidence")
    registrations = _require_object_list(
        service_workers.get("registrations"),
        context=f"{context} service-worker registrations",
    )
    for index, registration in enumerate(registrations):
        registration_context = f"{context} service-worker registration {index}"
        _require_exact_keys(
            registration,
            {
                "scope",
                "scope_token_matches",
                "script_urls",
                "script_url_token_matches",
            },
            context=registration_context,
        )
        scope = _require_nonempty_string(
            registration.get("scope"), context=f"{registration_context} scope"
        )
        if token_list(
            registration.get("scope_token_matches"),
            item_context=f"{registration_context} scope token matches",
        ) != _privacy_token_matches(scope, tokens):
            raise ValueError(f"{registration_context} scope matches are inconsistent")
        script_urls = _require_string_list(
            registration.get("script_urls"),
            context=f"{registration_context} script URLs",
            unique=True,
        )
        joined_urls = "\n".join(script_urls)
        if token_list(
            registration.get("script_url_token_matches"),
            item_context=f"{registration_context} script URL token matches",
        ) != _privacy_token_matches(joined_urls, tokens):
            raise ValueError(
                f"{registration_context} script URL token matches are inconsistent"
            )
    return surfaces


def _frontend_privacy_evidence(
    evidence: Any, *, protocol: dict[str, Any], context: str
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValueError(f"{context} evidence must be an object")
    _require_exact_keys(
        evidence,
        {
            "fixture_data_only",
            "persistence_probe_tokens",
            "geolocation_calls",
            "api_request_roster",
            "network_request_events",
            "network_request_derived",
            "browser_surfaces",
            "derived",
        },
        context=f"{context} evidence",
    )
    if evidence.get("fixture_data_only") is not True:
        raise ValueError(f"{context} must use only the frozen privacy fixture")
    config = protocol["privacy_evidence"]
    tokens = evidence.get("persistence_probe_tokens")
    if tokens != config["persistence_probe_tokens"]:
        raise ValueError(f"{context} probe-token roster differs from the protocol")
    geolocation = evidence.get("geolocation_calls")
    if not isinstance(geolocation, dict):
        raise ValueError(f"{context} geolocation calls must be an object")
    _require_exact_keys(
        geolocation,
        {"before_opt_in", "after_opt_in"},
        context=f"{context} geolocation calls",
    )
    before_calls = _strict_int(
        geolocation, "before_opt_in", f"{context} geolocation calls", minimum=0
    )
    after_calls = _strict_int(
        geolocation, "after_opt_in", f"{context} geolocation calls", minimum=0
    )

    api_roster = _require_object_list(
        evidence.get("api_request_roster"), context=f"{context} API request roster"
    )
    api_issues: list[dict[str, Any]] = []
    expected_url = config["request_url"]
    expected_origin = f"{urlsplit(expected_url).scheme}://{urlsplit(expected_url).netloc}"
    for index, request in enumerate(api_roster):
        request_context = f"{context} API request {index}"
        _require_exact_keys(
            request,
            {
                "sequence_index",
                "method",
                "url",
                "origin",
                "resource_type",
                "body",
                "body_sha256",
                "response_status",
            },
            context=request_context,
        )
        body = request.get("body")
        if not isinstance(body, dict):
            raise ValueError(f"{request_context} body must be an object")
        body_digest = hashlib.sha256(
            json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        body_keys = sorted(body)
        unexpected_keys = [key for key in body_keys if key not in config["allowed_body_keys"]]
        expected_question = (
            config["expected_questions"][index]
            if index < len(config["expected_questions"])
            else None
        )
        if (
            request.get("sequence_index") != index
            or request.get("method") != "POST"
            or request.get("url") != expected_url
            or request.get("origin") != expected_origin
            or request.get("resource_type") != "fetch"
            or request.get("response_status") != 200
            or request.get("body_sha256") != body_digest
            or body.get("question") != expected_question
            or unexpected_keys
        ):
            api_issues.append({"sequence_index": index, "reason": "request_contract_mismatch"})
    if len(api_roster) != len(config["expected_questions"]):
        api_issues.append(
            {
                "sequence_index": None,
                "reason": "request_count_mismatch",
                "expected": len(config["expected_questions"]),
                "observed": len(api_roster),
            }
        )
    first_body = api_roster[0].get("body", {}) if api_roster else {}
    second_body = api_roster[1].get("body", {}) if len(api_roster) > 1 else {}
    first_history = first_body.get("history")
    if "location" in first_body or not (
        isinstance(first_history, list) and len(first_history) == 0
    ):
        api_issues.append({"sequence_index": 0, "reason": "first_request_location_or_history"})
    location_config = config["fixture_location"]
    second_location = second_body.get("location")
    second_history = second_body.get("history")
    if not isinstance(second_location, dict) or (
        second_location.get("latitude") != location_config["rounded_latitude"]
        or second_location.get("longitude") != location_config["rounded_longitude"]
        or second_location.get("radius_km") != location_config["radius_km"]
        or not (isinstance(second_history, list) and len(second_history) == 2)
    ):
        api_issues.append({"sequence_index": 1, "reason": "live_request_boundary_mismatch"})

    body_token_findings: list[dict[str, Any]] = []
    for index, request in enumerate(api_roster):
        body_without_location = dict(request["body"])
        body_without_location.pop("location", None)
        serialized = json.dumps(
            body_without_location,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for token in tokens:
            if token in serialized:
                body_token_findings.append({"sequence_index": index, "token": token})

    network_events = evidence.get("network_request_events")
    network_derived = evidence.get("network_request_derived")
    _frontend_runtime(
        {
            "console_errors": [],
            "expected_console_errors": [],
            "unexpected_console_errors": [],
            "expected_http_failures": [],
            "page_errors": [],
            "request_events": network_events,
            "request_derived": network_derived,
        },
        context=f"{context} network",
        state={"id": "grounded"},
        base_url="http://127.0.0.1:4175",
        thresholds=protocol["surface_thresholds"],
    )
    if not isinstance(network_derived, dict):
        raise ValueError(f"{context} network derived evidence must be an object")
    surfaces = _validate_privacy_browser_surfaces(
        evidence.get("browser_surfaces"), tokens=tokens, context=context
    )
    browser_token_findings = _privacy_token_findings(surfaces)
    url_history_clean = (
        not surfaces["current_url_token_matches"]
        and not surfaces["history"]["state_token_matches"]
    )
    browser_storage_clean = (
        not surfaces["local_storage"]
        and not surfaces["session_storage"]
        and not surfaces["cookies"]
        and not surfaces["indexed_db"]["databases"]
        and not surfaces["cache_storage"]["caches"]
        and not surfaces["service_workers"]["registrations"]
        and not browser_token_findings
    )
    unexpected_network_entries = [
        {"kind": "unexpected_origin", "origin": origin}
        for origin in network_derived["unexpected_request_origins"]
    ] + [
        {"kind": "unallowlisted_failed_request", "request": request}
        for request in network_derived["unallowlisted_failed_requests"]
    ]
    coordinates_rounded = (
        isinstance(second_location, dict)
        and second_location.get("latitude") == location_config["rounded_latitude"]
        and second_location.get("longitude") == location_config["rounded_longitude"]
    )
    location_only_live = (
        "location" not in first_body
        and isinstance(second_location, dict)
        and second_location.get("radius_km") == location_config["radius_km"]
        and second_body.get("question") == config["expected_questions"][1]
    )
    recomputed = {
        "geolocation_not_called_before_opt_in": before_calls == 0,
        "geolocation_called_once_after_opt_in": after_calls == 1,
        "coordinates_rounded_to_two_decimals": coordinates_rounded,
        "location_sent_only_with_live_request": location_only_live,
        "location_not_persisted_in_browser_storage": not browser_token_findings,
        "no_cookie_written": not surfaces["cookies"],
        "canonical_request_roster_valid": not api_issues,
        "api_request_issues": api_issues,
        "network_request_derivation_matches": True,
        "unexpected_network_entries": unexpected_network_entries,
        "body_token_leak_findings": body_token_findings,
        "browser_token_leak_findings": browser_token_findings,
        "no_unexpected_request_or_body_leakage": (
            not api_issues and not unexpected_network_entries and not body_token_findings
        ),
        "url_history_clean": url_history_clean,
        "both_coordinate_tokens_absent_outside_allowed_request": (
            not body_token_findings and not browser_token_findings
        ),
        "browser_storage_surfaces_clean": browser_storage_clean,
    }
    if evidence.get("derived") != recomputed:
        raise ValueError(f"{context} derived privacy evidence differs from raw observations")
    return recomputed


def _frontend_functional_journeys(journeys: Any, *, protocol: dict[str, Any]) -> dict[str, Any]:
    rows = _require_object_list(journeys, context="frontend functional journeys")
    expected = protocol["functional_journeys"]
    if len(rows) != len(expected):
        raise ValueError("frontend functional journey roster is incomplete")
    normalized: dict[str, bool] = {}
    for row, definition in zip(rows, expected, strict=True):
        context = f"frontend journey {definition['id']}"
        expected_keys = {"id", "checks", "errors", "qualified"}
        if definition["id"] == "location_privacy_boundary":
            expected_keys.add("evidence")
        _require_exact_keys(
            row,
            expected_keys,
            context=context,
        )
        if row.get("id") != definition["id"]:
            raise ValueError("frontend functional journey roster or order was altered")
        checks = row.get("checks")
        if not isinstance(checks, dict) or list(checks) != definition["required_checks"]:
            raise ValueError(f"{context} check roster or order differs from the protocol")
        for key in definition["required_checks"]:
            _strict_bool(checks, key, context)
        if definition["id"] == "location_privacy_boundary":
            recomputed_privacy = _frontend_privacy_evidence(
                row.get("evidence"), protocol=protocol, context=context
            )
            if any(
                checks[key] != recomputed_privacy[key] for key in definition["required_checks"]
            ):
                raise ValueError(f"{context} checks differ from raw privacy evidence")
        errors = _require_string_list(row.get("errors"), context=f"{context} errors")
        qualified = not errors and all(
            checks[key] is True for key in definition["required_checks"]
        )
        if type(row.get("qualified")) is not bool or row["qualified"] != qualified:
            raise ValueError(f"{context} qualification differs from raw checks")
        normalized[definition["id"]] = qualified
    return {
        "qualified": all(normalized.values()),
        "keyboard_journey_passed": normalized["keyboard_evidence_navigation"],
        "journeys": normalized,
    }
