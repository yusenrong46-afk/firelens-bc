from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_frontend_manual_protocol_freezes_thresholds_standards_and_matrix() -> None:
    protocol = _frontend_manual_review_protocol(
        ROOT / "data/evaluation/frontend_manual_review.v1.yaml"
    )

    assert protocol["status"] == "frozen"
    assert protocol["standards"]["wcag_version"] == "2.2"
    assert protocol["standards"]["conformance_level"] == "AA"
    assert protocol["manual_thresholds"] == {
        "normal_text_contrast_ratio_min": 4.5,
        "large_text_contrast_ratio_min": 3.0,
        "non_text_and_focus_contrast_ratio_min": 3.0,
        "browser_zoom_percent_required": 200,
        "reflow_width_css_px": 320,
        "horizontal_content_scroll_max_css_px": 0,
        "target_width_css_px_min": 24,
        "target_height_css_px_min": 24,
        "text_spacing": {
            "line_height_em_min": 1.5,
            "paragraph_spacing_em_min": 2.0,
            "letter_spacing_em_min": 0.12,
            "word_spacing_em_min": 0.16,
        },
    }
    assert len(protocol["test_profiles"]) == 5
    assert len(protocol["state_roster"]) == 10
    assert len(protocol["atomic_check_requirements"]) == 30
    assert all(
        requirement["required_profile_ids"]
        for requirement in protocol["atomic_check_requirements"].values()
    )


def test_frontend_manual_review_recomputes_complete_bundle(tmp_path: Path) -> None:
    bundle_path, _, _ = _write_frontend_manual_review_fixture(tmp_path)

    result = validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    assert result["status"] == "complete"
    assert result["candidate_id"] == f"firelens-v1-5-2:{'a' * 40}"
    assert result["test_profile_count"] == 5
    assert result["state_count"] == 10
    assert result["coverage_count"] == 50
    assert result["atomic_check_count"] == 30
    assert result["accessibility_qualified"] is True
    assert result["product_safety_qualified"] is True
    assert result["open_finding_count"] == 0
    assert result["qualified"] is True


def test_frontend_manual_review_records_honest_open_finding(tmp_path: Path) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    first_check = bundle["criteria"][0]["atomic_checks"][0]
    first_check["status"] = "fail"
    bundle["findings"] = [
        {
            "finding_id": "F-001",
            "target_type": "atomic_check",
            "target_id": first_check["check_id"],
            "severity": "high",
            "status": "open",
            "opened_at": "2026-08-06T09:25:00+00:00",
            "resolved_at": None,
            "owner_id": "reviewer-a11y-001",
            "resolution": None,
            "evidence_ids": [first_check["evidence_ids"][0]],
        }
    ]
    bundle["adjudication"].update(
        {
            "decision": "not_qualified",
            "accessibility_qualified": False,
            "open_finding_count": 1,
        }
    )
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    result = validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    assert result["accessibility_qualified"] is False
    assert result["product_safety_qualified"] is True
    assert result["open_finding_count"] == 1
    assert result["qualified"] is False


def test_frontend_manual_review_rejects_non_distinct_or_placeholder_roles(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["role_assignments"][1]["reviewer_name"] = bundle["role_assignments"][0][
        "reviewer_name"
    ]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="distinct people"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle["role_assignments"][1]["reviewer_name"] = "Reviewer"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="named human"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_sparse_matrix_or_check_evidence(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["coverage"].pop()
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage roster is incomplete"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    screen_reader_check = bundle["criteria"][1]["atomic_checks"][0]
    screen_reader_check["evidence_ids"] = screen_reader_check["evidence_ids"][:1]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="omits required test profiles"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_wrong_candidate_url_or_commit(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)

    with pytest.raises(ValueError, match="wrong candidate commit"):
        validate_frontend_manual_review(bundle_path, expected_commit="b" * 40)

    bundle["candidate"]["target_url"] = "https://other.example.test/"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="identity request targets the wrong URL"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_tampered_or_unsafe_retained_evidence(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    evidence_path = tmp_path / bundle["evidence"][1]["path"]
    evidence_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="digest does not match"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["evidence"][1]["path"] = "../outside.txt"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical relative path"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_review_rejects_timestamp_or_adjudication_tampering(
    tmp_path: Path,
) -> None:
    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["role_assignments"][0]["attested_at"] = "2026-08-06T09:15:00+00:00"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="attestation chain"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)

    bundle_path, bundle, _ = _write_frontend_manual_review_fixture(tmp_path)
    bundle["adjudication"]["open_finding_count"] = 1
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="summary differs"):
        validate_frontend_manual_review(bundle_path, expected_commit="a" * 40)


def test_frontend_manual_protocol_rejects_weakened_threshold(tmp_path: Path) -> None:
    protocol = yaml.safe_load(
        (ROOT / "data/evaluation/frontend_manual_review.v1.yaml").read_text(encoding="utf-8")
    )
    protocol["manual_thresholds"]["target_width_css_px_min"] = 20
    path = tmp_path / "weakened-protocol.yaml"
    path.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="thresholds are not canonical"):
        _frontend_manual_review_protocol(path)


def test_frontend_bundle_classifies_manifest_graph_initial_and_lazy(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client)

    bundle = _frontend_bundle(dist)
    by_name = {row["name"]: row for row in bundle["assets"]}

    assert {name: row["scope"] for name, row in by_name.items() if row["category"] == "js"} == {
        "client/assets/app.js": "initial",
        "client/assets/map.js": "lazy",
        "client/assets/shared.js": "initial",
        "server/index.js": "server",
    }
    initial_content = [
        (client / "assets/app.js").read_bytes(),
        (client / "assets/shared.js").read_bytes(),
    ]
    assert bundle["initial_js_bytes"] == sum(map(len, initial_content))
    assert bundle["initial_js_gzip_bytes"] == sum(
        len(gzip.compress(content, compresslevel=9, mtime=0)) for content in initial_content
    )
    map_content = (client / "assets/map.js").read_bytes()
    assert bundle["lazy_js_bytes"] == len(map_content)
    assert bundle["lazy_js_gzip_bytes"] == len(
        gzip.compress(map_content, compresslevel=9, mtime=0)
    )
    assert bundle["total_js_bytes"] == (
        bundle["initial_js_bytes"] + bundle["lazy_js_bytes"] + bundle["server_js_bytes"]
    )
    assert by_name["client/assets/app.css"]["scope"] == "initial"
    assert by_name["client/assets/map.css"]["scope"] == "lazy"
    assert bundle["initial_css_gzip_bytes"] == len(
        gzip.compress((client / "assets/app.css").read_bytes(), compresslevel=9, mtime=0)
    )
    assert bundle["lazy_css_gzip_bytes"] == len(
        gzip.compress((client / "assets/map.css").read_bytes(), compresslevel=9, mtime=0)
    )
    assert bundle["font_bytes"] == len((client / "assets/brand.woff2").read_bytes())
    assert bundle["image_bytes"] == len((client / "assets/logo.png").read_bytes())
    assert bundle["server_js_bytes"] == len((dist / "server/index.js").read_bytes())
    assert bundle["deployment_metadata_bytes"] == len(
        (dist / ".openai/hosting.json").read_bytes()
    )
    assert bundle["unclassified_files"] == []
    assert bundle["unclassified_bytes"] == 0
    assert {row["name"] for row in bundle["assets"]} == {
        path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()
    }


def test_frontend_bundle_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Vite manifest is missing"):
        _frontend_bundle(tmp_path / "dist")


def test_frontend_bundle_rejects_unclassified_emitted_javascript(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    client = dist / "client"
    _write_manifest_fixture(client, include_orphan=True)

    with pytest.raises(ValueError, match="classification mismatch"):
        _frontend_bundle(dist)


@pytest.mark.parametrize("relative", ["server/index.js", ".openai/hosting.json"])
def test_frontend_bundle_rejects_omitted_runtime_artifact(
    tmp_path: Path, relative: str
) -> None:
    dist = tmp_path / "dist"
    _write_manifest_fixture(dist / "client")
    (dist / relative).unlink()

    with pytest.raises(ValueError, match="missing required server/hosting artifacts"):
        _frontend_bundle(dist)


def test_frontend_surface_recomputes_complete_report(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["visual_matrix_pass_rate"] == 1.0
    assert result["map_list_parity"] is True
    assert result["worst_profile_p75"] == {
        "lcp_ms": 1000.0,
        "cls": 0.01,
        "inp_interaction_proxy_ms": 100.0,
        "map_ready_after_interaction_ms": 500.0,
    }
    assert result["qualified"] is report["summary"]["qualified"]


def test_frontend_surface_accepts_real_failing_map_roster(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(
        tmp_path, truncate_live_list=True
    )

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["map_list_parity"] is False
    assert result["visual_matrix_pass_rate"] == 33 / 36
    assert result["qualified"] is False


def test_frontend_surface_gates_moderate_wcag_a_aa_finding(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    row = report["surface_rows"][0]
    row["axe"] = {
        "engine_version": "4.12.1",
        "installed_package_version": "4.12.1",
        "engine_version_matches_installed_package": True,
        "finding_count": 1,
        "impact_counts": {
            "critical": 0,
            "serious": 0,
            "moderate": 1,
            "minor": 0,
            "unknown": 0,
        },
        "findings": [
            {
                "id": "color-contrast",
                "impact": "moderate",
                "tags": ["wcag2aa"],
                "help": "Elements must meet minimum color contrast ratio thresholds",
                "help_url": "https://dequeuniversity.com/rules/axe/color-contrast",
                "nodes": [
                    {
                        "target": [".secondary-copy"],
                        "failure_summary": "Contrast is below the required threshold.",
                    }
                ],
            }
        ],
    }
    row["checks"]["axe_wcag_a_aa_findings_within_limit"] = False
    row["qualified"] = False
    report["summary"]["qualified_surface_rows"] = 35
    report["summary"]["qualified"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["axe_wcag_a_aa_finding_count"] == 1
    assert result["visual_matrix_pass_rate"] == 35 / 36


def test_frontend_surface_accepts_but_fails_unallowlisted_request(
    tmp_path: Path,
) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    row = report["surface_rows"][0]
    event = {
        "sequence_index": len(row["runtime"]["request_events"]),
        "method": "GET",
        "url": "https://unexpected.example.test/failure",
        "origin": "https://unexpected.example.test",
        "resource_type": "image",
        "response_status": None,
        "failure": "net::ERR_FAILED",
    }
    row["runtime"]["request_events"].append(event)
    row["runtime"]["request_derived"] = {
        "request_origins": [
            "http://127.0.0.1:4175",
            "https://unexpected.example.test",
        ],
        "unexpected_request_origins": ["https://unexpected.example.test"],
        "failed_requests": [event],
        "unallowlisted_failed_requests": [event],
        "stylesheet_load_failures": [],
        "direct_third_party_tile_requests": [],
    }
    row["checks"]["request_origins_allowed"] = False
    row["checks"]["no_unallowlisted_failed_requests"] = False
    row["qualified"] = False
    report["summary"]["qualified_surface_rows"] = 35
    report["summary"]["qualified"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["runtime_violation_count"] == 2
    assert result["visual_matrix_pass_rate"] == 35 / 36


@pytest.mark.parametrize(
    "mutation",
    [
        "unexpected_top_key",
        "surface_roster_order",
        "summary_aggregate",
        "screenshot_digest",
        "performance_sample",
        "performance_p75",
        "environment_identity",
        "build_identity",
        "map_parity_aggregate",
        "map_dom_partition",
        "map_canonical_detail",
        "marker_placement_aggregate",
        "runtime_derived",
        "console_blank_url",
        "axe_version",
        "axe_impact_aggregate",
        "privacy_derived",
        "privacy_request_body_digest",
    ],
)
def test_frontend_surface_rejects_tampered_evidence(tmp_path: Path, mutation: str) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    if mutation == "unexpected_top_key":
        report["synthetic_override"] = True
    elif mutation == "surface_roster_order":
        report["surface_rows"][0], report["surface_rows"][1] = (
            report["surface_rows"][1],
            report["surface_rows"][0],
        )
    elif mutation == "summary_aggregate":
        report["summary"]["qualified_surface_rows"] = 0
    elif mutation == "screenshot_digest":
        report["surface_rows"][0]["screenshot"]["sha256"] = "f" * 64
    elif mutation == "performance_sample":
        report["performance"]["profiles"][0]["samples"].pop()
    elif mutation == "performance_p75":
        report["performance"]["profiles"][0]["cold_p75"]["lcp_ms"] = 1.0
    elif mutation == "environment_identity":
        report["execution_environment"]["os"]["cpu_model"] = "Different CPU"
    elif mutation == "build_identity":
        report["build"]["manifest_sha256"] = "f" * 64
    elif mutation == "map_parity_aggregate":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["map_list_parity"] = False
    elif mutation == "map_dom_partition":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["rendered_accessible_list_records"][0]["dom_index"] = 4
    elif mutation == "map_canonical_detail":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["rendered_accessible_list_records"][0][
            "rendered_source_url"
        ] = "https://example.test/wrong"
    elif mutation == "marker_placement_aggregate":
        live_row = next(row for row in report["surface_rows"] if row["state_id"] == "live")
        live_row["map_evidence"]["marker_placement_sanity"]["observed_visible_marker_count"] = 0
    elif mutation == "runtime_derived":
        report["surface_rows"][0]["runtime"]["request_derived"]["request_origins"] = []
    elif mutation == "console_blank_url":
        provider_row = next(
            row for row in report["surface_rows"] if row["state_id"] == "provider_failure"
        )
        provider_row["runtime"]["console_errors"][0]["location"]["url"] = ""
    elif mutation == "axe_version":
        report["surface_rows"][0]["axe"]["installed_package_version"] = "4.11.0"
    elif mutation == "axe_impact_aggregate":
        report["surface_rows"][0]["axe"]["impact_counts"]["moderate"] = 1
    elif mutation == "privacy_derived":
        privacy = next(
            row
            for row in report["functional_journeys"]
            if row["id"] == "location_privacy_boundary"
        )
        privacy["evidence"]["derived"]["url_history_clean"] = False
    elif mutation == "privacy_request_body_digest":
        privacy = next(
            row
            for row in report["functional_journeys"]
            if row["id"] == "location_privacy_boundary"
        )
        privacy["evidence"]["api_request_roster"][0]["body_sha256"] = "f" * 64
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


def test_frontend_surface_rejects_missing_screenshot_file(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    (report_path.parent / report["surface_rows"][0]["screenshot"]["path"]).unlink()

    with pytest.raises(ValueError, match="screenshot file is missing"):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


def test_frontend_surface_accepts_bounded_full_page_screenshot(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    screenshot = report["surface_rows"][0]["screenshot"]
    screenshot_path = report_path.parent / screenshot["path"]
    image = Image.new("RGB", (390, 1688), (0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255))
    image.save(screenshot_path, format="PNG")
    screenshot["bytes"] = screenshot_path.stat().st_size
    screenshot["sha256"] = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    screenshot["height_px"] = 1688
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _frontend_surface(
        report_path,
        protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
        expected_commit=report["build"]["commit"],
        expected_environment=environment,
        frontend_bundle=bundle,
        client_root=client,
    )

    assert result["visual_matrix_pass_rate"] == 1.0


def test_frontend_surface_rejects_visually_uniform_screenshot(tmp_path: Path) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    screenshot = report["surface_rows"][0]["screenshot"]
    screenshot_path = report_path.parent / screenshot["path"]
    Image.new("RGB", (390, 844), (0, 0, 0)).save(screenshot_path, format="PNG")
    screenshot["bytes"] = screenshot_path.stat().st_size
    screenshot["sha256"] = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="visually uniform"):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )


@pytest.mark.parametrize(
    "mutation", ["invalid_png", "wrong_dimensions", "absurd_height", "symlink"]
)
def test_frontend_surface_rejects_ineligible_screenshot_artifact(
    tmp_path: Path, mutation: str
) -> None:
    report_path, report, environment, bundle, client = _write_frontend_surface_fixture(tmp_path)
    screenshot = report["surface_rows"][0]["screenshot"]
    screenshot_path = report_path.parent / screenshot["path"]
    if mutation == "invalid_png":
        screenshot_path.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"truncated")
    elif mutation == "wrong_dimensions":
        Image.new("RGB", (2, 2), (0, 0, 0)).save(screenshot_path, format="PNG")
        screenshot["width_px"] = 2
        screenshot["height_px"] = 2
    elif mutation == "absurd_height":
        Image.new("RGB", (390, 844 * 21), (0, 0, 0)).save(screenshot_path, format="PNG")
        screenshot["height_px"] = 844 * 21
    else:
        target = tmp_path / "external.png"
        Image.new("RGB", (390, 844), (0, 0, 0)).save(target, format="PNG")
        screenshot_path.unlink()
        screenshot_path.symlink_to(target)
    screenshot["bytes"] = screenshot_path.stat().st_size
    screenshot["sha256"] = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="screenshot"):
        _frontend_surface(
            report_path,
            protocol_path=ROOT / "data/evaluation/frontend_surface.v1.yaml",
            expected_commit=report["build"]["commit"],
            expected_environment=environment,
            frontend_bundle=bundle,
            client_root=client,
        )
