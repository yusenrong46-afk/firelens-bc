import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  canonicalApiRequestRecord,
  classifyConsoleErrors,
  configuredExecutionRunProfiles,
  derivePrivacyEvidence,
  deriveRequestEvidence,
  expectedMapResponseDetails,
  expectedMapResponseRecordIds,
  loadProtocol,
  p75NearestRank,
  recomputeMapListParity,
  surfaceMatrixComplete,
  validateReportStructure,
} from "../scripts/qualify-frontend-surface.mjs";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendRoot, "../..");
const protocolPath = path.join(repositoryRoot, "data/evaluation/frontend_surface.v1.yaml");
const installedAxeCoreVersion = JSON.parse(await readFile(
  path.join(frontendRoot, "node_modules/axe-core/package.json"),
  "utf8",
)).version;

function mapEvidenceForState(protocol, state) {
  if (!protocol.map_parity.applicable_state_ids.includes(state.id)) {
    return {
      applicability: "not_applicable",
      reason: "state_not_in_map_parity_roster",
      collection_status: "not_applicable",
      pagination: null,
      map_surface_present: null,
      expected_response_record_ids: null,
      rendered_accessible_list_record_ids: null,
      rendered_map_feature_or_marker_record_ids: null,
      rendered_accessible_list_records: null,
      rendered_map_feature_or_marker_records: null,
      unresolved_accessible_list_entries: null,
      unresolved_map_feature_or_marker_entries: null,
      detail_integrity: null,
      marker_placement_sanity: null,
      map_list_parity: null,
    };
  }
  const ids = expectedMapResponseRecordIds(state);
  const details = expectedMapResponseDetails(state);
  const evidence = {
    applicability: "applicable",
    reason: null,
    collection_status: "complete",
    pagination: {
      mode: protocol.map_parity.pagination_mode,
      response_complete_roster: protocol.map_parity.response_complete_roster,
      rendered_complete_roster_required:
        protocol.map_parity.allow_rendered_roster_truncation === false,
      map_surface_required: ids.length > 0,
      expected_total_records: ids.length,
    },
    map_surface_present: ids.length > 0,
    expected_response_record_ids: ids,
    rendered_accessible_list_record_ids: [...ids],
    rendered_map_feature_or_marker_record_ids: [...ids],
    rendered_accessible_list_records: details.map((record, domIndex) => ({
      dom_index: domIndex,
      rendered_name: record.name,
      rendered_source_url: record.source_url,
      record_id: record.result_id,
      geometry_type: record.geometry_type,
      resolution: "unique_name_and_source",
    })),
    rendered_map_feature_or_marker_records: details.map((record, domIndex) => ({
      dom_index: domIndex,
      rendered_popup_name: record.name,
      element_tag: "path",
      record_id: record.result_id,
      geometry_type: record.geometry_type,
      canonical_source_url: record.source_url,
      source_url_observed_in_popup: false,
      observed_visible: true,
      observed_center_css_px: { x: domIndex * 10, y: domIndex * 10 },
      resolution: "unique_popup_name",
    })),
    unresolved_accessible_list_entries: [],
    unresolved_map_feature_or_marker_entries: [],
    detail_integrity: true,
    marker_placement_sanity: {
      scope: "css_pixel_center_uniqueness_only_not_geospatial_accuracy",
      observed_visible_marker_count: ids.length,
      observed_unique_visible_center_count: ids.length,
      expected_rendered_marker_count: ids.length,
      sanity_passed: true,
    },
    map_list_parity: false,
  };
  evidence.map_list_parity = recomputeMapListParity(evidence);
  return evidence;
}

function requestEvent(sequenceIndex, overrides = {}) {
  const url = overrides.url ?? "http://127.0.0.1:4175/";
  return {
    sequence_index: sequenceIndex,
    method: overrides.method ?? "GET",
    url,
    origin: new URL(url).origin,
    resource_type: overrides.resource_type ?? "document",
    response_status: overrides.response_status ?? 200,
    failure: overrides.failure ?? null,
  };
}

function privacyEvidence(protocol) {
  const apiRequestRoster = [
    canonicalApiRequestRecord({
      sequenceIndex: 0,
      method: "POST",
      url: protocol.privacy_evidence.request_url,
      resourceType: "fetch",
      body: { question: "surface:requires-location", history: [] },
      responseStatus: 200,
    }),
    canonicalApiRequestRecord({
      sequenceIndex: 1,
      method: "POST",
      url: protocol.privacy_evidence.request_url,
      resourceType: "fetch",
      body: {
        question: "surface:live-fresh",
        history: [
          { role: "user", content: "surface:requires-location" },
          { role: "assistant", content: "fixture answer" },
        ],
        location: { latitude: 49.28, longitude: -123.12, radius_km: 50 },
      },
      responseStatus: 200,
    }),
  ];
  const networkRequestEvents = [
    requestEvent(0),
    requestEvent(1, {
      method: "POST",
      url: protocol.privacy_evidence.request_url,
      resource_type: "fetch",
    }),
    requestEvent(2, {
      method: "POST",
      url: protocol.privacy_evidence.request_url,
      resource_type: "fetch",
    }),
  ];
  const evidence = {
    fixture_data_only: true,
    persistence_probe_tokens: protocol.privacy_evidence.persistence_probe_tokens,
    geolocation_calls: { before_opt_in: 0, after_opt_in: 1 },
    api_request_roster: apiRequestRoster,
    network_request_events: networkRequestEvents,
    network_request_derived: deriveRequestEvidence(
      networkRequestEvents,
      protocol.surface_thresholds,
    ),
    browser_surfaces: {
      current_url: "http://127.0.0.1:4175/",
      current_url_token_matches: [],
      history: {
        length: 2,
        state_type: "null",
        state_serialized_length: 4,
        state_token_matches: [],
      },
      local_storage: [],
      session_storage: [],
      cookies: [],
      indexed_db: { supported: true, databases: [] },
      cache_storage: { supported: true, caches: [] },
      service_workers: { supported: true, registrations: [] },
    },
    derived: null,
  };
  evidence.derived = derivePrivacyEvidence(evidence, protocol);
  return evidence;
}

function performanceProfile(protocol, profileId) {
  const viewport = protocol.viewports.find((item) => item.id === profileId);
  const samples = [
    { phase: "warmup", sample_index: 1 },
    ...Array.from({ length: 7 }, (_, index) => ({
      phase: "cold",
      sample_index: index + 1,
    })),
  ].map((sample, index) => ({
    ...sample,
    lcp_ms: 800 + index,
    cls: 0.01,
    inp_interaction_proxy_ms: 30 + index,
    map_ready_after_interaction_ms: 820 + index,
    status: "complete",
    error: null,
  }));
  const cold = samples.filter((sample) => sample.phase === "cold");
  const coldP75 = {
    lcp_ms: p75NearestRank(cold.map((sample) => sample.lcp_ms)),
    cls: p75NearestRank(cold.map((sample) => sample.cls)),
    inp_interaction_proxy_ms: p75NearestRank(
      cold.map((sample) => sample.inp_interaction_proxy_ms),
    ),
    map_ready_after_interaction_ms: p75NearestRank(
      cold.map((sample) => sample.map_ready_after_interaction_ms),
    ),
  };
  const thresholds = protocol.performance.thresholds[profileId];
  const checks = {
    exact_sample_count: true,
    lcp_within_threshold: coldP75.lcp_ms <= thresholds.lcp_ms_max,
    cls_within_threshold: coldP75.cls <= thresholds.cls_max,
    inp_proxy_within_threshold:
      coldP75.inp_interaction_proxy_ms <= thresholds.inp_interaction_proxy_ms_max,
    map_ready_within_threshold:
      coldP75.map_ready_after_interaction_ms
      <= thresholds.map_ready_after_interaction_ms_max,
  };
  return {
    profile_id: profileId,
    viewport: { width: viewport.width, height: viewport.height },
    throttling: {
      cpu_rate: protocol.performance.cpu_throttling_rate,
      network: protocol.performance.network,
      cache_disabled: protocol.performance.cache_disabled_for_cold_samples,
    },
    samples,
    cold_p75: coldP75,
    thresholds,
    checks,
    qualified: Object.values(checks).every(Boolean),
  };
}

function completeReport(protocol) {
  const surfaceRows = protocol.states.flatMap((state) => (
    protocol.viewports.map((viewport) => {
      const mapEvidence = mapEvidenceForState(protocol, state);
      const requestEvents = [requestEvent(0)];
      const requestDerived = deriveRequestEvidence(
        requestEvents,
        protocol.surface_thresholds,
      );
      return {
        state_id: state.id,
        viewport_id: viewport.id,
        status: "complete",
        screenshot: {
          path: `output/${state.id}-${viewport.id}.png`,
          sha256: "a".repeat(64),
          bytes: 1,
          format: "png",
          signature_hex: "89504e470d0a1a0a",
          width_px: viewport.width * viewport.device_scale_factor,
          height_px: viewport.height * viewport.device_scale_factor,
        },
        axe: {
          engine_version: installedAxeCoreVersion,
          installed_package_version: installedAxeCoreVersion,
          engine_version_matches_installed_package: true,
          finding_count: 0,
          impact_counts: {
            critical: 0,
            serious: 0,
            moderate: 0,
            minor: 0,
            unknown: 0,
          },
          findings: [],
        },
        layout: {},
        map_evidence: mapEvidence,
        runtime: {
          console_errors: [],
          expected_console_errors: [],
          unexpected_console_errors: [],
          expected_http_failures: [],
          page_errors: [],
          request_events: requestEvents,
          request_derived: requestDerived,
        },
        checks: {
          axe_engine_version_bound: true,
          axe_wcag_a_aa_findings_within_limit: true,
          stylesheets_loaded: true,
          request_origins_allowed: true,
          no_unallowlisted_failed_requests: true,
          no_direct_third_party_tile_requests: true,
          map_list_parity: mapEvidence.applicability === "applicable"
            ? mapEvidence.map_list_parity
            : "not_applicable",
          map_detail_integrity: mapEvidence.applicability === "applicable"
            ? mapEvidence.detail_integrity
            : "not_applicable",
          map_marker_placement_sanity: mapEvidence.applicability === "applicable"
            ? mapEvidence.marker_placement_sanity.sanity_passed
            : "not_applicable",
        },
        qualified: false,
      };
    })
  ));
  const journeyRows = protocol.functional_journeys.map((journey) => {
    if (journey.id === "location_privacy_boundary") {
      const evidence = privacyEvidence(protocol);
      const checks = Object.fromEntries(
        journey.required_checks.map((check) => [check, evidence.derived[check]]),
      );
      return { id: journey.id, checks, evidence, errors: [], qualified: true };
    }
    return {
      id: journey.id,
      checks: Object.fromEntries(journey.required_checks.map((check) => [check, true])),
      errors: [],
      qualified: true,
    };
  });
  const profiles = protocol.performance.profiles.map(
    (profileId) => performanceProfile(protocol, profileId),
  );
  return {
    schema_version: "firelens.frontend_surface_report.v1",
    protocol_id: protocol.protocol_id,
    execution_environment: {
      os: {
        name: "darwin",
        release: "25.0.0",
        architecture: "arm64",
        cpu_model: "Test CPU",
        logical_cpu_count: 8,
      },
      runtime: {
        node_version: "22.1.0",
        npm_version: "11.1.0",
        playwright_package_version: "1.58.2",
      },
      browser: {
        name: protocol.execution_environment.browser_name,
        version: "140.0.0",
        headless: protocol.execution_environment.headless,
        locale: protocol.execution_environment.locale,
        timezone_id: protocol.execution_environment.timezone_id,
      },
      run_profiles: configuredExecutionRunProfiles(protocol),
    },
    surface_rows: surfaceRows,
    functional_journeys: journeyRows,
    performance: {
      aggregation: protocol.performance.aggregation,
      profiles,
      qualified: profiles.every((profile) => profile.qualified),
    },
  };
}

test("JSON-compatible YAML freezes the exact safety-critical matrix", async () => {
  const raw = await readFile(protocolPath, "utf8");
  assert.doesNotThrow(() => JSON.parse(raw));
  const protocol = await loadProtocol(protocolPath);

  assert.equal(protocol.status, "provisional");
  assert.equal(protocol.frozen_at, null);
  assert.deepEqual(protocol.states.map((state) => state.id), [
    "idle",
    "grounded",
    "partial",
    "background",
    "requires_input",
    "abstention",
    "provider_failure",
    "live",
    "mixed",
    "stale",
    "no_result",
    "partial_layer",
  ]);
  assert.deepEqual(protocol.viewports.map((viewport) => viewport.id), [
    "mobile",
    "tablet",
    "desktop",
  ]);
  assert.equal(protocol.matrix.expected_rows, 36);
  assert.equal(protocol.performance.warmup_samples, 1);
  assert.equal(protocol.performance.cold_samples, 7);
  assert.equal(protocol.performance.network.download_bytes_per_second, 200_000);
  assert.equal(protocol.performance.network.upload_bytes_per_second, 93_750);
  for (const profileId of protocol.performance.profiles) {
    assert.deepEqual(protocol.performance.thresholds[profileId], {
      lcp_ms_max: 2500,
      cls_max: 0.1,
      inp_interaction_proxy_ms_max: 200,
      map_ready_after_interaction_ms_max: 2000,
    });
  }
  assert.equal(protocol.surface_thresholds.direct_third_party_tile_requests_max, 48);
  assert.equal(protocol.surface_thresholds.axe_wcag_a_aa_findings_max, 0);
  assert.deepEqual(protocol.surface_thresholds.allowed_failed_request_urls, []);
  assert.deepEqual(protocol.map_parity.applicable_state_ids, [
    "live",
    "mixed",
    "stale",
    "no_result",
    "partial_layer",
  ]);
  assert.equal(protocol.map_parity.response_complete_roster, true);
  assert.equal(protocol.map_parity.allow_rendered_roster_truncation, false);
  assert.deepEqual(protocol.execution_environment, {
    locale: "en-CA",
    timezone_id: "America/Vancouver",
    color_scheme: "light",
    reduced_motion: "reduce",
    browser_name: "chromium",
    headless: true,
  });
  assert.deepEqual(protocol.privacy_evidence.persistence_probe_tokens, [
    "49.282729",
    "-123.120738",
    "49.28",
    "-123.12",
  ]);
});

test("report validation requires every state and viewport exactly once", async () => {
  const protocol = await loadProtocol(protocolPath);
  const report = completeReport(protocol);
  assert.deepEqual(validateReportStructure(report, protocol), []);
  assert.equal(surfaceMatrixComplete(report.surface_rows, protocol), true);

  report.surface_rows.pop();
  assert.equal(surfaceMatrixComplete(report.surface_rows, protocol), false);
  assert.match(validateReportStructure(report, protocol).join("\n"), /missing surface row/);

  report.surface_rows.push(report.surface_rows[0]);
  assert.equal(surfaceMatrixComplete(report.surface_rows, protocol), false);
  assert.match(validateReportStructure(report, protocol).join("\n"), /duplicate surface row/);
});

test("screenshot PNG path, signature, width, and bounded full-page height fail closed", async () => {
  const protocol = await loadProtocol(protocolPath);
  const mutations = [
    (screenshot) => { screenshot.width_px += 1; },
    (screenshot, viewport) => { screenshot.height_px = viewport.height - 1; },
    (screenshot, viewport) => { screenshot.height_px = (20 * viewport.height) + 1; },
    (screenshot) => { screenshot.format = "jpeg"; },
    (screenshot) => { screenshot.signature_hex = "0000000000000000"; },
    (screenshot) => { screenshot.path = "../escape.png"; },
  ];
  for (const mutate of mutations) {
    const report = completeReport(protocol);
    mutate(report.surface_rows[0].screenshot, protocol.viewports[0]);
    assert.match(
      validateReportStructure(report, protocol).join("\n"),
      /invalid screenshot evidence/,
    );
  }
});

test("performance roster fails closed on a missing cold sample", async () => {
  const protocol = await loadProtocol(protocolPath);
  const report = completeReport(protocol);
  report.performance.profiles[0].samples.pop();
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /performance sample count mismatch/,
  );
});

test("duplicate journeys and profiles fail closed", async () => {
  const protocol = await loadProtocol(protocolPath);
  const journeyReport = completeReport(protocol);
  journeyReport.functional_journeys[1] = structuredClone(
    journeyReport.functional_journeys[0],
  );
  assert.match(
    validateReportStructure(journeyReport, protocol).join("\n"),
    /duplicate functional journey id/,
  );

  const profileReport = completeReport(protocol);
  profileReport.performance.profiles[1] = structuredClone(
    profileReport.performance.profiles[0],
  );
  assert.match(
    validateReportStructure(profileReport, protocol).join("\n"),
    /duplicate performance profile id/,
  );
});

test("performance sample order, status, p75, and checks are recomputed", async () => {
  const protocol = await loadProtocol(protocolPath);

  const orderReport = completeReport(protocol);
  [
    orderReport.performance.profiles[0].samples[1],
    orderReport.performance.profiles[0].samples[2],
  ] = [
    orderReport.performance.profiles[0].samples[2],
    orderReport.performance.profiles[0].samples[1],
  ];
  assert.match(
    validateReportStructure(orderReport, protocol).join("\n"),
    /performance sample invalid/,
  );

  const statusReport = completeReport(protocol);
  statusReport.performance.profiles[0].samples[1].status = "error";
  assert.match(
    validateReportStructure(statusReport, protocol).join("\n"),
    /performance sample invalid/,
  );

  const p75Report = completeReport(protocol);
  p75Report.performance.profiles[0].cold_p75.lcp_ms += 1;
  assert.match(
    validateReportStructure(p75Report, protocol).join("\n"),
    /performance derivation mismatch/,
  );

  const checkReport = completeReport(protocol);
  checkReport.performance.profiles[0].checks.lcp_within_threshold = false;
  assert.match(
    validateReportStructure(checkReport, protocol).join("\n"),
    /performance derivation mismatch/,
  );
});

test("execution environment mutations fail closed", async () => {
  const protocol = await loadProtocol(protocolPath);
  const report = completeReport(protocol);
  report.execution_environment.run_profiles.performance[0]
    .network.download_bytes_per_second = 1;
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /execution_environment run profile mismatch/,
  );
});

test("map parity is recomputed from the complete 10-record roster", async () => {
  const protocol = await loadProtocol(protocolPath);
  const liveState = protocol.states.find((state) => state.id === "live");
  const expectedIds = expectedMapResponseRecordIds(liveState);
  assert.equal(expectedIds.length, 10);

  const report = completeReport(protocol);
  const liveRow = report.surface_rows.find(
    (row) => row.state_id === "live" && row.viewport_id === "desktop",
  );
  assert.deepEqual(
    liveRow.map_evidence.rendered_map_feature_or_marker_record_ids,
    expectedIds,
  );
  liveRow.map_evidence.rendered_accessible_list_record_ids = expectedIds.slice(0, 8);
  liveRow.map_evidence.rendered_accessible_list_records =
    liveRow.map_evidence.rendered_accessible_list_records.slice(0, 8);
  assert.equal(liveRow.map_evidence.rendered_accessible_list_record_ids.length, 8);
  assert.equal(recomputeMapListParity(liveRow.map_evidence), false);
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /map parity recomputation mismatch/,
  );

  liveRow.map_evidence.map_list_parity = false;
  liveRow.checks.map_list_parity = false;
  assert.deepEqual(validateReportStructure(report, protocol), []);
});

test("map detail partitions, canonical fields, indices, and marker centers fail closed", async () => {
  const protocol = await loadProtocol(protocolPath);
  const mutations = [
    (row) => { row.map_evidence.rendered_accessible_list_records[0].dom_index = 1; },
    (row) => { row.map_evidence.rendered_accessible_list_records[0].rendered_name = "Wrong"; },
    (row) => {
      row.map_evidence.rendered_accessible_list_records[0].rendered_source_url
        = "https://example.test/wrong";
    },
    (row) => {
      row.map_evidence.rendered_map_feature_or_marker_records[0].geometry_type = "Polygon";
    },
  ];
  for (const mutate of mutations) {
    const report = completeReport(protocol);
    const row = report.surface_rows.find(
      (item) => item.state_id === "live" && item.viewport_id === "desktop",
    );
    mutate(row);
    assert.match(
      validateReportStructure(report, protocol).join("\n"),
      /map detail integrity mismatch/,
    );
  }

  const placementReport = completeReport(protocol);
  const placementRow = placementReport.surface_rows.find(
    (item) => item.state_id === "live" && item.viewport_id === "desktop",
  );
  placementRow.map_evidence.rendered_map_feature_or_marker_records[1]
    .observed_center_css_px = { x: 0, y: 0 };
  assert.match(
    validateReportStructure(placementReport, protocol).join("\n"),
    /map marker placement derivation mismatch/,
  );
});

test("canonical request roster is authoritative and failed requests gate false", async () => {
  const protocol = await loadProtocol(protocolPath);
  const mutated = completeReport(protocol);
  mutated.surface_rows[0].runtime.request_derived.request_origins = [];
  assert.match(
    validateReportStructure(mutated, protocol).join("\n"),
    /request derivation mismatch/,
  );

  const failed = completeReport(protocol);
  const row = failed.surface_rows[0];
  row.runtime.request_events[0].response_status = null;
  row.runtime.request_events[0].failure = "net::ERR_FAILED";
  row.runtime.request_derived = deriveRequestEvidence(
    row.runtime.request_events,
    protocol.surface_thresholds,
  );
  row.checks.no_unallowlisted_failed_requests = false;
  row.qualified = false;
  assert.equal(row.runtime.request_derived.unallowlisted_failed_requests.length, 1);
  assert.deepEqual(validateReportStructure(failed, protocol), []);
});

test("axe retains all impacts and binds its installed engine version", async () => {
  const protocol = await loadProtocol(protocolPath);
  const report = completeReport(protocol);
  const row = report.surface_rows[0];
  row.axe.findings.push({
    id: "fixture-moderate",
    impact: "moderate",
    tags: ["wcag2aa"],
    help: "Fixture finding",
    help_url: "https://example.test/axe",
    nodes: [{ target: ["main"], failure_summary: "Fixture only" }],
  });
  row.axe.finding_count = 1;
  row.axe.impact_counts.moderate = 1;
  row.checks.axe_wcag_a_aa_findings_within_limit = false;
  row.qualified = false;
  assert.deepEqual(validateReportStructure(report, protocol), []);

  row.axe.finding_count = 0;
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /axe finding derivation mismatch/,
  );
  row.axe.finding_count = 1;
  row.axe.engine_version = "0.0.0";
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /axe engine evidence mismatch/,
  );
});

test("privacy evidence detects request-body and persistence-token leakage", async () => {
  const protocol = await loadProtocol(protocolPath);
  const stale = completeReport(protocol);
  const staleJourney = stale.functional_journeys.find(
    (journey) => journey.id === "location_privacy_boundary",
  );
  staleJourney.evidence.api_request_roster[0].body.unexpected = "fixture-only";
  assert.match(
    validateReportStructure(stale, protocol).join("\n"),
    /privacy journey derivation mismatch/,
  );

  const truthful = completeReport(protocol);
  const journey = truthful.functional_journeys.find(
    (item) => item.id === "location_privacy_boundary",
  );
  journey.evidence.browser_surfaces.local_storage.push({
    key: "fixture-location",
    key_token_matches: [],
    value_length: 5,
    value_token_matches: ["49.28"],
  });
  journey.evidence.derived = derivePrivacyEvidence(journey.evidence, protocol);
  for (const check of protocol.functional_journeys.find(
    (item) => item.id === "location_privacy_boundary",
  ).required_checks) {
    journey.checks[check] = journey.evidence.derived[check];
  }
  journey.qualified = false;
  assert.equal(
    journey.evidence.derived.both_coordinate_tokens_absent_outside_allowed_request,
    false,
  );
  assert.deepEqual(validateReportStructure(truthful, protocol), []);
});

test("non-map states require typed not_applicable evidence", async () => {
  const protocol = await loadProtocol(protocolPath);
  const report = completeReport(protocol);
  const idleRow = report.surface_rows.find(
    (row) => row.state_id === "idle" && row.viewport_id === "mobile",
  );
  idleRow.map_evidence.map_list_parity = true;
  assert.match(
    validateReportStructure(report, protocol).join("\n"),
    /invalid not-applicable map evidence/,
  );
});

test("p75 uses the frozen nearest-rank rule and ignores non-finite values", () => {
  assert.equal(p75NearestRank([7, 1, 2, 6, 3, 5, 4]), 6);
  assert.equal(p75NearestRank([1, 2, Number.NaN, Number.POSITIVE_INFINITY, 3]), 3);
  assert.equal(p75NearestRank([]), null);
});

test("expected mocked HTTP failures do not hide unrelated console defects", () => {
  const expectedFailure = {
    url: "http://127.0.0.1:4175/api/v1/ask",
    status: 503,
    question: "surface:unavailable",
  };
  const expectedResourceLine = {
    text: "Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
    location: { url: expectedFailure.url, lineNumber: 0, columnNumber: 0 },
  };
  const unexpectedApplicationError = {
    text: "Uncaught TypeError: failed to render recovery state",
    location: { url: "http://127.0.0.1:4175/assets/index.js", lineNumber: 4 },
  };
  const unrelatedHttpError = {
    text: "Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
    location: { url: "http://127.0.0.1:4175/api/unrelated", lineNumber: 0 },
  };
  const blankLocationError = {
    text: "Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
    location: { url: "", lineNumber: 0 },
  };
  const result = classifyConsoleErrors(
    [
      expectedResourceLine,
      unrelatedHttpError,
      blankLocationError,
      unexpectedApplicationError,
    ],
    [expectedFailure],
  );

  assert.equal(result.expectedConsoleErrors.length, 1);
  assert.deepEqual(result.expectedConsoleErrors[0].expected_http_failure, expectedFailure);
  assert.deepEqual(
    result.unexpectedConsoleErrors,
    [unrelatedHttpError, blankLocationError, unexpectedApplicationError],
  );
  assert.equal(classifyConsoleErrors(
    [blankLocationError],
    [{ ...expectedFailure, url: "" }],
  ).expectedConsoleErrors.length, 0);
});

test("package exposes build-preview qualification and focused tests", async () => {
  const packageJson = JSON.parse(
    await readFile(path.join(frontendRoot, "package.json"), "utf8"),
  );
  assert.equal(
    packageJson.scripts["qualify:surface"],
    "npm run build && node scripts/qualify-frontend-surface.mjs",
  );
  assert.equal(
    packageJson.scripts["test:surface"],
    "node --test tests/frontend-surface-runner.test.mjs",
  );
  assert.equal(packageJson.devDependencies["axe-core"], "^4.12.1");
});
