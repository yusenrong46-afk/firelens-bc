"use strict";

const state = {
  token: null,
  context: null,
  progress: null,
  presentation: null,
  acknowledged: false,
};

const byId = (id) => document.getElementById(id);

function announce(message, error = false) {
  const region = byId("status-message");
  region.textContent = message;
  region.classList.toggle("error", error);
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function textElement(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, options = {}) {
  if (!state.token) throw new Error("Load your capability before using the review service.");
  const method = options.method || "GET";
  const headers = { Authorization: `Bearer ${state.token}` };
  if (method !== "GET") headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "same-origin",
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "The review service refused the request.");
  return payload;
}

function renderSimpleList(id, values, emptyText = "None") {
  const list = byId(id);
  clearChildren(list);
  const rows = values && values.length ? values : [emptyText];
  rows.forEach((value) => list.appendChild(textElement("li", value)));
}

function renderHistory(history) {
  const section = byId("history-section");
  const list = byId("history-list");
  clearChildren(list);
  section.hidden = !history.length;
  history.forEach((turn) => {
    const row = document.createElement("li");
    row.appendChild(textElement("strong", turn.role === "user" ? "User" : "Assistant"));
    row.appendChild(textElement("p", turn.content));
    list.appendChild(row);
  });
}

function renderClaims(claims) {
  const section = byId("claims-section");
  const list = byId("claims-list");
  clearChildren(list);
  section.hidden = !claims.length;
  claims.forEach((claim) => {
    const row = document.createElement("li");
    row.appendChild(textElement("p", claim.claim_id, "evidence-label"));
    row.appendChild(textElement("p", claim.text, "claim-text"));
    list.appendChild(row);
  });
}

function renderSources(sources) {
  const section = byId("sources-section");
  const list = byId("sources-list");
  clearChildren(list);
  section.hidden = !sources.length;
  sources.forEach((source) => {
    const row = document.createElement("li");
    row.appendChild(textElement("p", source.context_id, "evidence-label"));
    const metadata = [source.title, source.publisher, source.locator].filter(Boolean).join(" · ");
    if (metadata) row.appendChild(textElement("p", metadata, "source-meta"));
    row.appendChild(textElement("p", source.text, "source-text"));
    list.appendChild(row);
  });
}

function summarizeDecision(decision) {
  const details = [`Disposition: ${decision.disposition.replaceAll("_", " ")}`];
  Object.entries(decision).forEach(([key, value]) => {
    if (typeof value === "boolean") details.push(`${key.replaceAll("_", " ")}: ${value ? "yes" : "no"}`);
  });
  if (decision.notes) details.push(`Notes: ${decision.notes}`);
  return details.join(" · ");
}

function renderPriorReview(material) {
  const section = byId("prior-review-section");
  const list = byId("prior-review-list");
  clearChildren(list);
  section.hidden = !material.length;
  material.forEach((entry) => {
    const block = document.createElement("section");
    block.className = "claim-decision";
    block.appendChild(textElement("h4", entry.reviewer_slot.replace("-", " ")));
    block.appendChild(textElement("p", summarizeDecision(entry.decision)));
    list.appendChild(block);
  });
}

function checkbox(id, labelText) {
  const label = document.createElement("label");
  label.className = "check-row";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = id;
  label.appendChild(input);
  label.appendChild(document.createTextNode(labelText));
  return label;
}

function buildDecisionForm() {
  const checks = byId("decision-checks");
  clearChildren(checks);
  const retrieval = state.context.review_kind === "retrieval";
  const definitions = retrieval
    ? [
        ["question-is-independent", "The question was independently authored after configuration freeze."],
        ["answerability-correct", "The answerability label is correct."],
        ["acceptable-evidence-correct", "The declared acceptable evidence is correct."],
      ]
    : [
        ["required-concepts-present", "All required concepts are present."],
        ["forbidden-claims-absent", "All forbidden claims are absent."],
        ["required-limitations-present", "All required limitations are present."],
      ];
  const fieldset = document.createElement("fieldset");
  fieldset.appendChild(textElement("legend", retrieval ? "Retrieval-label checks" : "Semantic rubric checks"));
  definitions.forEach(([id, label]) => fieldset.appendChild(checkbox(id, label)));
  checks.appendChild(fieldset);

  const claimFieldset = byId("claim-decisions");
  const claimList = byId("claim-decision-list");
  clearChildren(claimList);
  const claims = state.presentation.payload.claims;
  claimFieldset.hidden = retrieval || !claims.length;
  claims.forEach((claim) => {
    const row = document.createElement("div");
    row.className = "claim-decision";
    row.dataset.claimId = claim.claim_id;
    row.appendChild(textElement("p", `${claim.claim_id} · ${claim.text}`));
    const grid = document.createElement("div");
    grid.className = "claim-decision-grid";
    const selectLabel = document.createElement("label");
    selectLabel.textContent = "Assessment";
    const select = document.createElement("select");
    select.required = true;
    select.className = "claim-outcome";
    [
      ["", "Choose"],
      ["supported", "Supported"],
      ["unsupported", "Unsupported"],
      ["unclear", "Unclear"],
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
    selectLabel.appendChild(select);
    const notesLabel = document.createElement("label");
    notesLabel.textContent = "Claim notes";
    const notes = document.createElement("textarea");
    notes.className = "claim-notes";
    notes.maxLength = 4000;
    notes.rows = 3;
    notesLabel.appendChild(notes);
    grid.append(selectLabel, notesLabel);
    row.appendChild(grid);
    claimList.appendChild(row);
  });
  byId("disposition").value = "";
  byId("decision-notes").value = "";
}

function renderPresentation(presentation, acknowledged) {
  state.presentation = presentation;
  state.acknowledged = acknowledged;
  const payload = presentation.payload;
  byId("case-view").hidden = false;
  byId("case-position").textContent = `Case ${presentation.case_position} of ${state.progress.case_count}`;
  byId("case-id").textContent = presentation.case_id;
  byId("question-text").textContent = payload.question;
  renderHistory(payload.history);
  renderSimpleList("required-concepts", payload.rubric.required_concepts);
  renderSimpleList("forbidden-claims", payload.rubric.forbidden_claims);
  renderSimpleList("required-limitations", payload.rubric.required_limitations);
  byId("answer-section").hidden = payload.answer === null;
  byId("answer-text").textContent = payload.answer || "";
  renderClaims(payload.claims);
  renderSources(payload.local_source_context);
  renderPriorReview(presentation.review_material);
  buildDecisionForm();
  byId("acknowledgement-bar").hidden = acknowledged;
  byId("decision-form").hidden = !acknowledged;
  byId("case-view").scrollIntoView({ block: "start" });
}

function updateControls() {
  const progress = state.progress;
  byId("progress-count").textContent = `${progress.completed_case_count} / ${progress.case_count}`;
  byId("actor-state").textContent = progress.actor_state.replaceAll("_", " ");
  byId("open-case").hidden = progress.actor_state !== "awaiting_presentation";
  byId("lock-review").hidden = progress.actor_state !== "complete_pending_lock" || state.context.actor_role !== "reviewer";
  byId("finalize-review").hidden = progress.actor_state !== "complete_pending_lock" || state.context.actor_role !== "adjudicator";
  const guidance = {
    blocked_on_reviewer_locks: "Waiting for both independent reviewer journals to lock.",
    awaiting_presentation: "Open the next assigned case when you are ready.",
    awaiting_display_acknowledgement: "Read the complete open case before acknowledging it.",
    awaiting_decision: "Submit the irreversible decision for the open case.",
    complete_pending_lock: state.context.actor_role === "adjudicator" ? "All cases decided. Finalize adjudication." : "All cases decided. Lock your journal.",
    locked: "Your independent review journal is locked.",
    finalized: "This adjudication session is finalized.",
  };
  byId("action-guidance").textContent = guidance[progress.actor_state] || "Review state loaded.";
}

async function refresh() {
  state.progress = await api("/api/v1/review/progress");
  updateControls();
  if (["awaiting_display_acknowledgement", "awaiting_decision"].includes(state.progress.actor_state)) {
    const presentation = await api("/api/v1/review/current");
    renderPresentation(presentation, state.progress.actor_state === "awaiting_decision");
  } else if (!["awaiting_decision", "awaiting_display_acknowledgement"].includes(state.progress.actor_state)) {
    state.presentation = null;
    byId("case-view").hidden = true;
  }
}

async function loadCapability() {
  const file = byId("capability-file").files[0];
  if (!file) throw new Error("Choose your assigned capability JSON file.");
  const capability = JSON.parse(await file.text());
  if (
    capability.capability_version !== "firelens_review_actor_capability.v1" ||
    typeof capability.token !== "string" || capability.token.length < 43
  ) throw new Error("The selected file is not a valid review capability.");
  state.token = capability.token;
  try {
    state.context = await api("/api/v1/review/context");
    if (state.context.actor_id !== capability.actor_id || state.context.session_id !== capability.session_id) {
      throw new Error("The capability does not match this review session.");
    }
    byId("actor-name").textContent = state.context.actor_display_name;
    byId("actor-role").textContent = state.context.actor_role.replaceAll("_", " ");
    byId("access-panel").hidden = true;
    byId("desk").hidden = false;
    await refresh();
    announce("Private capability accepted. Your assigned review state is ready.");
  } catch (error) {
    state.token = null;
    state.context = null;
    throw error;
  }
}

async function openCase() {
  const presentation = await api("/api/v1/review/present", { method: "POST", body: {} });
  state.progress = await api("/api/v1/review/progress");
  updateControls();
  renderPresentation(presentation, false);
  announce(`Opened case ${presentation.case_position}.`);
}

async function acknowledgeDisplay() {
  await api("/api/v1/review/acknowledge", {
    method: "POST",
    body: { presentation_id: state.presentation.presentation_id },
  });
  state.acknowledged = true;
  byId("acknowledgement-bar").hidden = true;
  byId("decision-form").hidden = false;
  byId("decision-form").scrollIntoView({ block: "start" });
  announce("Display acknowledged. The irreversible decision form is enabled.");
}

function decisionPayload() {
  const retrieval = state.context.review_kind === "retrieval";
  const claimRows = [...document.querySelectorAll(".claim-decision[data-claim-id]")];
  return {
    disposition: byId("disposition").value,
    required_concepts_present: retrieval ? null : byId("required-concepts-present").checked,
    forbidden_claims_absent: retrieval ? null : byId("forbidden-claims-absent").checked,
    required_limitations_present: retrieval ? null : byId("required-limitations-present").checked,
    question_is_independent: retrieval ? byId("question-is-independent").checked : null,
    answerability_correct: retrieval ? byId("answerability-correct").checked : null,
    acceptable_evidence_correct: retrieval ? byId("acceptable-evidence-correct").checked : null,
    claims: retrieval ? [] : claimRows.map((row) => ({
      claim_id: row.dataset.claimId,
      decision: row.querySelector(".claim-outcome").value,
      notes: row.querySelector(".claim-notes").value,
    })),
    notes: byId("decision-notes").value,
  };
}

async function submitDecision(event) {
  event.preventDefault();
  if (!byId("decision-form").reportValidity()) return;
  if (!window.confirm("Submit this irreversible case decision? It cannot be edited or reopened.")) return;
  await api("/api/v1/review/decision", {
    method: "POST",
    body: { presentation_id: state.presentation.presentation_id, decision: decisionPayload() },
  });
  announce("Decision recorded and receipt-bound.");
  await refresh();
}

async function completeSession(action) {
  const label = action === "lock" ? "lock your completed reviewer journal" : "finalize adjudication";
  if (!window.confirm(`Irreversibly ${label}?`)) return;
  await api(`/api/v1/review/${action}`, { method: "POST", body: {} });
  announce(action === "lock" ? "Reviewer journal locked." : "Adjudication finalized.");
  await refresh();
}

function withErrors(handler) {
  return async (...args) => {
    try { await handler(...args); }
    catch (error) { announce(error.message || "The review action failed.", true); }
  };
}

byId("load-capability").addEventListener("click", withErrors(loadCapability));
byId("open-case").addEventListener("click", withErrors(openCase));
byId("acknowledge-display").addEventListener("click", withErrors(acknowledgeDisplay));
byId("decision-form").addEventListener("submit", withErrors(submitDecision));
byId("lock-review").addEventListener("click", withErrors(() => completeSession("lock")));
byId("finalize-review").addEventListener("click", withErrors(() => completeSession("finalize")));
