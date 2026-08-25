from __future__ import annotations

# ruff: noqa: F401
import gzip
import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import scripts.upgrade_benchmark as upgrade_benchmark
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from scripts.upgrade_benchmark import (
    _assert_recomputed_summary_matches,
    _build_before_snapshot_seal,
    _capture_frontend_surface,
    _deployment,
    _development_retrieval,
    _frontend_bundle,
    _frontend_manual_review_protocol,
    _frontend_surface,
    _hard_probe,
    _live,
    _preview,
    _relevant_untracked_paths,
    _retrieval_qualification,
    _review,
    _semantic_holdout,
    _ux,
    _verify_before_snapshot_seal_payload,
    capture,
    compare_snapshots,
    load_dataset_role_registry,
    load_spec,
    validate_frontend_manual_review,
    validate_semantic_holdout,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data/evaluation/upgrade_benchmark_v1_5_2.yaml"
V3_PROTOCOL_PATH = ROOT / "data/evaluation/benchmark_v1_5_2_sealed_retrieval_v3.protocol.yaml"


def _write_manifest_fixture(client: Path, *, include_orphan: bool = False) -> None:
    dist = client.parent
    assets = client / "assets"
    manifest_dir = client / ".vite"
    assets.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    (assets / "app.js").write_text("const app = true;", encoding="utf-8")
    (assets / "shared.js").write_text("export const shared = true;", encoding="utf-8")
    (assets / "map.js").write_text("export const map = true;", encoding="utf-8")
    (assets / "app.css").write_text("body{color:#111}", encoding="utf-8")
    (assets / "map.css").write_text(".map{display:block}", encoding="utf-8")
    (assets / "brand.woff2").write_bytes(b"font-bytes")
    (assets / "logo.png").write_bytes(b"image-bytes")
    (client / "index.html").write_text("<main>FireLens</main>", encoding="utf-8")
    (dist / "server").mkdir(parents=True)
    (dist / "server/index.js").write_text("export default {};", encoding="utf-8")
    (dist / ".openai").mkdir(parents=True)
    (dist / ".openai/hosting.json").write_text("{}", encoding="utf-8")
    if include_orphan:
        (assets / "orphan.js").write_text("export const orphan = true;", encoding="utf-8")
    manifest = {
        "src/main.tsx": {
            "file": "assets/app.js",
            "isEntry": True,
            "imports": ["_shared.js"],
            "dynamicImports": ["src/map.tsx"],
            "css": ["assets/app.css"],
            "assets": ["assets/brand.woff2", "assets/logo.png"],
        },
        "_shared.js": {"file": "assets/shared.js"},
        "src/map.tsx": {
            "file": "assets/map.js",
            "imports": ["_shared.js"],
            "css": ["assets/map.css"],
        },
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_frontend_surface_fixture(
    tmp_path: Path, *, truncate_live_list: bool = False
) -> tuple[Path, dict, dict[str, str | int], dict, Path]:
    protocol_path = ROOT / "data/evaluation/frontend_surface.v1.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client)
    bundle = _frontend_bundle(dist)
    report_path = tmp_path / "report.json"
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    commit = "a" * 40
    browser_version = "151.0.7922.34"
    expected_environment: dict[str, str | int] = {
        "os": "Darwin",
        "os_release": "25.0.0",
        "architecture": "arm64",
        "cpu_model": "Apple M5",
        "logical_cpu_count": 10,
        "python_implementation": "CPython",
        "python_version": "3.14.5",
        "node_version": "v22.17.0",
        "npm_version": "10.9.2",
        "playwright_version": "1.62.0",
        "chromium_version": f"Google Chrome for Testing {browser_version}",
    }

    def execution_profile(viewport: dict) -> dict:
        return {
            "viewport_id": viewport["id"],
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "device_scale_factor": viewport["device_scale_factor"],
            "is_mobile": viewport["is_mobile"],
            "color_scheme": protocol["execution_environment"]["color_scheme"],
            "reduced_motion": protocol["execution_environment"]["reduced_motion"],
            "locale": protocol["execution_environment"]["locale"],
            "timezone_id": protocol["execution_environment"]["timezone_id"],
        }

    def unthrottled_profile(viewport: dict) -> dict:
        return {
            **execution_profile(viewport),
            "cpu_throttling": {"mode": "none", "rate": 1},
            "network": {
                "mode": "local_preview_with_deterministic_routes",
                "cache_policy": "fresh_browser_context_default",
            },
        }

    viewport_by_id = {viewport["id"]: viewport for viewport in protocol["viewports"]}
    desktop = viewport_by_id["desktop"]
    run_profiles = {
        "surface_matrix": [unthrottled_profile(viewport) for viewport in protocol["viewports"]],
        "functional_journeys": [
            {"journey_id": journey["id"], **unthrottled_profile(desktop)}
            for journey in protocol["functional_journeys"]
        ],
        "performance": [
            {
                "profile_id": profile_id,
                **execution_profile(viewport_by_id[profile_id]),
                "cpu_throttling": {
                    "mode": "cdp_emulation",
                    "rate": protocol["performance"]["cpu_throttling_rate"],
                },
                "network": {
                    "mode": "cdp_emulation",
                    **protocol["performance"]["network"],
                    "cache_disabled": protocol["performance"][
                        "cache_disabled_for_cold_samples"
                    ],
                },
            }
            for profile_id in protocol["performance"]["profiles"]
        ],
    }
    report_environment = {
        "os": {
            "name": "darwin",
            "release": expected_environment["os_release"],
            "architecture": expected_environment["architecture"],
            "cpu_model": expected_environment["cpu_model"],
            "logical_cpu_count": expected_environment["logical_cpu_count"],
        },
        "runtime": {
            "node_version": str(expected_environment["node_version"]).removeprefix("v"),
            "npm_version": expected_environment["npm_version"],
            "playwright_package_version": expected_environment["playwright_version"],
        },
        "browser": {
            "name": protocol["execution_environment"]["browser_name"],
            "version": browser_version,
            "headless": protocol["execution_environment"]["headless"],
            "locale": protocol["execution_environment"]["locale"],
            "timezone_id": protocol["execution_environment"]["timezone_id"],
        },
        "run_profiles": run_profiles,
    }

    def expected_map_ids(state_id: str) -> list[str]:
        if state_id == "live":
            return [f"incident:surface-{index:02d}" for index in range(1, 11)]
        if state_id in {"mixed", "stale", "partial_layer"}:
            return ["incident:surface-7"]
        return []

    def expected_map_record(state_id: str, record_id: str) -> dict[str, str]:
        if state_id == "live":
            suffix = record_id.rsplit("-", 1)[1]
            return {
                "name": f"Surface Test Fire {suffix}",
                "source_url": f"https://example.test/incidents/surface-{suffix}",
                "geometry_type": "Point",
            }
        return {
            "name": "Surface Test Fire",
            "source_url": "https://example.test/incidents/surface-7",
            "geometry_type": "Point",
        }

    surface_rows = []
    for state in protocol["states"]:
        for viewport in protocol["viewports"]:
            screenshot_path = screenshots / f"{state['id']}--{viewport['id']}.png"
            screenshot_image = Image.new(
                "RGB",
                (
                    viewport["width"] * viewport["device_scale_factor"],
                    viewport["height"] * viewport["device_scale_factor"],
                ),
                (12, 24, 36),
            )
            screenshot_image.putpixel((0, 0), (220, 230, 240))
            screenshot_image.save(screenshot_path, format="PNG")
            applicable = state["id"] in protocol["map_parity"]["applicable_state_ids"]
            map_parity: bool | None = None
            if applicable:
                expected_ids = expected_map_ids(state["id"])
                list_ids = (
                    expected_ids[:8]
                    if truncate_live_list and state["id"] == "live"
                    else expected_ids
                )
                list_records = [
                    {
                        "dom_index": index,
                        "rendered_name": expected_map_record(state["id"], record_id)["name"],
                        "rendered_source_url": expected_map_record(state["id"], record_id)[
                            "source_url"
                        ],
                        "record_id": record_id,
                        "geometry_type": "Point",
                        "resolution": "unique_name_and_source",
                    }
                    for index, record_id in enumerate(list_ids)
                ]
                map_records = [
                    {
                        "dom_index": index,
                        "rendered_popup_name": expected_map_record(state["id"], record_id)[
                            "name"
                        ],
                        "element_tag": "path",
                        "record_id": record_id,
                        "geometry_type": "Point",
                        "canonical_source_url": expected_map_record(state["id"], record_id)[
                            "source_url"
                        ],
                        "source_url_observed_in_popup": False,
                        "observed_visible": True,
                        "observed_center_css_px": {
                            "x": float(100 + index),
                            "y": float(200 + index),
                        },
                        "resolution": "unique_popup_name",
                    }
                    for index, record_id in enumerate(expected_ids)
                ]
                map_parity = list_ids == expected_ids
                map_evidence = {
                    "applicability": "applicable",
                    "reason": None,
                    "collection_status": "complete",
                    "pagination": {
                        "mode": protocol["map_parity"]["pagination_mode"],
                        "response_complete_roster": protocol["map_parity"][
                            "response_complete_roster"
                        ],
                        "rendered_complete_roster_required": True,
                        "map_surface_required": bool(expected_ids),
                        "expected_total_records": len(expected_ids),
                    },
                    "map_surface_present": bool(expected_ids),
                    "expected_response_record_ids": expected_ids,
                    "rendered_accessible_list_record_ids": list_ids,
                    "rendered_map_feature_or_marker_record_ids": expected_ids,
                    "rendered_accessible_list_records": list_records,
                    "rendered_map_feature_or_marker_records": map_records,
                    "unresolved_accessible_list_entries": [],
                    "unresolved_map_feature_or_marker_entries": [],
                    "detail_integrity": True,
                    "marker_placement_sanity": {
                        "scope": ("css_pixel_center_uniqueness_only_not_geospatial_accuracy"),
                        "observed_visible_marker_count": len(expected_ids),
                        "observed_unique_visible_center_count": len(expected_ids),
                        "expected_rendered_marker_count": len(expected_ids),
                        "sanity_passed": True,
                    },
                    "map_list_parity": map_parity,
                }
            else:
                map_evidence = {
                    "applicability": "not_applicable",
                    "reason": "state_not_in_map_parity_roster",
                    "collection_status": "not_applicable",
                    "pagination": None,
                    "map_surface_present": None,
                    "expected_response_record_ids": None,
                    "rendered_accessible_list_record_ids": None,
                    "rendered_map_feature_or_marker_record_ids": None,
                    "rendered_accessible_list_records": None,
                    "rendered_map_feature_or_marker_records": None,
                    "unresolved_accessible_list_entries": None,
                    "unresolved_map_feature_or_marker_entries": None,
                    "detail_integrity": None,
                    "marker_placement_sanity": None,
                    "map_list_parity": None,
                }
            expected_failure = (
                [
                    {
                        "url": "http://127.0.0.1:4175/api/v1/ask",
                        "status": 503,
                        "question": "surface:unavailable",
                    }
                ]
                if state["id"] == "provider_failure"
                else []
            )
            console_errors = (
                [
                    {
                        "text": (
                            "Failed to load resource: the server responded with a status "
                            "of 503 (Service Unavailable)"
                        ),
                        "location": {
                            "url": "http://127.0.0.1:4175/api/v1/ask",
                            "line": 0,
                            "column": 0,
                            "lineNumber": 0,
                            "columnNumber": 0,
                        },
                    }
                ]
                if expected_failure
                else []
            )
            expected_console_errors = (
                [
                    {
                        "event": console_errors[0],
                        "expected_http_failure": expected_failure[0],
                    }
                ]
                if expected_failure
                else []
            )
            request_events = [
                {
                    "sequence_index": 0,
                    "method": "GET",
                    "url": "http://127.0.0.1:4175/",
                    "origin": "http://127.0.0.1:4175",
                    "resource_type": "document",
                    "response_status": 200,
                    "failure": None,
                }
            ]
            if state["question"]:
                request_events.append(
                    {
                        "sequence_index": 1,
                        "method": "POST",
                        "url": "http://127.0.0.1:4175/api/v1/ask",
                        "origin": "http://127.0.0.1:4175",
                        "resource_type": "fetch",
                        "response_status": 503 if expected_failure else 200,
                        "failure": None,
                    }
                )
            request_derived = {
                "request_origins": ["http://127.0.0.1:4175"],
                "unexpected_request_origins": [],
                "failed_requests": [],
                "unallowlisted_failed_requests": [],
                "stylesheet_load_failures": [],
                "direct_third_party_tile_requests": [],
            }
            runtime = {
                "console_errors": console_errors,
                "expected_console_errors": expected_console_errors,
                "unexpected_console_errors": [],
                "expected_http_failures": expected_failure,
                "page_errors": [],
                "request_events": request_events,
                "request_derived": request_derived,
            }
            checks = {
                "axe_engine_version_bound": True,
                "axe_wcag_a_aa_findings_within_limit": True,
                "no_document_horizontal_overflow": True,
                "clipped_text_within_limit": True,
                "stylesheets_accessible": True,
                "stylesheets_loaded": True,
                "interactive_elements_styled": True,
                "interactive_targets_sized": True,
                "text_sizes_within_protocol": True,
                "console_clean": True,
                "page_errors_clean": True,
                "request_origins_allowed": True,
                "no_unallowlisted_failed_requests": True,
                "no_direct_third_party_tile_requests": True,
                "map_list_parity": map_parity if applicable else "not_applicable",
                "map_detail_integrity": True if applicable else "not_applicable",
                "map_marker_placement_sanity": (True if applicable else "not_applicable"),
            }
            surface_rows.append(
                {
                    "state_id": state["id"],
                    "viewport_id": viewport["id"],
                    "viewport": {
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "device_scale_factor": viewport["device_scale_factor"],
                        "is_mobile": viewport["is_mobile"],
                    },
                    "status": "complete",
                    "screenshot": {
                        "path": f"screenshots/{state['id']}--{viewport['id']}.png",
                        "sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
                        "bytes": screenshot_path.stat().st_size,
                        "format": "png",
                        "signature_hex": "89504e470d0a1a0a",
                        "width_px": viewport["width"] * viewport["device_scale_factor"],
                        "height_px": viewport["height"] * viewport["device_scale_factor"],
                    },
                    "axe": {
                        "engine_version": "4.12.1",
                        "installed_package_version": "4.12.1",
                        "engine_version_matches_installed_package": True,
                        "finding_count": 0,
                        "impact_counts": {
                            "critical": 0,
                            "serious": 0,
                            "moderate": 0,
                            "minor": 0,
                            "unknown": 0,
                        },
                        "findings": [],
                    },
                    "layout": {
                        "document_horizontal_overflow_px": 0,
                        "clipped_text_elements": [],
                        "undersized_text_elements": [],
                        "stylesheet_count": 2,
                        "css_rule_count": 10,
                        "inaccessible_stylesheets": [],
                        "undersized_interactive_elements": [],
                        "unstyled_interactive_elements": [],
                        "app_font_family": "Inter",
                    },
                    "map_evidence": map_evidence,
                    "runtime": runtime,
                    "checks": checks,
                    "qualified": all(
                        value is True or value == "not_applicable" for value in checks.values()
                    ),
                }
            )

    privacy_bodies = [
        {
            "context": {"visible_live_result_ids": []},
            "history": [],
            "question": "surface:requires-location",
        },
        {
            "context": {
                "selected_live_result_id": "incident:surface-7",
                "visible_live_result_ids": [],
            },
            "history": [
                {"content": "surface:requires-location", "role": "user"},
                {"content": "Share an approximate location.", "role": "assistant"},
            ],
            "location": {"latitude": 49.28, "longitude": -123.12, "radius_km": 50},
            "question": "surface:live-fresh",
        },
    ]
    privacy_api_roster = []
    for index, body in enumerate(privacy_bodies):
        body_sha256 = hashlib.sha256(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        privacy_api_roster.append(
            {
                "sequence_index": index,
                "method": "POST",
                "url": "http://127.0.0.1:4175/api/v1/ask",
                "origin": "http://127.0.0.1:4175",
                "resource_type": "fetch",
                "body": body,
                "body_sha256": body_sha256,
                "response_status": 200,
            }
        )
    privacy_network_events = [
        {
            "sequence_index": index,
            "method": "POST",
            "url": "http://127.0.0.1:4175/api/v1/ask",
            "origin": "http://127.0.0.1:4175",
            "resource_type": "fetch",
            "response_status": 200,
            "failure": None,
        }
        for index in range(2)
    ]
    privacy_network_derived = {
        "request_origins": ["http://127.0.0.1:4175"],
        "unexpected_request_origins": [],
        "failed_requests": [],
        "unallowlisted_failed_requests": [],
        "stylesheet_load_failures": [],
        "direct_third_party_tile_requests": [],
    }
    privacy_browser_surfaces = {
        "current_url": "http://127.0.0.1:4175/",
        "current_url_token_matches": [],
        "history": {
            "length": 2,
            "state_type": "null",
            "state_serialized_length": 4,
            "state_token_matches": [],
        },
        "local_storage": [],
        "session_storage": [],
        "cookies": [],
        "indexed_db": {"supported": True, "databases": []},
        "cache_storage": {"supported": True, "caches": []},
        "service_workers": {"supported": True, "registrations": []},
    }
    privacy_derived = {
        "geolocation_not_called_before_opt_in": True,
        "geolocation_called_once_after_opt_in": True,
        "coordinates_rounded_to_two_decimals": True,
        "location_sent_only_with_live_request": True,
        "location_not_persisted_in_browser_storage": True,
        "no_cookie_written": True,
        "canonical_request_roster_valid": True,
        "api_request_issues": [],
        "network_request_derivation_matches": True,
        "unexpected_network_entries": [],
        "body_token_leak_findings": [],
        "browser_token_leak_findings": [],
        "no_unexpected_request_or_body_leakage": True,
        "url_history_clean": True,
        "both_coordinate_tokens_absent_outside_allowed_request": True,
        "browser_storage_surfaces_clean": True,
    }
    privacy_evidence = {
        "fixture_data_only": True,
        "persistence_probe_tokens": protocol["privacy_evidence"]["persistence_probe_tokens"],
        "geolocation_calls": {"before_opt_in": 0, "after_opt_in": 1},
        "api_request_roster": privacy_api_roster,
        "network_request_events": privacy_network_events,
        "network_request_derived": privacy_network_derived,
        "browser_surfaces": privacy_browser_surfaces,
        "derived": privacy_derived,
    }
    functional_journeys = []
    for journey in protocol["functional_journeys"]:
        row = {
            "id": journey["id"],
            "checks": {key: True for key in journey["required_checks"]},
            "errors": [],
            "qualified": True,
        }
        if journey["id"] == "location_privacy_boundary":
            row["evidence"] = privacy_evidence
        functional_journeys.append(row)
    profiles = []
    p75 = {
        "lcp_ms": 1000.0,
        "cls": 0.01,
        "inp_interaction_proxy_ms": 100.0,
        "map_ready_after_interaction_ms": 500.0,
    }
    for profile_id in protocol["performance"]["profiles"]:
        samples = []
        for phase, sample_index in [("warmup", 1)] + [("cold", index) for index in range(1, 8)]:
            samples.append(
                {
                    "phase": phase,
                    "sample_index": sample_index,
                    **p75,
                    "status": "complete",
                    "error": None,
                }
            )
        profiles.append(
            {
                "profile_id": profile_id,
                "viewport": {
                    "width": viewport_by_id[profile_id]["width"],
                    "height": viewport_by_id[profile_id]["height"],
                },
                "throttling": {
                    "cpu_rate": protocol["performance"]["cpu_throttling_rate"],
                    "network": protocol["performance"]["network"],
                    "cache_disabled": protocol["performance"][
                        "cache_disabled_for_cold_samples"
                    ],
                },
                "samples": samples,
                "cold_p75": p75,
                "thresholds": protocol["performance"]["thresholds"][profile_id],
                "checks": {
                    "exact_sample_count": True,
                    "lcp_within_threshold": True,
                    "cls_within_threshold": True,
                    "inp_proxy_within_threshold": True,
                    "map_ready_within_threshold": True,
                },
                "qualified": True,
            }
        )
    qualified_rows = sum(row["qualified"] for row in surface_rows)
    protocol_ratified = protocol["status"] == "ratified" and bool(protocol["frozen_at"])
    summary = {
        "protocol_ratified": protocol_ratified,
        "expected_surface_rows": protocol["matrix"]["expected_rows"],
        "executed_surface_rows": len(surface_rows),
        "matrix_complete": True,
        "qualified_surface_rows": qualified_rows,
        "functional_journeys_qualified": True,
        "performance_qualified": True,
        "structure_issues": [],
        "qualified": protocol_ratified and qualified_rows == len(surface_rows),
    }
    report = {
        "schema_version": "firelens.frontend_surface_report.v1",
        "generated_at": "2026-08-06T12:00:00+00:00",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "protocol_status": protocol["status"],
        "protocol_frozen_at": protocol["frozen_at"],
        "base_url": "http://127.0.0.1:4175",
        "execution_environment": report_environment,
        "browser": {"name": "chromium", "version": browser_version},
        "build": {
            "commit": commit,
            "index_sha256": hashlib.sha256((client / "index.html").read_bytes()).hexdigest(),
            "manifest_sha256": bundle["manifest_sha256"],
        },
        "surface_rows": surface_rows,
        "functional_journeys": functional_journeys,
        "performance": {
            "aggregation": "p75_nearest_rank",
            "profiles": profiles,
            "qualified": True,
        },
        "summary": summary,
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path, report, expected_environment, bundle, client


def _write_frontend_manual_review_fixture(
    tmp_path: Path, *, commit: str = "a" * 40
) -> tuple[Path, dict, dict[tuple[str, str], str]]:
    protocol_path = ROOT / "data/evaluation/frontend_manual_review.v1.yaml"
    protocol = _frontend_manual_review_protocol(protocol_path)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    candidate_id = f"firelens-v1-5-2:{commit}"
    target_url = "https://candidate.example.test/"
    captured_at = "2026-08-06T09:10:00+00:00"
    evidence_rows: list[dict] = []
    evidence_by_pair: dict[tuple[str, str], str] = {}

    index = 0
    for profile in protocol["test_profiles"]:
        for state_id in protocol["state_roster"]:
            index += 1
            evidence_id = f"EV-{index:03d}"
            if index == 1:
                relative_path = "evidence/candidate-identity.json"
                payload = {
                    "schema_version": "firelens.frontend_candidate_identity_evidence.v1",
                    "captured_at": captured_at,
                    "request": {
                        "method": "GET",
                        "url": "https://candidate.example.test/api/v1/health/ready",
                    },
                    "response": {
                        "status_code": 200,
                        "content_type": "application/json",
                        "candidate_id": candidate_id,
                        "build_commit": commit,
                    },
                }
                content = json.dumps(payload, sort_keys=True).encode()
                media_type = "application/json"
            else:
                relative_path = f"evidence/{profile['id']}--{state_id}.txt"
                content = f"manual evidence {profile['id']} {state_id} {index}\n".encode()
                media_type = "text/plain"
            evidence_path = tmp_path / relative_path
            evidence_path.write_bytes(content)
            evidence_rows.append(
                {
                    "evidence_id": evidence_id,
                    "path": relative_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                    "media_type": media_type,
                    "captured_at": captured_at,
                    "description": f"Retained {profile['id']} evidence for {state_id}.",
                    "profile_ids": [profile["id"]],
                    "state_ids": [state_id],
                }
            )
            evidence_by_pair[(profile["id"], state_id)] = evidence_id

    assignments = [
        {
            "role": "accessibility_specialist",
            "reviewer_id": "reviewer-a11y-001",
            "reviewer_name": "Alex Morgan",
            "credentials": "Accessibility specialist experienced with VoiceOver and WCAG 2.2.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T09:40:00+00:00",
            "attestation": "I performed and verified every assigned accessibility check.",
        },
        {
            "role": "wildfire_product_safety_reviewer",
            "reviewer_id": "reviewer-safety-001",
            "reviewer_name": "Jordan Chen",
            "credentials": "Wildfire public-information and product-safety reviewer.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T09:40:00+00:00",
            "attestation": "I performed and verified every assigned product-safety check.",
        },
        {
            "role": "release_adjudicator",
            "reviewer_id": "reviewer-release-001",
            "reviewer_name": "Taylor Singh",
            "credentials": "Independent release adjudicator for evidence-bound qualification.",
            "assigned_at": "2026-08-06T08:30:00+00:00",
            "attested_at": "2026-08-06T10:05:00+00:00",
            "attestation": "I independently reconciled the complete retained review evidence.",
        },
    ]
    assignment_by_role = {row["role"]: row for row in assignments}
    environments = [
        {
            "profile_id": profile["id"],
            "reviewer_id": assignment_by_role[profile["required_role"]]["reviewer_id"],
            "os_name": profile["os_name"],
            "os_version": "test-os-1.0",
            "browser_name": profile["browser_name"],
            "browser_version": "test-browser-1.0",
            "assistive_technology": profile["assistive_technology"],
            "assistive_technology_version": (
                None if profile["assistive_technology"] == "none" else "test-at-1.0"
            ),
            "input_methods": profile["input_methods"],
            "viewport": profile["viewport"],
            "zoom_percentages": profile["zoom_percentages"],
            "reflow_widths_css_px": profile["reflow_widths_css_px"],
            "reduced_motion": profile["reduced_motion"],
            "verified_at": "2026-08-06T09:05:00+00:00",
        }
        for profile in protocol["test_profiles"]
    ]
    coverage = [
        {
            "profile_id": profile["id"],
            "state_id": state_id,
            "status": "pass",
            "reviewer_id": assignment_by_role[profile["required_role"]]["reviewer_id"],
            "observed_at": "2026-08-06T09:20:00+00:00",
            "evidence_ids": [evidence_by_pair[(profile["id"], state_id)]],
            "notes": f"Reviewed {state_id} under {profile['id']}.",
        }
        for profile in protocol["test_profiles"]
        for state_id in protocol["state_roster"]
    ]
    criteria = []
    atomic_ids: list[str] = []
    for criterion in protocol["criteria"]:
        checks = []
        for check in criterion["atomic_checks"]:
            check_id = check["id"]
            atomic_ids.append(check_id)
            required_profiles = protocol["atomic_check_requirements"][check_id][
                "required_profile_ids"
            ]
            role = criterion["required_role"]
            checks.append(
                {
                    "check_id": check_id,
                    "status": "pass",
                    "reviewer_id": assignment_by_role[role]["reviewer_id"],
                    "reviewed_at": "2026-08-06T09:30:00+00:00",
                    "evidence_ids": [
                        evidence_by_pair[(profile_id, "idle")]
                        for profile_id in required_profiles
                    ],
                    "notes": f"Completed frozen atomic check {check_id}.",
                }
            )
        criteria.append({"criterion_id": criterion["id"], "atomic_checks": checks})

    coverage_ids = [
        f"{profile['id']}/{state_id}"
        for profile in protocol["test_profiles"]
        for state_id in protocol["state_roster"]
    ]
    bundle = {
        "schema_version": "firelens.frontend_manual_review_bundle.v1",
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": upgrade_benchmark.file_sha256(protocol_path),
        },
        "candidate": {
            "candidate_id": candidate_id,
            "commit": commit,
            "target_url": target_url,
            "build_verified_at": "2026-08-06T08:00:00+00:00",
            "identity_evidence_id": "EV-001",
        },
        "review_window": {
            "started_at": "2026-08-06T09:00:00+00:00",
            "completed_at": "2026-08-06T09:45:00+00:00",
        },
        "role_assignments": assignments,
        "test_environments": environments,
        "evidence": evidence_rows,
        "coverage": coverage,
        "criteria": criteria,
        "findings": [],
        "adjudication": {
            "adjudicator_id": "reviewer-release-001",
            "decision": "qualified",
            "decided_at": "2026-08-06T10:00:00+00:00",
            "accessibility_qualified": True,
            "product_safety_qualified": True,
            "open_finding_count": 0,
            "criterion_ids": [criterion["id"] for criterion in protocol["criteria"]],
            "atomic_check_ids": atomic_ids,
            "test_profile_ids": [profile["id"] for profile in protocol["test_profiles"]],
            "state_ids": protocol["state_roster"],
            "coverage_ids": coverage_ids,
            "evidence_ids": [row["evidence_id"] for row in evidence_rows],
            "attestation": "All frozen criteria, environments, states, and retained evidence were reconciled.",
        },
        "generated_at": "2026-08-06T10:10:00+00:00",
    }
    bundle_path = tmp_path / "frontend-manual-review.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle_path, bundle, evidence_by_pair


__all__ = [name for name in globals() if not name.startswith("__")]
