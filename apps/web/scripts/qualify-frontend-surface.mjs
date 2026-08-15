#!/usr/bin/env node

import { chromium } from "@playwright/test";
import sharp from "sharp";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdir,
  readFile,
  rename,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendRoot, "../..");
const defaultProtocolPath = path.join(
  repositoryRoot,
  "data/evaluation/frontend_surface.v1.yaml",
);
const defaultOutputDirectory = path.join(
  repositoryRoot,
  "output/benchmark/frontend_surface",
);
const defaultBaseUrl = "http://127.0.0.1:4175";
const axePath = path.join(frontendRoot, "node_modules/axe-core/axe.min.js");
const installedAxeCoreVersion = JSON.parse(await readFile(
  path.join(frontendRoot, "node_modules/axe-core/package.json"),
  "utf8",
)).version;
const requiredMapParityStateIds = [
  "live",
  "mixed",
  "stale",
  "no_result",
  "partial_layer",
];

const transparentPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

const groundedResponse = {
  status: "answer",
  response_mode: "grounded",
  trace_id: "surface-grounded",
  answer: "Prepare water, food, and medication.",
  suggested_questions: ["How often should I update my emergency kit?"],
  claims: [
    {
      claim_id: "C1",
      text: "Prepare water, food, and medication.",
      evidence_status: "verified_corpus",
      supports: [{ evidence_id: "E1", quote: "Food & water" }],
    },
  ],
  evidence: [
    {
      evidence_id: "E1",
      title: "Wildfire Preparedness Guide",
      publisher: "PreparedBC",
      canonical_url: "https://example.test/guide.pdf",
      locator: "PDF page 5",
      temporal_class: "stable_guidance",
      review_provenance: "human_verified_repair",
      primary_text: "Food & water",
      context_text: "A grab-and-go bag includes Food & water and other supplies.",
    },
  ],
  limitations: ["Stable guidance only."],
  validation: {
    accepted: true,
    schema_valid: true,
    citation_ids_valid: true,
    quotes_exact: true,
    policy_valid: true,
    errors: [],
  },
};

const liveResult = {
  result_id: "incident:surface-7",
  kind: "incident",
  authority: "BC Wildfire Service",
  source_url: "https://example.test/incidents/surface-7",
  source_updated_at: "2026-08-06T11:55:00Z",
  retrieved_at: "2026-08-06T12:00:00Z",
  freshness: "fresh",
  status: "Out of Control",
  name: "Surface Test Fire",
  geometry_relation: "nearby",
  geometry: { type: "Point", coordinates: [-123.12, 49.28] },
};

const tenRecordCoordinates = [
  [-123.12, 49.28],
  [-120.33, 50.67],
  [-122.75, 53.91],
  [-119.49, 55.76],
  [-128.60, 54.52],
  [-135.05, 59.90],
  [-115.78, 49.51],
  [-126.85, 49.15],
  [-117.30, 49.49],
  [-121.50, 58.50],
];

const liveResultsTen = Array.from({ length: 10 }, (_, index) => {
  const ordinal = String(index + 1).padStart(2, "0");
  return {
    ...liveResult,
    result_id: `incident:surface-${ordinal}`,
    source_url: `https://example.test/incidents/surface-${ordinal}`,
    name: `Surface Test Fire ${ordinal}`,
    geometry: {
      type: "Point",
      coordinates: tenRecordCoordinates[index],
    },
  };
});

const responseFixtures = {
  "surface:grounded": groundedResponse,
  "surface:partial": {
    ...groundedResponse,
    response_mode: "partial",
    trace_id: "surface-partial",
    answer: "Prepare water and food; medication guidance could not be fully verified.",
    limitations: ["Medication details were not supported by the selected passage."],
  },
  "surface:background": {
    status: "answer",
    response_mode: "background",
    trace_id: "surface-background",
    answer: "Embers can travel ahead of a wildfire front.",
    suggested_questions: [],
    claims: [
      {
        claim_id: "C1",
        text: "Embers can travel ahead of a wildfire front.",
        evidence_status: "general_background",
        supports: [],
      },
    ],
    evidence: [],
    limitations: ["General background — not verified against the FireLens corpus."],
  },
  "surface:capability": {
    status: "answer",
    response_mode: "capability",
    trace_id: "surface-capability",
    answer: "I can help you explore reviewed wildfire preparedness guidance.",
    suggested_questions: ["What belongs in a grab-and-go bag?"],
    claims: [],
    evidence: [],
    limitations: [],
  },
  "surface:scope": {
    status: "answer",
    response_mode: "scope_redirect",
    trace_id: "surface-scope",
    answer: "That request is outside the FireLens guidance collection.",
    suggested_questions: ["What can FireLens help me understand?"],
    claims: [],
    evidence: [],
    limitations: [],
  },
  "surface:requires-location": {
    status: "answer",
    response_mode: "requires_input",
    trace_id: "surface-requires-location",
    answer: "Share an approximate location or enter a BC community to continue.",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: [],
    required_input: {
      kind: "location",
      prompt: "Use approximate location or enter a BC community.",
      continuation_question: "surface:live-fresh",
    },
    selected_live_result_id: "incident:surface-7",
  },
  "surface:abstention": {
    status: "abstention",
    response_mode: "abstention",
    trace_id: "surface-abstention",
    answer: null,
    reason_code: "requires_current_official_information",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: ["Use the official BC Wildfire Service map for emergency direction."],
  },
  "surface:live-fresh": {
    status: "answer",
    response_mode: "live",
    trace_id: "surface-live-fresh",
    answer: "Current official information: Surface Test Fire is Out of Control.",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: ["No matching record is not a safety determination."],
    aggregate_freshness: "fresh",
    live_results: liveResultsTen,
    unavailable_layers: [],
  },
  "surface:live-stale": {
    status: "answer",
    response_mode: "live",
    trace_id: "surface-live-stale",
    answer: "Cached official information (refresh failed): Surface Test Fire.",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: ["A refresh failed; this cached record is visibly stale."],
    aggregate_freshness: "stale",
    live_results: [{ ...liveResult, freshness: "stale" }],
    unavailable_layers: ["evacuation"],
  },
  "surface:mixed": {
    ...groundedResponse,
    response_mode: "mixed",
    trace_id: "surface-mixed",
    answer: "Surface Test Fire is active; keep your reviewed grab-and-go guidance ready.",
    aggregate_freshness: "fresh",
    live_results: [liveResult],
    unavailable_layers: [],
  },
  "surface:no-result": {
    status: "abstention",
    response_mode: "abstention",
    trace_id: "surface-no-result",
    answer: null,
    reason_code: "no_matching_official_records",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: ["No matching record is not a safety determination."],
  },
  "surface:partial-layer": {
    status: "answer",
    response_mode: "live",
    trace_id: "surface-partial-layer",
    answer: "Available incident records are shown; the evacuation layer is unavailable.",
    suggested_questions: [],
    claims: [],
    evidence: [],
    limitations: ["The missing evacuation layer is not represented below."],
    aggregate_freshness: "fresh",
    live_results: [liveResult],
    unavailable_layers: ["evacuation"],
  },
};

function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) return value.map((item) => stableJson(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stableJson(value[key])]),
    );
  }
  return value;
}

function stableJsonString(value) {
  return JSON.stringify(stableJson(value));
}

export function canonicalApiRequestRecord({
  sequenceIndex,
  method,
  url,
  resourceType,
  body,
  responseStatus,
}) {
  const canonicalBody = stableJson(body);
  const canonicalUrl = canonicalHttpUrl(url);
  return {
    sequence_index: sequenceIndex,
    method: method.toUpperCase(),
    url: canonicalUrl,
    origin: requestOrigin(canonicalUrl),
    resource_type: resourceType,
    body: canonicalBody,
    body_sha256: sha256Bytes(Buffer.from(stableJsonString(canonicalBody), "utf8")),
    response_status: responseStatus,
  };
}

async function fileSha256(file) {
  return sha256Bytes(await readFile(file));
}

function strictObject(value, context) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${context} must be an object`);
  }
  return value;
}

export async function loadProtocol(protocolPath = defaultProtocolPath) {
  const raw = await readFile(protocolPath, "utf8");
  let protocol;
  try {
    // JSON is a strict subset of YAML. Keeping the frozen protocol JSON-compatible
    // avoids an unfrozen parser dependency in the qualification path.
    protocol = JSON.parse(raw);
  } catch (error) {
    throw new Error(`frontend surface protocol must be JSON-compatible YAML: ${error}`);
  }
  strictObject(protocol, "frontend surface protocol");
  if (protocol.schema_version !== "firelens.frontend_surface_protocol.v1") {
    throw new Error("unsupported frontend surface protocol schema");
  }
  if (typeof protocol.protocol_id !== "string" || !protocol.protocol_id) {
    throw new Error("frontend surface protocol requires protocol_id");
  }
  if (!["provisional", "ratified"].includes(protocol.status)) {
    throw new Error("frontend surface protocol requires provisional or ratified status");
  }
  if (
    (protocol.status === "ratified" && typeof protocol.frozen_at !== "string")
    || (protocol.status === "provisional" && protocol.frozen_at !== null)
  ) {
    throw new Error("frontend surface protocol status and frozen_at disagree");
  }
  if (!Array.isArray(protocol.states) || protocol.states.length !== 12) {
    throw new Error("frontend surface protocol requires exactly 12 states");
  }
  if (!Array.isArray(protocol.viewports) || protocol.viewports.length !== 3) {
    throw new Error("frontend surface protocol requires exactly 3 viewports");
  }
  const stateIds = protocol.states.map((item) => item.id);
  const viewportIds = protocol.viewports.map((item) => item.id);
  if (new Set(stateIds).size !== stateIds.length) {
    throw new Error("frontend surface state IDs must be unique");
  }
  if (new Set(viewportIds).size !== viewportIds.length) {
    throw new Error("frontend surface viewport IDs must be unique");
  }
  const requiredStateIds = [
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
  ];
  if (JSON.stringify(stateIds) !== JSON.stringify(requiredStateIds)) {
    throw new Error("frontend surface protocol has the wrong safety-critical state roster");
  }
  if (JSON.stringify(viewportIds) !== JSON.stringify(["mobile", "tablet", "desktop"])) {
    throw new Error("frontend surface protocol has the wrong viewport roster");
  }
  const executionEnvironment = strictObject(
    protocol.execution_environment,
    "execution environment protocol",
  );
  const requiredExecutionEnvironment = {
    locale: "en-CA",
    timezone_id: "America/Vancouver",
    color_scheme: "light",
    reduced_motion: "reduce",
    browser_name: "chromium",
    headless: true,
  };
  if (JSON.stringify(executionEnvironment) !== JSON.stringify(requiredExecutionEnvironment)) {
    throw new Error("frontend surface execution environment is not the frozen profile");
  }
  const mapParity = strictObject(protocol.map_parity, "map parity protocol");
  if (
    JSON.stringify(mapParity.applicable_state_ids)
      !== JSON.stringify(requiredMapParityStateIds)
    || mapParity.pagination_mode !== "none"
    || mapParity.response_complete_roster !== true
    || mapParity.allow_rendered_roster_truncation !== false
  ) {
    throw new Error("frontend surface map parity protocol is inconsistent");
  }
  if (
    protocol.surface_thresholds?.axe_wcag_a_aa_findings_max !== 0
    || !Array.isArray(protocol.surface_thresholds?.allowed_failed_request_urls)
    || protocol.surface_thresholds.allowed_failed_request_urls.some(
      (url) => canonicalHttpUrl(url) !== url,
    )
  ) {
    throw new Error("frontend surface request or axe threshold protocol is inconsistent");
  }
  const privacyEvidence = strictObject(protocol.privacy_evidence, "privacy evidence protocol");
  if (
    canonicalHttpUrl(privacyEvidence.request_url) !== privacyEvidence.request_url
    || JSON.stringify(privacyEvidence.expected_questions)
      !== JSON.stringify(["surface:requires-location", "surface:live-fresh"])
    || JSON.stringify(privacyEvidence.allowed_body_keys)
      !== JSON.stringify(["context", "history", "location", "question"])
    || JSON.stringify(privacyEvidence.persistence_probe_tokens)
      !== JSON.stringify(["49.282729", "-123.120738", "49.28", "-123.12"])
    || privacyEvidence.fixture_location?.rounded_latitude !== 49.28
    || privacyEvidence.fixture_location?.rounded_longitude !== -123.12
    || privacyEvidence.fixture_location?.radius_km !== 50
  ) {
    throw new Error("frontend surface privacy evidence protocol is inconsistent");
  }
  const fixtureIds = new Set(["idle", "loading", "provider_failure", ...Object.keys(responseFixtures).map(
    (question) => protocol.states.find((state) => state.question === question)?.id,
  )]);
  if (stateIds.some((stateId) => !fixtureIds.has(stateId))) {
    throw new Error("frontend surface protocol contains a state without a deterministic fixture");
  }
  if (
    protocol.matrix?.expected_rows !== stateIds.length * viewportIds.length
    || protocol.matrix?.require_every_state_viewport_pair_once !== true
  ) {
    throw new Error("frontend surface matrix declaration is inconsistent");
  }
  if (!Array.isArray(protocol.functional_journeys) || protocol.functional_journeys.length < 2) {
    throw new Error("frontend surface protocol requires frozen functional journeys");
  }
  const performance = strictObject(protocol.performance, "performance protocol");
  if (performance.warmup_samples !== 1 || performance.cold_samples !== 7) {
    throw new Error("performance protocol requires 1 warmup and 7 cold samples");
  }
  if (
    !Array.isArray(performance.profiles)
    || performance.profiles.length !== 2
    || !performance.profiles.includes("mobile")
    || !performance.profiles.includes("desktop")
  ) {
    throw new Error("performance protocol requires mobile and desktop profiles");
  }
  return protocol;
}

function parseArguments(argv) {
  const options = {
    protocolPath: defaultProtocolPath,
    outputDirectory: defaultOutputDirectory,
    baseUrl: defaultBaseUrl,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const option = argv[index];
    const value = argv[index + 1];
    if (option === "--protocol" && value) {
      options.protocolPath = path.resolve(value);
      index += 1;
    } else if (option === "--output-dir" && value) {
      options.outputDirectory = path.resolve(value);
      index += 1;
    } else if (option === "--base-url" && value) {
      options.baseUrl = value.replace(/\/$/, "");
      index += 1;
    } else {
      throw new Error(`unknown or incomplete option: ${option}`);
    }
  }
  const parsed = new URL(options.baseUrl);
  if (parsed.protocol !== "http:" || parsed.hostname !== "127.0.0.1") {
    throw new Error("frontend surface preview must bind to local 127.0.0.1 HTTP");
  }
  return options;
}

function browserContextConfiguration(protocol, viewport) {
  return {
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.device_scale_factor,
    isMobile: viewport.is_mobile,
    locale: protocol.execution_environment.locale,
    timezoneId: protocol.execution_environment.timezone_id,
    colorScheme: protocol.execution_environment.color_scheme,
    reducedMotion: protocol.execution_environment.reduced_motion,
  };
}

export function canonicalRequestUrl(value) {
  if (typeof value !== "string" || value.trim() === "") return null;
  try {
    const parsed = new URL(value);
    parsed.hash = "";
    const entries = [...parsed.searchParams.entries()].sort(
      ([leftKey, leftValue], [rightKey, rightValue]) => (
        leftKey.localeCompare(rightKey) || leftValue.localeCompare(rightValue)
      ),
    );
    parsed.search = "";
    for (const [key, entryValue] of entries) parsed.searchParams.append(key, entryValue);
    return parsed.href;
  } catch {
    return null;
  }
}

function canonicalHttpUrl(value) {
  const canonical = canonicalRequestUrl(value);
  if (!canonical) return null;
  const parsed = new URL(canonical);
  return ["http:", "https:"].includes(parsed.protocol) ? canonical : null;
}

function requestOrigin(url) {
  const canonical = canonicalRequestUrl(url);
  if (!canonical) return null;
  const parsed = new URL(canonical);
  return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : null;
}

function fixtureForQuestion(question) {
  if (question === "surface:unavailable") {
    return {
      statusCode: 503,
      body: {
        trace_id: "surface-unavailable",
        error_kind: "unavailable",
        message: "The required OpenRouter service is unavailable.",
        retryable: true,
      },
    };
  }
  const body = responseFixtures[question] ?? groundedResponse;
  return { statusCode: 200, body };
}

async function installDeterministicRoutes(page) {
  const requestBodies = [];
  const apiRequestRecords = [];
  const expectedHttpFailures = [];
  let releaseLoading;
  const loadingGate = new Promise((resolve) => {
    releaseLoading = resolve;
  });
  await page.route("https://*.tile.openstreetmap.org/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/png", body: transparentPng });
  });
  await page.route("**/api/v1/live/map*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-08-06T12:00:00Z",
        results: [],
        aggregate_freshness: "fresh",
        unavailable_layers: [],
        layer_statuses: [],
        limitations: ["No matching record is not a safety determination."],
      }),
    });
  });
  await page.route("**/api/v1/ask", async (route) => {
    let body = {};
    try {
      body = route.request().postDataJSON();
    } catch {
      body = {};
    }
    requestBodies.push(body);
    const question = String(body.question ?? "");
    if (question === "surface:loading") {
      await loadingGate;
    }
    const fixture = fixtureForQuestion(question);
    const requestUrl = canonicalHttpUrl(route.request().url());
    apiRequestRecords.push(canonicalApiRequestRecord({
      sequenceIndex: apiRequestRecords.length,
      method: route.request().method(),
      url: requestUrl,
      resourceType: route.request().resourceType(),
      body,
      responseStatus: fixture.statusCode,
    }));
    if (fixture.statusCode >= 400) {
      expectedHttpFailures.push({
        url: canonicalHttpUrl(route.request().url()),
        status: fixture.statusCode,
        question,
      });
    }
    await route.fulfill({
      status: fixture.statusCode,
      contentType: "application/json",
      body: JSON.stringify(fixture.body),
    });
  });
  return {
    requestBodies,
    apiRequestRecords,
    expectedHttpFailures,
    releaseLoading: () => releaseLoading(),
  };
}

async function waitForText(page, text) {
  await page.getByText(text, { exact: true }).first().waitFor({ state: "visible" });
}

async function driveState(page, state) {
  await page.goto("/", { waitUntil: "networkidle" });
  if (state.question) {
    await page.getByLabel("Ask FireLens a question").fill(state.question);
    await page.getByLabel("Ask FireLens a question").press("Enter");
  }
  await waitForText(page, state.ready_text);
  if (["live", "mixed", "stale", "partial_layer"].includes(state.id)) {
    await page.getByRole("region", { name: "Official wildfire records map" }).waitFor();
    await page.locator(".leaflet-container").waitFor();
  }
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
  });
}

function expectedMapResponseRecords(state) {
  if (!requiredMapParityStateIds.includes(state.id)) return [];
  const fixture = state.question ? fixtureForQuestion(state.question) : null;
  const records = fixture?.body?.live_results;
  return Array.isArray(records) ? records : [];
}

export function expectedMapResponseRecordIds(state) {
  return expectedMapResponseRecords(state).map((record) => record.result_id);
}

export function expectedMapResponseDetails(state) {
  return expectedMapResponseRecords(state).map((record) => ({
    result_id: record.result_id,
    name: record.name,
    source_url: canonicalHttpUrl(record.source_url),
    geometry_type: record.geometry?.type ?? null,
  }));
}

function sameExactRoster(expected, rendered) {
  if (!Array.isArray(expected) || !Array.isArray(rendered)) return false;
  if (expected.length !== rendered.length) return false;
  if (new Set(expected).size !== expected.length) return false;
  if (new Set(rendered).size !== rendered.length) return false;
  const sortedExpected = [...expected].sort();
  const sortedRendered = [...rendered].sort();
  return sortedExpected.every((id, index) => id === sortedRendered[index]);
}

function contiguousDomIndices(rows) {
  return rows.every((row, index) => row.dom_index === index);
}

function exactPartition(details, ids, unresolved) {
  const resolvedIds = details
    .filter((row) => row.record_id !== null)
    .map((row) => row.record_id);
  const unresolvedRows = details.filter((row) => row.record_id === null);
  return (
    JSON.stringify(resolvedIds) === JSON.stringify(ids)
    && JSON.stringify(unresolvedRows) === JSON.stringify(unresolved)
    && details.length === ids.length + unresolved.length
    && contiguousDomIndices(details)
  );
}

function recomputeMapDetailIntegrity(mapEvidence, expectedRecords) {
  if (mapEvidence?.applicability !== "applicable") return null;
  const expectedById = new Map(expectedRecords.map((record) => [record.result_id, record]));
  const listDetails = mapEvidence.rendered_accessible_list_records ?? [];
  const mapDetails = mapEvidence.rendered_map_feature_or_marker_records ?? [];
  const listCanonical = listDetails.every((detail) => {
    if (detail.record_id === null) return detail.resolution !== "unique_name_and_source";
    const expected = expectedById.get(detail.record_id);
    return (
      expected
      && detail.rendered_name === expected.name
      && detail.rendered_source_url === canonicalHttpUrl(expected.source_url)
      && detail.geometry_type === expected.geometry?.type
      && detail.resolution === "unique_name_and_source"
    );
  });
  const mapCanonical = mapDetails.every((detail) => {
    if (detail.record_id === null) return detail.resolution !== "unique_popup_name";
    const expected = expectedById.get(detail.record_id);
    return (
      expected
      && detail.rendered_popup_name === expected.name
      && detail.canonical_source_url === canonicalHttpUrl(expected.source_url)
      && detail.source_url_observed_in_popup === false
      && detail.geometry_type === expected.geometry?.type
      && detail.resolution === "unique_popup_name"
    );
  });
  return (
    exactPartition(
      listDetails,
      mapEvidence.rendered_accessible_list_record_ids ?? [],
      mapEvidence.unresolved_accessible_list_entries ?? [],
    )
    && exactPartition(
      mapDetails,
      mapEvidence.rendered_map_feature_or_marker_record_ids ?? [],
      mapEvidence.unresolved_map_feature_or_marker_entries ?? [],
    )
    && listCanonical
    && mapCanonical
  );
}

function recomputeMarkerPlacementSanity(mapEvidence) {
  if (mapEvidence?.applicability !== "applicable") return null;
  const details = mapEvidence.rendered_map_feature_or_marker_records ?? [];
  const visibleResolved = details.filter((detail) => (
    detail.record_id !== null
    && detail.observed_visible === true
    && Number.isFinite(detail.observed_center_css_px?.x)
    && Number.isFinite(detail.observed_center_css_px?.y)
  ));
  const uniqueCenters = new Set(visibleResolved.map(
    (detail) => `${detail.observed_center_css_px.x}:${detail.observed_center_css_px.y}`,
  ));
  const expectedCount = mapEvidence.rendered_map_feature_or_marker_record_ids?.length ?? 0;
  return {
    scope: "css_pixel_center_uniqueness_only_not_geospatial_accuracy",
    observed_visible_marker_count: visibleResolved.length,
    observed_unique_visible_center_count: uniqueCenters.size,
    expected_rendered_marker_count: expectedCount,
    sanity_passed: (
      visibleResolved.length === expectedCount
      && uniqueCenters.size === expectedCount
    ),
  };
}

export function recomputeMapListParity(mapEvidence) {
  if (mapEvidence?.applicability !== "applicable") return null;
  const pagination = mapEvidence.pagination;
  return (
    mapEvidence.collection_status === "complete"
    && pagination?.mode === "none"
    && pagination?.response_complete_roster === true
    && pagination?.rendered_complete_roster_required === true
    && pagination?.expected_total_records
      === mapEvidence.expected_response_record_ids?.length
    && (
      pagination?.map_surface_required !== true
      || mapEvidence.map_surface_present === true
    )
    && sameExactRoster(
      mapEvidence.expected_response_record_ids,
      mapEvidence.rendered_accessible_list_record_ids,
    )
    && sameExactRoster(
      mapEvidence.expected_response_record_ids,
      mapEvidence.rendered_map_feature_or_marker_record_ids,
    )
    && mapEvidence.unresolved_accessible_list_entries?.length === 0
    && mapEvidence.unresolved_map_feature_or_marker_entries?.length === 0
  );
}

function notApplicableMapEvidence() {
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

function initialApplicableMapEvidence(state, protocol) {
  const expectedIds = expectedMapResponseRecordIds(state);
  return {
    applicability: "applicable",
    reason: null,
    collection_status: "not_executed",
    pagination: {
      mode: protocol.map_parity.pagination_mode,
      response_complete_roster: protocol.map_parity.response_complete_roster,
      rendered_complete_roster_required:
        protocol.map_parity.allow_rendered_roster_truncation === false,
      map_surface_required: expectedIds.length > 0,
      expected_total_records: expectedIds.length,
    },
    map_surface_present: false,
    expected_response_record_ids: expectedIds,
    rendered_accessible_list_record_ids: [],
    rendered_map_feature_or_marker_record_ids: [],
    rendered_accessible_list_records: [],
    rendered_map_feature_or_marker_records: [],
    unresolved_accessible_list_entries: [],
    unresolved_map_feature_or_marker_entries: [],
    detail_integrity: false,
    marker_placement_sanity: {
      scope: "css_pixel_center_uniqueness_only_not_geospatial_accuracy",
      observed_visible_marker_count: 0,
      observed_unique_visible_center_count: 0,
      expected_rendered_marker_count: 0,
      sanity_passed: false,
    },
    map_list_parity: false,
  };
}

function resolveUniqueRecord(records, { name, sourceUrl = null }) {
  const candidates = records.filter((record) => (
    record.name === name
    && (
      sourceUrl === null
      || canonicalHttpUrl(record.source_url) === canonicalHttpUrl(sourceUrl)
    )
  ));
  return candidates.length === 1 ? candidates[0] : null;
}

async function inspectMapEvidence(page, state, protocol) {
  if (!protocol.map_parity.applicable_state_ids.includes(state.id)) {
    return notApplicableMapEvidence();
  }
  const evidence = initialApplicableMapEvidence(state, protocol);
  const expectedRecords = expectedMapResponseRecords(state);
  const mapSurface = page.getByRole("region", { name: "Official wildfire records map" });
  evidence.map_surface_present = await mapSurface.count() === 1;

  if (evidence.map_surface_present) {
    const listItems = mapSurface.locator("ul.live-list > li");
    for (let index = 0; index < await listItems.count(); index += 1) {
      const item = listItems.nth(index);
      const name = (await item.locator("strong").first().innerText()).trim();
      const sourceUrl = await item.locator("a[href]").first().getAttribute("href");
      const record = resolveUniqueRecord(expectedRecords, { name, sourceUrl });
      const rendered = {
        dom_index: index,
        rendered_name: name,
        rendered_source_url: canonicalHttpUrl(sourceUrl),
        record_id: record?.result_id ?? null,
        geometry_type: record?.geometry?.type ?? null,
        resolution: record ? "unique_name_and_source" : "unresolved",
      };
      evidence.rendered_accessible_list_records.push(rendered);
      if (record) evidence.rendered_accessible_list_record_ids.push(record.result_id);
      else evidence.unresolved_accessible_list_entries.push(rendered);
    }

    const mapElements = mapSurface.locator(
      ".leaflet-overlay-pane .leaflet-interactive",
    );
    const mapElementCount = await mapElements.count();
    for (let index = 0; index < mapElementCount; index += 1) {
      const element = mapElements.nth(index);
      try {
        await element.evaluate((node) => {
          node.dispatchEvent(new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
            view: window,
          }));
        });
        const popup = mapSurface.locator(".leaflet-popup-content").last();
        await popup.waitFor({ state: "visible", timeout: 2_000 });
        const name = (await popup.locator("strong").first().innerText()).trim();
        const record = resolveUniqueRecord(expectedRecords, { name });
        const bounds = await element.boundingBox();
        const observedCenter = bounds ? {
          x: Number((bounds.x + (bounds.width / 2)).toFixed(3)),
          y: Number((bounds.y + (bounds.height / 2)).toFixed(3)),
        } : null;
        const rendered = {
          dom_index: index,
          rendered_popup_name: name,
          element_tag: await element.evaluate((node) => node.tagName.toLowerCase()),
          record_id: record?.result_id ?? null,
          geometry_type: record?.geometry?.type ?? null,
          canonical_source_url: record ? canonicalHttpUrl(record.source_url) : null,
          source_url_observed_in_popup: false,
          observed_visible: await element.isVisible(),
          observed_center_css_px: observedCenter,
          resolution: record ? "unique_popup_name" : "unresolved",
        };
        evidence.rendered_map_feature_or_marker_records.push(rendered);
        if (record) {
          evidence.rendered_map_feature_or_marker_record_ids.push(record.result_id);
        } else {
          evidence.unresolved_map_feature_or_marker_entries.push(rendered);
        }
      } catch (error) {
        const unresolved = {
          dom_index: index,
          rendered_popup_name: null,
          element_tag: await element.evaluate((node) => node.tagName.toLowerCase()),
          record_id: null,
          geometry_type: null,
          canonical_source_url: null,
          source_url_observed_in_popup: false,
          observed_visible: false,
          observed_center_css_px: null,
          resolution: "interaction_error",
          error: String(error?.message ?? error),
        };
        evidence.rendered_map_feature_or_marker_records.push(unresolved);
        evidence.unresolved_map_feature_or_marker_entries.push(unresolved);
      } finally {
        await mapSurface.locator(".leaflet-popup-close-button").evaluateAll((buttons) => {
          for (const button of buttons) button.click();
        });
        await page.waitForFunction(
          () => document.querySelectorAll(".leaflet-popup").length === 0,
          undefined,
          { timeout: 2_000 },
        ).catch(() => {});
      }
    }
  }
  evidence.collection_status = "complete";
  evidence.detail_integrity = recomputeMapDetailIntegrity(evidence, expectedRecords);
  evidence.marker_placement_sanity = recomputeMarkerPlacementSanity(evidence);
  evidence.map_list_parity = recomputeMapListParity(evidence);
  return evidence;
}

async function runAxe(page) {
  await page.addScriptTag({ path: axePath });
  const result = await page.evaluate(async () => {
    return window.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
      },
      resultTypes: ["violations"],
    });
  });
  const findings = result.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    tags: [...violation.tags].sort(),
    help: violation.help,
    help_url: violation.helpUrl,
    nodes: violation.nodes.map((node) => ({
      target: node.target,
      failure_summary: node.failureSummary,
    })),
  }));
  const impactCounts = {
    critical: 0,
    serious: 0,
    moderate: 0,
    minor: 0,
    unknown: 0,
  };
  for (const finding of findings) {
    const bucket = Object.hasOwn(impactCounts, finding.impact)
      ? finding.impact
      : "unknown";
    impactCounts[bucket] += 1;
  }
  return {
    engine_version: result.testEngine.version,
    installed_package_version: installedAxeCoreVersion,
    engine_version_matches_installed_package:
      result.testEngine.version === installedAxeCoreVersion,
    finding_count: findings.length,
    impact_counts: impactCounts,
    findings,
  };
}

async function inspectLayoutAndCss(page, thresholds) {
  return page.evaluate((limits) => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none"
        && style.visibility !== "hidden"
        && Number.parseFloat(style.opacity || "1") > 0
        && rect.width > 0
        && rect.height > 0
      );
    };
    const clippedTextElements = [];
    const undersizedTextElements = [];
    for (const element of document.querySelectorAll("body *")) {
      if (!(element instanceof HTMLElement) || !visible(element)) continue;
      const directText = [...element.childNodes]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent?.trim() ?? "")
        .join(" ")
        .trim();
      if (!directText) continue;
      const style = getComputedStyle(element);
      const secondary = (
        element.matches("small, .panel-label, .assistant-name, .selected-kicker")
        || element.closest("small") !== null
      );
      const requiredFontSize = secondary
        ? limits.minimumSecondaryText
        : limits.minimumBodyText;
      const observedFontSize = Number.parseFloat(style.fontSize);
      if (Number.isFinite(observedFontSize) && observedFontSize < requiredFontSize) {
        undersizedTextElements.push({
          tag: element.tagName.toLowerCase(),
          class_name: element.className || null,
          font_size_px: observedFontSize,
          required_font_size_px: requiredFontSize,
          category: secondary ? "secondary" : "body",
        });
      }
      const clipsX = ["hidden", "clip"].includes(style.overflowX)
        && element.scrollWidth > element.clientWidth + 1;
      const clipsY = ["hidden", "clip"].includes(style.overflowY)
        && element.scrollHeight > element.clientHeight + 1;
      if (clipsX || clipsY) {
        clippedTextElements.push({
          tag: element.tagName.toLowerCase(),
          class_name: element.className || null,
          overflow_x: style.overflowX,
          overflow_y: style.overflowY,
          clipped_x_px: Math.max(0, element.scrollWidth - element.clientWidth),
          clipped_y_px: Math.max(0, element.scrollHeight - element.clientHeight),
        });
      }
    }
    const inaccessibleStylesheets = [];
    let cssRuleCount = 0;
    for (const stylesheet of document.styleSheets) {
      try {
        cssRuleCount += stylesheet.cssRules.length;
      } catch {
        inaccessibleStylesheets.push(stylesheet.href ?? "inline");
      }
    }
    const undersizedInteractiveElements = [];
    const unstyledInteractiveElements = [];
    for (const element of document.querySelectorAll("button, input, a[href]")) {
      if (!(element instanceof HTMLElement) || !visible(element)) continue;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const inlineLink = element.tagName === "A" && style.display === "inline";
      if (
        !inlineLink
        && (rect.width < limits.minimumTarget || rect.height < limits.minimumTarget)
      ) {
        undersizedInteractiveElements.push({
          tag: element.tagName.toLowerCase(),
          label: element.getAttribute("aria-label") || element.textContent?.trim() || null,
          width: rect.width,
          height: rect.height,
        });
      }
      if (
        Number.parseFloat(style.fontSize) < 10
        || style.color === "rgba(0, 0, 0, 0)"
        || style.visibility === "hidden"
      ) {
        unstyledInteractiveElements.push({
          tag: element.tagName.toLowerCase(),
          label: element.getAttribute("aria-label") || element.textContent?.trim() || null,
        });
      }
    }
    return {
      document_horizontal_overflow_px: Math.max(
        0,
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
      clipped_text_elements: clippedTextElements,
      undersized_text_elements: undersizedTextElements,
      stylesheet_count: document.styleSheets.length,
      css_rule_count: cssRuleCount,
      inaccessible_stylesheets: inaccessibleStylesheets,
      undersized_interactive_elements: undersizedInteractiveElements,
      unstyled_interactive_elements: unstyledInteractiveElements,
      app_font_family: getComputedStyle(document.body).fontFamily,
    };
  }, {
    minimumTarget: thresholds.minimum_interactive_target_css_px,
    minimumBodyText: thresholds.minimum_body_text_css_px,
    minimumSecondaryText: thresholds.minimum_secondary_text_css_px,
  });
}

function collectRuntimeSignals(page) {
  const consoleErrors = [];
  const pageErrors = [];
  const requestEvents = [];
  const requestEventByRequest = new Map();
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push({
        text: message.text(),
        location: message.location(),
      });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("request", (request) => {
    const url = canonicalRequestUrl(request.url());
    const event = {
      sequence_index: requestEvents.length,
      method: request.method().toUpperCase(),
      url,
      origin: requestOrigin(url),
      resource_type: request.resourceType(),
      response_status: null,
      failure: null,
    };
    requestEvents.push(event);
    requestEventByRequest.set(request, event);
  });
  page.on("requestfailed", (request) => {
    const event = requestEventByRequest.get(request);
    if (event) event.failure = normalizedText(request.failure()?.errorText ?? "unknown");
  });
  page.on("response", (response) => {
    const event = requestEventByRequest.get(response.request());
    if (event) event.response_status = response.status();
  });
  return {
    consoleErrors,
    pageErrors,
    requestEvents,
  };
}

export function deriveRequestEvidence(requestEvents, thresholds) {
  const allowedOrigins = new Set(thresholds.allowed_request_origins);
  const allowedFailedUrls = new Set(thresholds.allowed_failed_request_urls);
  const requestOrigins = [...new Set(
    requestEvents.map((event) => event.origin).filter(Boolean),
  )].sort();
  const failedRequests = requestEvents.filter((event) => event.failure !== null);
  const unallowlistedFailedRequests = failedRequests.filter(
    (event) => !allowedFailedUrls.has(event.url),
  );
  const stylesheetLoadFailures = requestEvents.filter((event) => (
    event.resource_type === "stylesheet"
    && (event.failure !== null || (event.response_status ?? 0) >= 400)
  ));
  const directThirdPartyTileRequests = requestEvents.filter((event) => {
    if (!event.url) return false;
    try {
      return new URL(event.url).hostname.endsWith(".tile.openstreetmap.org");
    } catch {
      return false;
    }
  });
  return {
    request_origins: requestOrigins,
    unexpected_request_origins: requestOrigins.filter(
      (origin) => !allowedOrigins.has(origin),
    ),
    failed_requests: failedRequests,
    unallowlisted_failed_requests: unallowlistedFailedRequests,
    stylesheet_load_failures: stylesheetLoadFailures,
    direct_third_party_tile_requests: directThirdPartyTileRequests,
  };
}

export function classifyConsoleErrors(consoleErrors, expectedHttpFailures) {
  const remainingExpected = expectedHttpFailures.map((failure) => ({ ...failure }));
  const expectedConsoleErrors = [];
  const unexpectedConsoleErrors = [];
  for (const event of consoleErrors) {
    const statusMatch = String(event.text ?? event).match(
      /Failed to load resource: the server responded with a status of (\d+)/,
    );
    const status = statusMatch ? Number.parseInt(statusMatch[1], 10) : null;
    const locationUrl = canonicalHttpUrl(event.location?.url);
    const candidateIndex = remainingExpected.findIndex((failure) => (
      failure.status === status
      && locationUrl !== null
      && canonicalHttpUrl(failure.url) === locationUrl
    ));
    if (candidateIndex >= 0) {
      expectedConsoleErrors.push({
        event,
        expected_http_failure: remainingExpected[candidateIndex],
      });
      remainingExpected.splice(candidateIndex, 1);
    } else {
      unexpectedConsoleErrors.push(event);
    }
  }
  return { expectedConsoleErrors, unexpectedConsoleErrors };
}

function surfaceChecks({ axe, layout, runtime, mapEvidence, thresholds }) {
  const checks = {
    axe_engine_version_bound: axe.engine_version_matches_installed_package,
    axe_wcag_a_aa_findings_within_limit:
      axe.finding_count <= thresholds.axe_wcag_a_aa_findings_max,
    no_document_horizontal_overflow:
      layout.document_horizontal_overflow_px
      <= thresholds.document_horizontal_overflow_max_px,
    clipped_text_within_limit:
      layout.clipped_text_elements.length <= thresholds.clipped_text_elements_max,
    stylesheets_accessible:
      layout.inaccessible_stylesheets.length <= thresholds.inaccessible_stylesheets_max,
    stylesheets_loaded:
      runtime.requestDerived.stylesheet_load_failures.length
      <= thresholds.stylesheet_load_failures_max,
    interactive_elements_styled:
      layout.unstyled_interactive_elements.length
      <= thresholds.unstyled_interactive_elements_max,
    interactive_targets_sized:
      layout.undersized_interactive_elements.length
      <= thresholds.undersized_interactive_elements_max,
    text_sizes_within_protocol:
      layout.undersized_text_elements.length <= thresholds.undersized_text_elements_max,
    console_clean:
      runtime.unexpectedConsoleErrors.length <= thresholds.console_errors_max,
    page_errors_clean: runtime.pageErrors.length <= thresholds.page_errors_max,
    request_origins_allowed:
      runtime.requestDerived.unexpected_request_origins.length
      <= thresholds.unexpected_request_origins_max,
    no_unallowlisted_failed_requests:
      runtime.requestDerived.unallowlisted_failed_requests.length === 0,
    no_direct_third_party_tile_requests:
      runtime.requestDerived.direct_third_party_tile_requests.length
      <= thresholds.direct_third_party_tile_requests_max,
    map_list_parity: mapEvidence.applicability === "applicable"
      ? mapEvidence.map_list_parity
      : "not_applicable",
    map_detail_integrity: mapEvidence.applicability === "applicable"
      ? mapEvidence.detail_integrity
      : "not_applicable",
    map_marker_placement_sanity: mapEvidence.applicability === "applicable"
      ? mapEvidence.marker_placement_sanity.sanity_passed
      : "not_applicable",
  };
  return {
    checks,
    qualified: Object.values(checks).every(
      (value) => value === true || value === "not_applicable",
    ),
  };
}

function relativeArtifact(file) {
  const relative = path.relative(repositoryRoot, file);
  return relative.startsWith("..") ? file : relative.split(path.sep).join("/");
}

async function captureSurfaceRow({
  browser,
  protocol,
  state,
  viewport,
  outputDirectory,
  baseUrl,
}) {
  const context = await browser.newContext({
    baseURL: baseUrl,
    ...browserContextConfiguration(protocol, viewport),
  });
  const page = await context.newPage();
  const runtime = collectRuntimeSignals(page);
  const routes = await installDeterministicRoutes(page);
  const screenshotDirectory = path.join(outputDirectory, "screenshots");
  const screenshotPath = path.join(
    screenshotDirectory,
    `${state.id}--${viewport.id}.png`,
  );
  await mkdir(screenshotDirectory, { recursive: true });
  let row;
  let mapEvidence = protocol.map_parity.applicable_state_ids.includes(state.id)
    ? initialApplicableMapEvidence(state, protocol)
    : notApplicableMapEvidence();
  try {
    await driveState(page, state);
    mapEvidence = await inspectMapEvidence(page, state, protocol);
    await page.waitForLoadState("networkidle");
    await page.addStyleTag({
      content: "*,*::before,*::after{animation:none!important;transition:none!important;}",
    });
    const axe = await runAxe(page);
    const layout = await inspectLayoutAndCss(page, protocol.surface_thresholds);
    const consoleClassification = classifyConsoleErrors(
      runtime.consoleErrors,
      routes.expectedHttpFailures,
    );
    const requestDerived = deriveRequestEvidence(
      runtime.requestEvents,
      protocol.surface_thresholds,
    );
    const screenshotBytes = await page.screenshot({
      path: screenshotPath,
      fullPage: true,
      animations: "disabled",
    });
    const screenshotStat = await stat(screenshotPath);
    const screenshotMetadata = await sharp(screenshotBytes).metadata();
    const assessment = surfaceChecks({
      axe,
      layout,
      runtime: { ...runtime, ...consoleClassification, requestDerived },
      mapEvidence,
      thresholds: protocol.surface_thresholds,
    });
    row = {
      state_id: state.id,
      viewport_id: viewport.id,
      viewport: {
        width: viewport.width,
        height: viewport.height,
        device_scale_factor: viewport.device_scale_factor,
        is_mobile: viewport.is_mobile,
      },
      status: "complete",
      screenshot: {
        path: relativeArtifact(screenshotPath),
        sha256: sha256Bytes(screenshotBytes),
        bytes: screenshotStat.size,
        format: screenshotMetadata.format,
        signature_hex: screenshotBytes.subarray(0, 8).toString("hex"),
        width_px: screenshotMetadata.width,
        height_px: screenshotMetadata.height,
      },
      axe,
      layout,
      map_evidence: mapEvidence,
      runtime: {
        console_errors: runtime.consoleErrors,
        expected_console_errors: consoleClassification.expectedConsoleErrors,
        unexpected_console_errors: consoleClassification.unexpectedConsoleErrors,
        expected_http_failures: routes.expectedHttpFailures,
        page_errors: runtime.pageErrors,
        request_events: runtime.requestEvents,
        request_derived: requestDerived,
      },
      checks: assessment.checks,
      qualified: assessment.qualified,
    };
  } catch (error) {
    const consoleClassification = classifyConsoleErrors(
      runtime.consoleErrors,
      routes.expectedHttpFailures,
    );
    const requestDerived = deriveRequestEvidence(
      runtime.requestEvents,
      protocol.surface_thresholds,
    );
    row = {
      state_id: state.id,
      viewport_id: viewport.id,
      viewport: {
        width: viewport.width,
        height: viewport.height,
        device_scale_factor: viewport.device_scale_factor,
        is_mobile: viewport.is_mobile,
      },
      status: "error",
      error: String(error?.stack ?? error),
      screenshot: null,
      axe: null,
      layout: null,
      map_evidence: mapEvidence,
      runtime: {
        console_errors: runtime.consoleErrors,
        expected_console_errors: consoleClassification.expectedConsoleErrors,
        unexpected_console_errors: consoleClassification.unexpectedConsoleErrors,
        expected_http_failures: routes.expectedHttpFailures,
        page_errors: runtime.pageErrors,
        request_events: runtime.requestEvents,
        request_derived: requestDerived,
      },
      checks: {},
      qualified: false,
    };
  } finally {
    routes.releaseLoading();
    await context.close();
  }
  return row;
}

async function runSurfaceMatrix(browser, protocol, outputDirectory, baseUrl) {
  const rows = [];
  for (const state of protocol.states) {
    for (const viewport of protocol.viewports) {
      rows.push(await captureSurfaceRow({
        browser,
        protocol,
        state,
        viewport,
        outputDirectory,
        baseUrl,
      }));
    }
  }
  return rows;
}

async function newJourneyPage(browser, protocol, viewport, baseUrl) {
  const context = await browser.newContext({
    baseURL: baseUrl,
    ...browserContextConfiguration(protocol, viewport),
  });
  const page = await context.newPage();
  const routes = await installDeterministicRoutes(page);
  return { context, page, routes };
}

async function keyboardJourney(browser, protocol, baseUrl) {
  const viewport = protocol.viewports.find((item) => item.id === "desktop");
  const { context, page } = await newJourneyPage(browser, protocol, viewport, baseUrl);
  const checks = {};
  const errors = [];
  try {
    await page.goto("/", { waitUntil: "networkidle" });
    const input = page.getByLabel("Ask FireLens a question");
    await input.fill("surface:grounded");
    await input.press("Enter");
    checks.question_submitted_with_enter = true;
    await waitForText(page, "Sources supporting this answer");
    checks.grounded_answer_visible = true;
    const toggle = page.locator("button.source-toggle").first();
    let reached = false;
    for (let index = 0; index < 30; index += 1) {
      await page.keyboard.press("Tab");
      reached = await toggle.evaluate((element) => document.activeElement === element);
      if (reached) break;
    }
    checks.source_toggle_reached_with_keyboard = reached;
    const before = await toggle.getAttribute("aria-expanded");
    if (reached) await page.keyboard.press("Enter");
    const after = await toggle.getAttribute("aria-expanded");
    checks.source_toggle_activated_with_enter = reached && before !== after;
    checks.focus_indicator_present = reached && await toggle.evaluate((element) => {
      const style = getComputedStyle(element);
      return (
        (style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0)
        || style.boxShadow !== "none"
      );
    });
  } catch (error) {
    errors.push(String(error?.stack ?? error));
  } finally {
    await context.close();
  }
  const required = protocol.functional_journeys.find(
    (item) => item.id === "keyboard_evidence_navigation",
  ).required_checks;
  return {
    id: "keyboard_evidence_navigation",
    checks,
    errors,
    qualified: errors.length === 0 && required.every((key) => checks[key] === true),
  };
}

async function inspectPrivacyBrowserSurfaces(page, tokens) {
  return page.evaluate(async (probeTokens) => {
    const matches = (value) => {
      const text = String(value ?? "");
      return probeTokens.filter((token) => text.includes(token));
    };
    const storageEntries = (storage) => Array.from(
      { length: storage.length },
      (_, index) => storage.key(index),
    ).filter(Boolean).sort().map((key) => {
      const value = storage.getItem(key) ?? "";
      return {
        key,
        key_token_matches: matches(key),
        value_length: value.length,
        value_token_matches: matches(value),
      };
    });
    const historyState = JSON.stringify(history.state) ?? "undefined";
    const indexedDbEvidence = { supported: false, databases: [] };
    if (typeof indexedDB?.databases === "function") {
      indexedDbEvidence.supported = true;
      const databases = await indexedDB.databases();
      for (const info of databases.sort((left, right) => (
        String(left.name).localeCompare(String(right.name))
      ))) {
        if (!info.name) continue;
        const database = await new Promise((resolve, reject) => {
          const request = indexedDB.open(info.name);
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });
        const objectStores = [];
        for (const storeName of [...database.objectStoreNames].sort()) {
          const values = await new Promise((resolve, reject) => {
            const request = database
              .transaction(storeName, "readonly")
              .objectStore(storeName)
              .getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const serialized = JSON.stringify(values);
          objectStores.push({
            name: storeName,
            name_token_matches: matches(storeName),
            record_count: values.length,
            serialized_length: serialized.length,
            value_token_matches: matches(serialized),
          });
        }
        indexedDbEvidence.databases.push({
          name: info.name,
          version: info.version ?? null,
          name_token_matches: matches(info.name),
          object_stores: objectStores,
        });
        database.close();
      }
    }
    const cacheEvidence = { supported: "caches" in window, caches: [] };
    if (cacheEvidence.supported) {
      for (const cacheName of (await caches.keys()).sort()) {
        const cache = await caches.open(cacheName);
        const entries = [];
        for (const request of await cache.keys()) {
          const response = await cache.match(request);
          let responseText = "";
          try {
            responseText = response ? await response.clone().text() : "";
          } catch {
            responseText = "";
          }
          entries.push({
            request_url: request.url,
            request_url_token_matches: matches(request.url),
            response_body_length: responseText.length,
            response_body_token_matches: matches(responseText),
          });
        }
        cacheEvidence.caches.push({
          name: cacheName,
          name_token_matches: matches(cacheName),
          entries,
        });
      }
    }
    const serviceWorkerEvidence = {
      supported: "serviceWorker" in navigator,
      registrations: [],
    };
    if (serviceWorkerEvidence.supported) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      serviceWorkerEvidence.registrations = registrations.map((registration) => {
        const scriptUrls = [
          registration.installing?.scriptURL,
          registration.waiting?.scriptURL,
          registration.active?.scriptURL,
        ].filter(Boolean).sort();
        return {
          scope: registration.scope,
          scope_token_matches: matches(registration.scope),
          script_urls: scriptUrls,
          script_url_token_matches: matches(scriptUrls.join("\n")),
        };
      }).sort((left, right) => left.scope.localeCompare(right.scope));
    }
    const cookies = document.cookie
      ? document.cookie.split(";").map((entry) => entry.trim()).filter(Boolean)
      : [];
    return {
      current_url: location.href,
      current_url_token_matches: matches(location.href),
      history: {
        length: history.length,
        state_type: history.state === null ? "null" : typeof history.state,
        state_serialized_length: historyState.length,
        state_token_matches: matches(historyState),
      },
      local_storage: storageEntries(localStorage),
      session_storage: storageEntries(sessionStorage),
      cookies: cookies.map((entry) => {
        const separator = entry.indexOf("=");
        const name = separator >= 0 ? entry.slice(0, separator) : entry;
        const value = separator >= 0 ? entry.slice(separator + 1) : "";
        return {
          name,
          name_token_matches: matches(name),
          value_length: value.length,
          value_token_matches: matches(value),
        };
      }),
      indexed_db: indexedDbEvidence,
      cache_storage: cacheEvidence,
      service_workers: serviceWorkerEvidence,
    };
  }, tokens);
}

function tokenMatchFindings(value, pathParts = []) {
  const findings = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      findings.push(...tokenMatchFindings(item, [...pathParts, String(index)]));
    });
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const childPath = [...pathParts, key];
      if (key.endsWith("_token_matches") && Array.isArray(child)) {
        for (const token of child) findings.push({ path: childPath.join("."), token });
      } else {
        findings.push(...tokenMatchFindings(child, childPath));
      }
    }
  }
  return findings;
}

export function derivePrivacyEvidence(evidence, protocol) {
  const config = protocol.privacy_evidence;
  const expectedUrl = canonicalHttpUrl(config.request_url);
  const apiRequestRoster = evidence.api_request_roster ?? [];
  const apiRequestIssues = [];
  apiRequestRoster.forEach((request, index) => {
    const expectedQuestion = config.expected_questions[index];
    const bodyKeys = Object.keys(request.body ?? {}).sort();
    const unexpectedKeys = bodyKeys.filter(
      (key) => !config.allowed_body_keys.includes(key),
    );
    if (
      !hasExactKeys(request, [
        "sequence_index",
        "method",
        "url",
        "origin",
        "resource_type",
        "body",
        "body_sha256",
        "response_status",
      ])
      || request.sequence_index !== index
      || request.method !== "POST"
      || request.url !== expectedUrl
      || request.origin !== requestOrigin(expectedUrl)
      || request.resource_type !== "fetch"
      || request.response_status !== 200
      || request.body_sha256
        !== sha256Bytes(Buffer.from(stableJsonString(request.body), "utf8"))
      || JSON.stringify(request.body) !== stableJsonString(request.body)
      || request.body?.question !== expectedQuestion
      || unexpectedKeys.length > 0
    ) {
      apiRequestIssues.push({ sequence_index: index, reason: "request_contract_mismatch" });
    }
  });
  if (apiRequestRoster.length !== config.expected_questions.length) {
    apiRequestIssues.push({
      sequence_index: null,
      reason: "request_count_mismatch",
      expected: config.expected_questions.length,
      observed: apiRequestRoster.length,
    });
  }
  const firstBody = apiRequestRoster[0]?.body ?? {};
  const secondBody = apiRequestRoster[1]?.body ?? {};
  const location = config.fixture_location;
  if ("location" in firstBody || firstBody.history?.length !== 0) {
    apiRequestIssues.push({ sequence_index: 0, reason: "first_request_location_or_history" });
  }
  if (
    secondBody.location?.latitude !== location.rounded_latitude
    || secondBody.location?.longitude !== location.rounded_longitude
    || secondBody.location?.radius_km !== location.radius_km
    || secondBody.history?.length !== 2
  ) {
    apiRequestIssues.push({ sequence_index: 1, reason: "live_request_boundary_mismatch" });
  }
  const bodyTokenLeakFindings = [];
  apiRequestRoster.forEach((request, index) => {
    const bodyOutsideAllowedLocation = stableJson({
      ...request.body,
      location: undefined,
    });
    const serialized = stableJsonString(bodyOutsideAllowedLocation);
    for (const token of config.persistence_probe_tokens) {
      if (serialized.includes(token)) {
        bodyTokenLeakFindings.push({ sequence_index: index, token });
      }
    }
  });
  const recomputedNetwork = deriveRequestEvidence(
    evidence.network_request_events ?? [],
    protocol.surface_thresholds,
  );
  const networkEvidenceMatches = (
    JSON.stringify(recomputedNetwork) === JSON.stringify(evidence.network_request_derived)
  );
  const browserTokenFindings = tokenMatchFindings(evidence.browser_surfaces ?? {});
  const surfaces = evidence.browser_surfaces ?? {};
  const urlHistoryClean = (
    (surfaces.current_url_token_matches?.length ?? 0) === 0
    && (surfaces.history?.state_token_matches?.length ?? 0) === 0
  );
  const browserStorageSurfacesClean = (
    (surfaces.local_storage?.length ?? 0) === 0
    && (surfaces.session_storage?.length ?? 0) === 0
    && (surfaces.cookies?.length ?? 0) === 0
    && (surfaces.indexed_db?.databases?.length ?? 0) === 0
    && (surfaces.cache_storage?.caches?.length ?? 0) === 0
    && (surfaces.service_workers?.registrations?.length ?? 0) === 0
    && browserTokenFindings.length === 0
  );
  const unexpectedNetworkEntries = [
    ...recomputedNetwork.unexpected_request_origins.map((origin) => ({
      kind: "unexpected_origin",
      origin,
    })),
    ...recomputedNetwork.unallowlisted_failed_requests.map((request) => ({
      kind: "unallowlisted_failed_request",
      request,
    })),
  ];
  return {
    geolocation_not_called_before_opt_in:
      evidence.geolocation_calls?.before_opt_in === 0,
    geolocation_called_once_after_opt_in:
      evidence.geolocation_calls?.after_opt_in === 1,
    coordinates_rounded_to_two_decimals: (
      secondBody.location?.latitude === location.rounded_latitude
      && secondBody.location?.longitude === location.rounded_longitude
    ),
    location_sent_only_with_live_request: (
      firstBody.location === undefined
      && secondBody.location?.radius_km === location.radius_km
      && secondBody.question === config.expected_questions[1]
    ),
    location_not_persisted_in_browser_storage: browserTokenFindings.length === 0,
    no_cookie_written: (surfaces.cookies?.length ?? 0) === 0,
    canonical_request_roster_valid: apiRequestIssues.length === 0,
    api_request_issues: apiRequestIssues,
    network_request_derivation_matches: networkEvidenceMatches,
    unexpected_network_entries: unexpectedNetworkEntries,
    body_token_leak_findings: bodyTokenLeakFindings,
    browser_token_leak_findings: browserTokenFindings,
    no_unexpected_request_or_body_leakage: (
      apiRequestIssues.length === 0
      && networkEvidenceMatches
      && unexpectedNetworkEntries.length === 0
      && bodyTokenLeakFindings.length === 0
    ),
    url_history_clean: urlHistoryClean,
    both_coordinate_tokens_absent_outside_allowed_request: (
      bodyTokenLeakFindings.length === 0 && browserTokenFindings.length === 0
    ),
    browser_storage_surfaces_clean: browserStorageSurfacesClean,
  };
}

async function privacyJourney(browser, protocol, baseUrl) {
  const viewport = protocol.viewports.find((item) => item.id === "desktop");
  const context = await browser.newContext({
    baseURL: baseUrl,
    ...browserContextConfiguration(protocol, viewport),
  });
  await context.addInitScript(() => {
    window.__surfaceGeolocationCalls = 0;
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          window.__surfaceGeolocationCalls += 1;
          success({ coords: { latitude: 49.282729, longitude: -123.120738 } });
        },
      },
    });
  });
  const page = await context.newPage();
  const runtime = collectRuntimeSignals(page);
  const routes = await installDeterministicRoutes(page);
  const checks = {};
  const errors = [];
  let evidence = null;
  try {
    await page.goto("/", { waitUntil: "networkidle" });
    const geolocationBeforeOptIn = await page.evaluate(
      () => window.__surfaceGeolocationCalls,
    );
    await page.getByLabel("Ask FireLens a question").fill("surface:requires-location");
    await page.getByLabel("Ask FireLens a question").press("Enter");
    await waitForText(page, "One detail needed");
    await page.getByRole("button", { name: "Use approximate location" }).click();
    await waitForText(page, "Approximate location ready for this request.");
    const geolocationAfterOptIn = await page.evaluate(
      () => window.__surfaceGeolocationCalls,
    );
    await waitForText(page, "Current BC wildfire information");
    await page.waitForLoadState("networkidle");
    const browserSurfaces = await inspectPrivacyBrowserSurfaces(
      page,
      protocol.privacy_evidence.persistence_probe_tokens,
    );
    const networkRequestDerived = deriveRequestEvidence(
      runtime.requestEvents,
      protocol.surface_thresholds,
    );
    evidence = {
      fixture_data_only: true,
      persistence_probe_tokens: protocol.privacy_evidence.persistence_probe_tokens,
      geolocation_calls: {
        before_opt_in: geolocationBeforeOptIn,
        after_opt_in: geolocationAfterOptIn,
      },
      api_request_roster: routes.apiRequestRecords,
      network_request_events: runtime.requestEvents,
      network_request_derived: networkRequestDerived,
      browser_surfaces: browserSurfaces,
      derived: null,
    };
    evidence.derived = derivePrivacyEvidence(evidence, protocol);
    for (const checkName of protocol.functional_journeys.find(
      (journey) => journey.id === "location_privacy_boundary",
    ).required_checks) {
      checks[checkName] = evidence.derived[checkName];
    }
  } catch (error) {
    errors.push(String(error?.stack ?? error));
  } finally {
    routes.releaseLoading();
    await context.close();
  }
  const required = protocol.functional_journeys.find(
    (item) => item.id === "location_privacy_boundary",
  ).required_checks;
  return {
    id: "location_privacy_boundary",
    checks,
    evidence,
    errors,
    qualified: errors.length === 0 && required.every((key) => checks[key] === true),
  };
}

async function historyJourney(browser, protocol, baseUrl) {
  const viewport = protocol.viewports.find((item) => item.id === "desktop");
  const { context, page, routes } = await newJourneyPage(
    browser,
    protocol,
    viewport,
    baseUrl,
  );
  const checks = {};
  const errors = [];
  try {
    await page.goto("/", { waitUntil: "networkidle" });
    const input = page.getByLabel("Ask FireLens a question");
    await input.fill("surface:grounded");
    await input.press("Enter");
    await waitForText(page, "Sources supporting this answer");
    await input.fill("surface:background");
    await input.press("Enter");
    await waitForText(page, "General background — no corpus evidence attached");
    checks.bounded_history_sent = routes.requestBodies[1]?.history?.length === 2;
    await page.getByLabel("Clear conversation history").click();
    await waitForText(page, "Select a fire or ask anything");
    checks.clear_returns_idle = true;
    await input.fill("surface:capability");
    await input.press("Enter");
    await waitForText(page, "Explore the FireLens collection");
    checks.next_request_history_empty = routes.requestBodies[2]?.history?.length === 0;
  } catch (error) {
    errors.push(String(error?.stack ?? error));
  } finally {
    routes.releaseLoading();
    await context.close();
  }
  const required = protocol.functional_journeys.find(
    (item) => item.id === "history_clear_boundary",
  ).required_checks;
  return {
    id: "history_clear_boundary",
    checks,
    errors,
    qualified: errors.length === 0 && required.every((key) => checks[key] === true),
  };
}

async function runFunctionalJourneys(browser, protocol, baseUrl) {
  return [
    await keyboardJourney(browser, protocol, baseUrl),
    await privacyJourney(browser, protocol, baseUrl),
    await historyJourney(browser, protocol, baseUrl),
  ];
}

function p75NearestRank(values) {
  const finite = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (finite.length === 0) return null;
  return finite[Math.max(0, Math.ceil(0.75 * finite.length) - 1)];
}

export { p75NearestRank };

async function configurePerformancePage(page, protocol) {
  await page.addInitScript(() => {
    window.__surfaceVitals = { lcp_ms: null, cls: 0, inp_interaction_proxy_ms: null };
    try {
      new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const latest = entries.at(-1);
        if (latest) window.__surfaceVitals.lcp_ms = latest.startTime;
      }).observe({ type: "largest-contentful-paint", buffered: true });
    } catch {
      // Missing browser support is represented as a null metric and fails qualification.
    }
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) window.__surfaceVitals.cls += entry.value;
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {
      // Missing browser support is represented by the protocol validator.
    }
    addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const started = performance.now();
      requestAnimationFrame(() => requestAnimationFrame(() => {
        window.__surfaceVitals.inp_interaction_proxy_ms = performance.now() - started;
      }));
    }, { once: true, capture: true });
  });
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setCPUThrottlingRate", {
    rate: protocol.performance.cpu_throttling_rate,
  });
  await session.send("Network.enable");
  await session.send("Network.setCacheDisabled", { cacheDisabled: true });
  await session.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: protocol.performance.network.latency_ms,
    downloadThroughput: protocol.performance.network.download_bytes_per_second,
    uploadThroughput: protocol.performance.network.upload_bytes_per_second,
    connectionType: protocol.performance.network.connection_type,
  });
}

async function performanceSample(
  browser,
  protocol,
  viewport,
  phase,
  sampleIndex,
  baseUrl,
) {
  const context = await browser.newContext({
    baseURL: baseUrl,
    ...browserContextConfiguration(protocol, viewport),
  });
  const page = await context.newPage();
  const routes = await installDeterministicRoutes(page);
  const result = {
    phase,
    sample_index: sampleIndex,
    lcp_ms: null,
    cls: null,
    inp_interaction_proxy_ms: null,
    map_ready_after_interaction_ms: null,
    status: "error",
    error: null,
  };
  try {
    await configurePerformancePage(page, protocol);
    await page.goto("/", { waitUntil: "networkidle" });
    await waitForText(page, "Select a fire or ask anything");
    await page.waitForTimeout(250);
    const beforeInteraction = await page.evaluate(() => ({ ...window.__surfaceVitals }));
    const input = page.getByLabel("Ask FireLens a question");
    await input.fill("surface:live-fresh");
    const interactionStarted = await page.evaluate(() => performance.now());
    await input.press("Enter");
    await page.getByRole("region", { name: "Official wildfire records map" }).waitFor();
    await page.locator(".leaflet-interactive").first().waitFor();
    await page.waitForFunction(
      () => Number.isFinite(window.__surfaceVitals.inp_interaction_proxy_ms),
    );
    const afterInteraction = await page.evaluate(() => ({
      now: performance.now(),
      vitals: { ...window.__surfaceVitals },
    }));
    result.lcp_ms = beforeInteraction.lcp_ms;
    result.cls = afterInteraction.vitals.cls;
    result.inp_interaction_proxy_ms = afterInteraction.vitals.inp_interaction_proxy_ms;
    result.map_ready_after_interaction_ms = afterInteraction.now - interactionStarted;
    result.status = [
      result.lcp_ms,
      result.cls,
      result.inp_interaction_proxy_ms,
      result.map_ready_after_interaction_ms,
    ].every((value) => Number.isFinite(value)) ? "complete" : "incomplete";
  } catch (error) {
    result.error = String(error?.stack ?? error);
  } finally {
    routes.releaseLoading();
    await context.close();
  }
  return result;
}

async function runPerformanceProfile(browser, protocol, viewport, baseUrl) {
  const samples = [];
  const total = protocol.performance.warmup_samples + protocol.performance.cold_samples;
  for (let index = 0; index < total; index += 1) {
    const phase = index < protocol.performance.warmup_samples ? "warmup" : "cold";
    const sampleIndex = phase === "warmup"
      ? index + 1
      : index - protocol.performance.warmup_samples + 1;
    samples.push(await performanceSample(
      browser,
      protocol,
      viewport,
      phase,
      sampleIndex,
      baseUrl,
    ));
  }
  const cold = samples.filter((sample) => sample.phase === "cold");
  const p75 = {
    lcp_ms: p75NearestRank(cold.map((sample) => sample.lcp_ms)),
    cls: p75NearestRank(cold.map((sample) => sample.cls)),
    inp_interaction_proxy_ms: p75NearestRank(
      cold.map((sample) => sample.inp_interaction_proxy_ms),
    ),
    map_ready_after_interaction_ms: p75NearestRank(
      cold.map((sample) => sample.map_ready_after_interaction_ms),
    ),
  };
  const thresholds = protocol.performance.thresholds[viewport.id];
  const checks = {
    exact_sample_count: (
      samples.filter((sample) => sample.phase === "warmup").length === 1
      && cold.length === 7
      && cold.every((sample) => sample.status === "complete")
    ),
    lcp_within_threshold: Number.isFinite(p75.lcp_ms)
      && p75.lcp_ms <= thresholds.lcp_ms_max,
    cls_within_threshold: Number.isFinite(p75.cls) && p75.cls <= thresholds.cls_max,
    inp_proxy_within_threshold: Number.isFinite(p75.inp_interaction_proxy_ms)
      && p75.inp_interaction_proxy_ms <= thresholds.inp_interaction_proxy_ms_max,
    map_ready_within_threshold: Number.isFinite(p75.map_ready_after_interaction_ms)
      && p75.map_ready_after_interaction_ms
      <= thresholds.map_ready_after_interaction_ms_max,
  };
  return {
    profile_id: viewport.id,
    viewport: { width: viewport.width, height: viewport.height },
    throttling: {
      cpu_rate: protocol.performance.cpu_throttling_rate,
      network: protocol.performance.network,
      cache_disabled: protocol.performance.cache_disabled_for_cold_samples,
    },
    samples,
    cold_p75: p75,
    thresholds,
    checks,
    qualified: Object.values(checks).every(Boolean),
  };
}

async function runPerformance(browser, protocol, baseUrl) {
  const profiles = [];
  for (const profileId of protocol.performance.profiles) {
    const viewport = protocol.viewports.find((item) => item.id === profileId);
    profiles.push(await runPerformanceProfile(browser, protocol, viewport, baseUrl));
  }
  return {
    aggregation: protocol.performance.aggregation,
    profiles,
    qualified: profiles.every((profile) => profile.qualified),
  };
}

function expectedPairs(protocol) {
  return new Set(protocol.states.flatMap(
    (state) => protocol.viewports.map((viewport) => `${state.id}::${viewport.id}`),
  ));
}

export function surfaceMatrixComplete(surfaceRows, protocol) {
  if (!Array.isArray(surfaceRows)) return false;
  const expected = expectedPairs(protocol);
  const observed = new Set(
    surfaceRows.map((row) => `${row.state_id}::${row.viewport_id}`),
  );
  return (
    surfaceRows.length === protocol.matrix.expected_rows
    && observed.size === expected.size
    && [...expected].every((key) => observed.has(key))
    && surfaceRows.every((row) => row.status === "complete")
  );
}

function recomputeAxeImpactCounts(findings) {
  const counts = { critical: 0, serious: 0, moderate: 0, minor: 0, unknown: 0 };
  for (const finding of findings) {
    const bucket = Object.hasOwn(counts, finding.impact) ? finding.impact : "unknown";
    counts[bucket] += 1;
  }
  return counts;
}

function validateAxeEvidence(row, protocol) {
  const key = `${row.state_id}::${row.viewport_id}`;
  const axe = row.axe;
  const issues = [];
  if (
    !axe
    || !Array.isArray(axe.findings)
    || axe.engine_version !== installedAxeCoreVersion
    || axe.installed_package_version !== installedAxeCoreVersion
    || axe.engine_version_matches_installed_package !== true
  ) {
    return [`axe engine evidence mismatch ${key}`];
  }
  if (
    axe.finding_count !== axe.findings.length
    || JSON.stringify(axe.impact_counts)
      !== JSON.stringify(recomputeAxeImpactCounts(axe.findings))
  ) {
    issues.push(`axe finding derivation mismatch ${key}`);
  }
  for (const finding of axe.findings) {
    if (
      typeof finding.id !== "string"
      || !Array.isArray(finding.tags)
      || !Array.isArray(finding.nodes)
      || finding.nodes.length === 0
    ) {
      issues.push(`axe finding detail invalid ${key}`);
      break;
    }
  }
  if (row.checks?.axe_engine_version_bound !== true) {
    issues.push(`axe engine qualification check mismatch ${key}`);
  }
  const expectedFindingCheck = (
    axe.finding_count <= protocol.surface_thresholds.axe_wcag_a_aa_findings_max
  );
  if (row.checks?.axe_wcag_a_aa_findings_within_limit !== expectedFindingCheck) {
    issues.push(`axe finding qualification check mismatch ${key}`);
  }
  if (!expectedFindingCheck && row.qualified !== false) {
    issues.push(`axe findings did not fail row qualification ${key}`);
  }
  return issues;
}

function validateRequestRuntime(row, protocol) {
  const key = `${row.state_id}::${row.viewport_id}`;
  const runtime = row.runtime;
  const issues = [];
  if (!Array.isArray(runtime?.request_events) || !runtime.request_derived) {
    return [`canonical request evidence missing ${key}`];
  }
  runtime.request_events.forEach((event, index) => {
    const outcomeCount = Number(Number.isInteger(event.response_status))
      + Number(typeof event.failure === "string" && event.failure.length > 0);
    if (
      !hasExactKeys(event, [
        "sequence_index",
        "method",
        "url",
        "origin",
        "resource_type",
        "response_status",
        "failure",
      ])
      || event.sequence_index !== index
      || event.method !== String(event.method).toUpperCase()
      || canonicalRequestUrl(event.url) !== event.url
      || requestOrigin(event.url) !== event.origin
      || typeof event.resource_type !== "string"
      || !event.resource_type
      || outcomeCount !== 1
    ) {
      issues.push(`canonical request event invalid ${key} index ${index}`);
    }
  });
  const recomputed = deriveRequestEvidence(
    runtime.request_events,
    protocol.surface_thresholds,
  );
  if (JSON.stringify(runtime.request_derived) !== JSON.stringify(recomputed)) {
    issues.push(`request derivation mismatch ${key}`);
  }
  const consoleClassification = classifyConsoleErrors(
    runtime.console_errors ?? [],
    runtime.expected_http_failures ?? [],
  );
  if (
    JSON.stringify(runtime.expected_console_errors)
      !== JSON.stringify(consoleClassification.expectedConsoleErrors)
    || JSON.stringify(runtime.unexpected_console_errors)
      !== JSON.stringify(consoleClassification.unexpectedConsoleErrors)
  ) {
    issues.push(`console classification mismatch ${key}`);
  }
  const expectedChecks = {
    stylesheets_loaded:
      recomputed.stylesheet_load_failures.length
      <= protocol.surface_thresholds.stylesheet_load_failures_max,
    request_origins_allowed:
      recomputed.unexpected_request_origins.length
      <= protocol.surface_thresholds.unexpected_request_origins_max,
    no_unallowlisted_failed_requests:
      recomputed.unallowlisted_failed_requests.length === 0,
    no_direct_third_party_tile_requests:
      recomputed.direct_third_party_tile_requests.length
      <= protocol.surface_thresholds.direct_third_party_tile_requests_max,
  };
  for (const [check, expected] of Object.entries(expectedChecks)) {
    if (row.checks?.[check] !== expected) {
      issues.push(`request qualification check mismatch ${key} ${check}`);
    }
    if (!expected && row.qualified !== false) {
      issues.push(`request failure did not fail row qualification ${key} ${check}`);
    }
  }
  return issues;
}

function validatePrivacyJourney(journey, protocol) {
  const issues = [];
  const evidence = journey.evidence;
  if (!evidence || evidence.fixture_data_only !== true) {
    return ["privacy journey evidence missing"];
  }
  if (
    JSON.stringify(evidence.persistence_probe_tokens)
      !== JSON.stringify(protocol.privacy_evidence.persistence_probe_tokens)
  ) {
    issues.push("privacy journey token roster mismatch");
  }
  if (!Array.isArray(evidence.network_request_events)) {
    issues.push("privacy network request roster missing");
  } else {
    evidence.network_request_events.forEach((event, index) => {
      const outcomeCount = Number(Number.isInteger(event.response_status))
        + Number(typeof event.failure === "string" && event.failure.length > 0);
      if (
        event.sequence_index !== index
        || canonicalRequestUrl(event.url) !== event.url
        || requestOrigin(event.url) !== event.origin
        || outcomeCount !== 1
      ) {
        issues.push(`privacy network request event invalid ${index}`);
      }
    });
  }
  const recomputed = derivePrivacyEvidence(evidence, protocol);
  if (JSON.stringify(evidence.derived) !== JSON.stringify(recomputed)) {
    issues.push("privacy journey derivation mismatch");
  }
  const required = protocol.functional_journeys.find(
    (item) => item.id === "location_privacy_boundary",
  ).required_checks;
  for (const check of required) {
    if (journey.checks?.[check] !== recomputed[check]) {
      issues.push(`privacy journey check mismatch ${check}`);
    }
  }
  return issues;
}

function validateFunctionalJourneys(journeys, protocol) {
  const issues = [];
  if (!Array.isArray(journeys)) return ["functional journeys missing"];
  const expectedIds = protocol.functional_journeys.map((item) => item.id);
  const observedIds = journeys.map((item) => item.id);
  if (new Set(observedIds).size !== observedIds.length) {
    issues.push("duplicate functional journey id");
  }
  if (JSON.stringify(observedIds) !== JSON.stringify(expectedIds)) {
    issues.push("functional journey roster mismatch");
  }
  journeys.forEach((journey) => {
    const definition = protocol.functional_journeys.find((item) => item.id === journey.id);
    if (!definition) return;
    if (!Array.isArray(journey.errors) || !journey.checks) {
      issues.push(`functional journey evidence incomplete ${journey.id}`);
      return;
    }
    const recomputedQualified = (
      journey.errors.length === 0
      && definition.required_checks.every((check) => journey.checks[check] === true)
    );
    if (journey.qualified !== recomputedQualified) {
      issues.push(`functional journey qualification mismatch ${journey.id}`);
    }
    if (journey.id === "location_privacy_boundary") {
      issues.push(...validatePrivacyJourney(journey, protocol));
    }
  });
  return issues;
}

function recomputePerformanceProfile(profile, protocol) {
  const cold = profile.samples.filter((sample) => sample.phase === "cold");
  const p75 = {
    lcp_ms: p75NearestRank(cold.map((sample) => sample.lcp_ms)),
    cls: p75NearestRank(cold.map((sample) => sample.cls)),
    inp_interaction_proxy_ms: p75NearestRank(
      cold.map((sample) => sample.inp_interaction_proxy_ms),
    ),
    map_ready_after_interaction_ms: p75NearestRank(
      cold.map((sample) => sample.map_ready_after_interaction_ms),
    ),
  };
  const thresholds = protocol.performance.thresholds[profile.profile_id];
  const checks = {
    exact_sample_count: (
      profile.samples.length === 8
      && profile.samples.every((sample) => sample.status === "complete")
    ),
    lcp_within_threshold: Number.isFinite(p75.lcp_ms)
      && p75.lcp_ms <= thresholds.lcp_ms_max,
    cls_within_threshold: Number.isFinite(p75.cls) && p75.cls <= thresholds.cls_max,
    inp_proxy_within_threshold: Number.isFinite(p75.inp_interaction_proxy_ms)
      && p75.inp_interaction_proxy_ms <= thresholds.inp_interaction_proxy_ms_max,
    map_ready_within_threshold: Number.isFinite(p75.map_ready_after_interaction_ms)
      && p75.map_ready_after_interaction_ms
      <= thresholds.map_ready_after_interaction_ms_max,
  };
  return { p75, checks, qualified: Object.values(checks).every(Boolean) };
}

function validatePerformance(performance, protocol) {
  const issues = [];
  const profiles = performance?.profiles;
  if (!Array.isArray(profiles)) return ["performance profiles missing"];
  const observedIds = profiles.map((profile) => profile.profile_id);
  if (new Set(observedIds).size !== observedIds.length) {
    issues.push("duplicate performance profile id");
  }
  if (JSON.stringify(observedIds) !== JSON.stringify(protocol.performance.profiles)) {
    issues.push("performance profile roster mismatch");
  }
  for (const profile of profiles) {
    if (!protocol.performance.profiles.includes(profile.profile_id)) continue;
    const expectedSampleOrder = [
      { phase: "warmup", sample_index: 1 },
      ...Array.from({ length: 7 }, (_, index) => ({
        phase: "cold",
        sample_index: index + 1,
      })),
    ];
    if (!Array.isArray(profile.samples) || profile.samples.length !== 8) {
      issues.push(`performance sample count mismatch for ${profile.profile_id}`);
      continue;
    }
    profile.samples.forEach((sample, index) => {
      const expected = expectedSampleOrder[index];
      if (
        sample.phase !== expected.phase
        || sample.sample_index !== expected.sample_index
        || sample.status !== "complete"
        || sample.error !== null
        || ![
          sample.lcp_ms,
          sample.cls,
          sample.inp_interaction_proxy_ms,
          sample.map_ready_after_interaction_ms,
        ].every(Number.isFinite)
      ) {
        issues.push(`performance sample invalid ${profile.profile_id} index ${index}`);
      }
    });
    const recomputed = recomputePerformanceProfile(profile, protocol);
    const viewport = protocol.viewports.find((item) => item.id === profile.profile_id);
    const expectedThrottling = {
      cpu_rate: protocol.performance.cpu_throttling_rate,
      network: protocol.performance.network,
      cache_disabled: protocol.performance.cache_disabled_for_cold_samples,
    };
    if (
      JSON.stringify(profile.viewport)
        !== JSON.stringify({ width: viewport.width, height: viewport.height })
      || JSON.stringify(profile.throttling) !== JSON.stringify(expectedThrottling)
      || JSON.stringify(profile.thresholds)
        !== JSON.stringify(protocol.performance.thresholds[profile.profile_id])
      || JSON.stringify(profile.cold_p75) !== JSON.stringify(recomputed.p75)
      || JSON.stringify(profile.checks) !== JSON.stringify(recomputed.checks)
      || profile.qualified !== recomputed.qualified
    ) {
      issues.push(`performance derivation mismatch ${profile.profile_id}`);
    }
  }
  if (
    performance?.aggregation !== protocol.performance.aggregation
    || performance?.qualified !== profiles.every((profile) => profile.qualified)
  ) {
    issues.push("performance aggregate mismatch");
  }
  return issues;
}

function validateMapEvidence(row, state, protocol) {
  const issues = [];
  const evidence = row.map_evidence;
  const applicable = protocol.map_parity.applicable_state_ids.includes(state.id);
  const key = `${row.state_id}::${row.viewport_id}`;
  if (!evidence || typeof evidence !== "object") {
    return [`map evidence missing ${key}`];
  }
  if (!applicable) {
    const nullFields = [
      "pagination",
      "map_surface_present",
      "expected_response_record_ids",
      "rendered_accessible_list_record_ids",
      "rendered_map_feature_or_marker_record_ids",
      "rendered_accessible_list_records",
      "rendered_map_feature_or_marker_records",
      "unresolved_accessible_list_entries",
      "unresolved_map_feature_or_marker_entries",
      "detail_integrity",
      "marker_placement_sanity",
      "map_list_parity",
    ];
    if (
      evidence.applicability !== "not_applicable"
      || evidence.collection_status !== "not_applicable"
      || evidence.reason !== "state_not_in_map_parity_roster"
      || nullFields.some((field) => evidence[field] !== null)
    ) {
      issues.push(`invalid not-applicable map evidence ${key}`);
    }
    if (
      row.status === "complete"
      && [
        "map_list_parity",
        "map_detail_integrity",
        "map_marker_placement_sanity",
      ].some((check) => row.checks?.[check] !== "not_applicable")
    ) {
      issues.push(`map checks must be not_applicable ${key}`);
    }
    return issues;
  }

  const expectedIds = expectedMapResponseRecordIds(state);
  const expectedRecords = expectedMapResponseRecords(state);
  const expectedPagination = {
    mode: protocol.map_parity.pagination_mode,
    response_complete_roster: protocol.map_parity.response_complete_roster,
    rendered_complete_roster_required:
      protocol.map_parity.allow_rendered_roster_truncation === false,
    map_surface_required: expectedIds.length > 0,
    expected_total_records: expectedIds.length,
  };
  if (evidence.applicability !== "applicable") {
    issues.push(`map evidence applicability mismatch ${key}`);
  }
  if (JSON.stringify(evidence.pagination) !== JSON.stringify(expectedPagination)) {
    issues.push(`map pagination declaration mismatch ${key}`);
  }
  if (JSON.stringify(evidence.expected_response_record_ids) !== JSON.stringify(expectedIds)) {
    issues.push(`expected map response roster mismatch ${key}`);
  }
  for (const field of [
    "rendered_accessible_list_record_ids",
    "rendered_map_feature_or_marker_record_ids",
    "rendered_accessible_list_records",
    "rendered_map_feature_or_marker_records",
    "unresolved_accessible_list_entries",
    "unresolved_map_feature_or_marker_entries",
  ]) {
    if (!Array.isArray(evidence[field])) issues.push(`map evidence ${field} missing ${key}`);
  }
  const recomputed = recomputeMapListParity(evidence);
  if (typeof evidence.map_list_parity !== "boolean" || evidence.map_list_parity !== recomputed) {
    issues.push(`map parity recomputation mismatch ${key}`);
  }
  const recomputedDetailIntegrity = recomputeMapDetailIntegrity(
    evidence,
    expectedRecords,
  );
  if (
    typeof evidence.detail_integrity !== "boolean"
    || evidence.detail_integrity !== recomputedDetailIntegrity
  ) {
    issues.push(`map detail integrity mismatch ${key}`);
  }
  const recomputedPlacement = recomputeMarkerPlacementSanity(evidence);
  if (
    JSON.stringify(evidence.marker_placement_sanity)
      !== JSON.stringify(recomputedPlacement)
  ) {
    issues.push(`map marker placement derivation mismatch ${key}`);
  }
  if (row.status === "complete") {
    if (row.checks?.map_list_parity !== recomputed) {
      issues.push(`map parity qualification check mismatch ${key}`);
    }
    if (row.checks?.map_detail_integrity !== recomputedDetailIntegrity) {
      issues.push(`map detail qualification check mismatch ${key}`);
    }
    if (
      row.checks?.map_marker_placement_sanity
      !== recomputedPlacement?.sanity_passed
    ) {
      issues.push(`map marker placement check mismatch ${key}`);
    }
    if (
      [recomputed, recomputedDetailIntegrity, recomputedPlacement?.sanity_passed]
        .some((value) => value !== true)
      && row.qualified !== false
    ) {
      issues.push(`map evidence failure did not fail row qualification ${key}`);
    }
  }
  return issues;
}

export function validateReportStructure(report, protocol) {
  const issues = [];
  if (report.schema_version !== "firelens.frontend_surface_report.v1") {
    issues.push("unsupported report schema");
  }
  if (report.protocol_id !== protocol.protocol_id) issues.push("protocol_id mismatch");
  issues.push(...validateExecutionEnvironment(report.execution_environment, protocol));
  const expected = expectedPairs(protocol);
  const observed = new Set();
  if (!Array.isArray(report.surface_rows)) {
    issues.push("surface_rows missing");
  } else {
    for (const row of report.surface_rows) {
      const key = `${row.state_id}::${row.viewport_id}`;
      const state = protocol.states.find((item) => item.id === row.state_id);
      const viewport = protocol.viewports.find((item) => item.id === row.viewport_id);
      if (observed.has(key)) issues.push(`duplicate surface row ${key}`);
      observed.add(key);
      if (state) issues.push(...validateMapEvidence(row, state, protocol));
      if (!["complete", "error"].includes(row.status)) {
        issues.push(`invalid surface row status ${key}`);
      }
      if (row.status === "complete") {
        if (
          !row.screenshot
          || typeof row.screenshot.path !== "string"
          || path.isAbsolute(row.screenshot.path)
          || row.screenshot.path.split(/[\\/]/).includes("..")
          || !row.screenshot.path.endsWith(".png")
          || !/^[a-f0-9]{64}$/.test(row.screenshot.sha256 ?? "")
          || !Number.isInteger(row.screenshot.bytes)
          || row.screenshot.bytes < 1
          || row.screenshot.format !== "png"
          || row.screenshot.signature_hex !== "89504e470d0a1a0a"
          || !viewport
          || row.screenshot.width_px
            !== viewport.width * viewport.device_scale_factor
          || row.screenshot.height_px
            < viewport.height * viewport.device_scale_factor
          || row.screenshot.height_px
            > 20 * viewport.height * viewport.device_scale_factor
        ) {
          issues.push(`invalid screenshot evidence ${key}`);
        }
        if (
          !row.axe
          || !row.layout
          || !row.map_evidence
          || !row.runtime
          || !row.checks
          || typeof row.qualified !== "boolean"
        ) {
          issues.push(`incomplete surface evidence ${key}`);
        }
        if (
          !Array.isArray(row.runtime?.console_errors)
          || !Array.isArray(row.runtime?.expected_console_errors)
          || !Array.isArray(row.runtime?.unexpected_console_errors)
          || !Array.isArray(row.runtime?.expected_http_failures)
        ) {
          issues.push(`incomplete console evidence ${key}`);
        }
        issues.push(...validateAxeEvidence(row, protocol));
        issues.push(...validateRequestRuntime(row, protocol));
      }
    }
    for (const key of expected) {
      if (!observed.has(key)) issues.push(`missing surface row ${key}`);
    }
    for (const key of observed) {
      if (!expected.has(key)) issues.push(`unknown surface row ${key}`);
    }
  }
  issues.push(...validateFunctionalJourneys(report.functional_journeys, protocol));
  issues.push(...validatePerformance(report.performance, protocol));
  return issues;
}

function gitCommit() {
  const result = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: repositoryRoot,
    encoding: "utf8",
  });
  return result.status === 0 ? result.stdout.trim() : null;
}

async function buildIdentity() {
  const indexPath = path.join(frontendRoot, "dist/client/index.html");
  const manifestPath = path.join(frontendRoot, "dist/client/.vite/manifest.json");
  return {
    commit: gitCommit(),
    index_sha256: await fileSha256(indexPath),
    manifest_sha256: await fileSha256(manifestPath),
  };
}

function normalizedText(value) {
  return String(value ?? "").trim().replace(/\s+/g, " ");
}

function viewportExecutionProfile(protocol, viewport) {
  return {
    viewport_id: viewport.id,
    viewport: { width: viewport.width, height: viewport.height },
    device_scale_factor: viewport.device_scale_factor,
    is_mobile: viewport.is_mobile,
    color_scheme: protocol.execution_environment.color_scheme,
    reduced_motion: protocol.execution_environment.reduced_motion,
    locale: protocol.execution_environment.locale,
    timezone_id: protocol.execution_environment.timezone_id,
  };
}

function unthrottledRunProfile(protocol, viewport) {
  return {
    ...viewportExecutionProfile(protocol, viewport),
    cpu_throttling: { mode: "none", rate: 1 },
    network: {
      mode: "local_preview_with_deterministic_routes",
      cache_policy: "fresh_browser_context_default",
    },
  };
}

export function configuredExecutionRunProfiles(protocol) {
  const desktop = protocol.viewports.find((viewport) => viewport.id === "desktop");
  return {
    surface_matrix: protocol.viewports.map((viewport) => (
      unthrottledRunProfile(protocol, viewport)
    )),
    functional_journeys: protocol.functional_journeys.map((journey) => ({
      journey_id: journey.id,
      ...unthrottledRunProfile(protocol, desktop),
    })),
    performance: protocol.performance.profiles.map((profileId) => {
      const viewport = protocol.viewports.find((item) => item.id === profileId);
      return {
        profile_id: profileId,
        ...viewportExecutionProfile(protocol, viewport),
        cpu_throttling: {
          mode: "cdp_emulation",
          rate: protocol.performance.cpu_throttling_rate,
        },
        network: {
          mode: "cdp_emulation",
          latency_ms: protocol.performance.network.latency_ms,
          download_bytes_per_second:
            protocol.performance.network.download_bytes_per_second,
          upload_bytes_per_second:
            protocol.performance.network.upload_bytes_per_second,
          connection_type: protocol.performance.network.connection_type,
          cache_disabled: protocol.performance.cache_disabled_for_cold_samples,
        },
      };
    }),
  };
}

function npmVersion() {
  const result = spawnSync("npm", ["--version"], { encoding: "utf8" });
  return result.status === 0 ? normalizedText(result.stdout) : null;
}

async function executionEnvironment(protocol, browser) {
  const playwrightPackage = JSON.parse(await readFile(
    path.join(frontendRoot, "node_modules/@playwright/test/package.json"),
    "utf8",
  ));
  const processors = os.cpus();
  return {
    os: {
      name: normalizedText(os.type()).toLowerCase(),
      release: normalizedText(os.release()),
      architecture: normalizedText(os.arch()),
      cpu_model: normalizedText(processors[0]?.model),
      logical_cpu_count: processors.length,
    },
    runtime: {
      node_version: normalizedText(process.versions.node),
      npm_version: npmVersion(),
      playwright_package_version: normalizedText(playwrightPackage.version),
    },
    browser: {
      name: protocol.execution_environment.browser_name,
      version: normalizedText(browser.version()),
      headless: protocol.execution_environment.headless,
      locale: protocol.execution_environment.locale,
      timezone_id: protocol.execution_environment.timezone_id,
    },
    run_profiles: configuredExecutionRunProfiles(protocol),
  };
}

function hasExactKeys(value, keys) {
  return (
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort())
  );
}

function validateExecutionEnvironment(environment, protocol) {
  const issues = [];
  if (!hasExactKeys(environment, ["os", "runtime", "browser", "run_profiles"])) {
    return ["execution_environment shape mismatch"];
  }
  if (!hasExactKeys(
    environment.os,
    ["name", "release", "architecture", "cpu_model", "logical_cpu_count"],
  )) {
    issues.push("execution_environment os identity mismatch");
  } else if (
    ["name", "release", "architecture", "cpu_model"].some(
      (field) => !environment.os[field]
        || environment.os[field] !== normalizedText(environment.os[field]),
    )
    || !Number.isInteger(environment.os.logical_cpu_count)
    || environment.os.logical_cpu_count < 1
  ) {
    issues.push("execution_environment os values invalid");
  }
  if (!hasExactKeys(
    environment.runtime,
    ["node_version", "npm_version", "playwright_package_version"],
  ) || [
    environment.runtime?.node_version,
    environment.runtime?.npm_version,
    environment.runtime?.playwright_package_version,
  ].some((value) => typeof value !== "string" || !/^\d+\.\d+\.\d+/.test(value))) {
    issues.push("execution_environment runtime identity invalid");
  }
  const expectedBrowser = {
    name: protocol.execution_environment.browser_name,
    headless: protocol.execution_environment.headless,
    locale: protocol.execution_environment.locale,
    timezone_id: protocol.execution_environment.timezone_id,
  };
  if (
    !hasExactKeys(
      environment.browser,
      ["name", "version", "headless", "locale", "timezone_id"],
    )
    || !environment.browser.version
    || Object.entries(expectedBrowser).some(
      ([field, expected]) => environment.browser[field] !== expected,
    )
  ) {
    issues.push("execution_environment browser identity mismatch");
  }
  if (
    JSON.stringify(environment.run_profiles)
    !== JSON.stringify(configuredExecutionRunProfiles(protocol))
  ) {
    issues.push("execution_environment run profile mismatch");
  }
  return issues;
}

async function waitForPreview(baseUrl, server, logs) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Vite preview exited early (${server.exitCode}): ${logs.join("")}`);
    }
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      // Retry until the bounded deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Vite preview did not become ready at ${baseUrl}`);
}

async function startPreview(baseUrl) {
  const parsed = new URL(baseUrl);
  const viteBin = path.join(frontendRoot, "node_modules/vite/bin/vite.js");
  const logs = [];
  const server = spawn(process.execPath, [
    viteBin,
    "preview",
    "--host",
    parsed.hostname,
    "--port",
    parsed.port,
    "--strictPort",
  ], {
    cwd: frontendRoot,
    stdio: ["ignore", "pipe", "pipe"],
  });
  for (const stream of [server.stdout, server.stderr]) {
    stream.on("data", (chunk) => {
      logs.push(String(chunk));
      if (logs.length > 50) logs.shift();
    });
  }
  await waitForPreview(baseUrl, server, logs);
  return server;
}

async function stopPreview(server) {
  if (server.exitCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => server.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 2_000)),
  ]);
}

async function writeReport(report, outputDirectory) {
  await mkdir(outputDirectory, { recursive: true });
  const output = path.join(outputDirectory, "report.json");
  const temporary = `${output}.tmp`;
  await writeFile(temporary, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await rename(temporary, output);
  return output;
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const protocol = await loadProtocol(options.protocolPath);
  await readFile(path.join(frontendRoot, "dist/client/index.html"));
  const server = await startPreview(options.baseUrl);
  const browser = await chromium.launch({ headless: true });
  let report;
  try {
    const surfaceRows = await runSurfaceMatrix(
      browser,
      protocol,
      options.outputDirectory,
      options.baseUrl,
    );
    const functionalJourneys = await runFunctionalJourneys(
      browser,
      protocol,
      options.baseUrl,
    );
    const performance = await runPerformance(browser, protocol, options.baseUrl);
    report = {
      schema_version: "firelens.frontend_surface_report.v1",
      generated_at: new Date().toISOString(),
      protocol_id: protocol.protocol_id,
      protocol_sha256: await fileSha256(options.protocolPath),
      protocol_status: protocol.status,
      protocol_frozen_at: protocol.frozen_at,
      base_url: options.baseUrl,
      execution_environment: await executionEnvironment(protocol, browser),
      browser: {
        name: "chromium",
        version: browser.version(),
      },
      build: await buildIdentity(),
      surface_rows: surfaceRows,
      functional_journeys: functionalJourneys,
      performance,
    };
    const structureIssues = validateReportStructure(report, protocol);
    const matrixComplete = surfaceMatrixComplete(surfaceRows, protocol);
    const surfaceQualified = matrixComplete && surfaceRows.every((row) => row.qualified);
    const journeysQualified = functionalJourneys.every((journey) => journey.qualified);
    report.summary = {
      protocol_ratified: protocol.status === "ratified" && Boolean(protocol.frozen_at),
      expected_surface_rows: protocol.matrix.expected_rows,
      executed_surface_rows: surfaceRows.length,
      matrix_complete: matrixComplete,
      qualified_surface_rows: surfaceRows.filter((row) => row.qualified).length,
      functional_journeys_qualified: journeysQualified,
      performance_qualified: performance.qualified,
      structure_issues: structureIssues,
      qualified: (
        protocol.status === "ratified"
        && Boolean(protocol.frozen_at)
        && structureIssues.length === 0
        && surfaceQualified
        && journeysQualified
        && performance.qualified
      ),
    };
    const output = await writeReport(report, options.outputDirectory);
    process.stdout.write(`${JSON.stringify({
      output: relativeArtifact(output),
      ...report.summary,
    }, null, 2)}\n`);
  } finally {
    await browser.close();
    await stopPreview(server);
  }
  process.exitCode = report.summary.qualified ? 0 : 2;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${String(error?.stack ?? error)}\n`);
    process.exitCode = 1;
  });
}
