"use strict";

const campaignState = {items: [], current: null, step: "M1"};

const CAMPAIGN_STATUS = {
  draft: "Draft",
  pending_approval: "Pending Review",
  approved: "Approved",
  executing: "In Progress",
  completed: "Completed",
  archived: "Archived",
};

function campaignEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function campaignList(value) {
  return String(value || "").split(/[,\n]/).map(item => item.trim()).filter(Boolean);
}

function campaignLines(value) {
  return String(value || "").split("\n").map(item => item.trim()).filter(Boolean);
}

async function campaignRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (window.__KOL_SESSION_TOKEN__) headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let message = `Request failed ${response.status}`;
    let issues = [];
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (data.detail) {
        message = data.detail.message || message;
        issues = data.detail.issues || [];
      }
    } catch (_) { /* use fallback */ }
    const error = new Error(message);
    error.issues = issues;
    throw error;
  }
  return response.json();
}

function initCampaignModule() {
  document.getElementById("campaign-new")?.addEventListener("click", () => {
    campaignState.current = null;
    showCampaignStep("M2", true);
  });
  document.querySelectorAll("[data-campaign-step]").forEach(button => {
    button.addEventListener("click", () => showCampaignStep(button.dataset.campaignStep));
  });
}

function updateCampaignContext() {
  const node = document.getElementById("campaign-context");
  const project = campaignState.current;
  if (!project) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.innerHTML = `
    <div><strong>${campaignEscape(project.project_name)}</strong><span>${campaignEscape(project.campaign_id)}</span></div>
    <div><span>${campaignEscape(project.brand)} · ${campaignEscape(project.vehicle_model)}</span><span>${project.markets.map(m => campaignEscape(m)).join(" / ")}</span></div>
    <div><span class="campaign-status status-${campaignEscape(project.status)}">${CAMPAIGN_STATUS[project.status] || project.status}</span><span>Current V${project.current_version}${project.approved_version ? ` · Approved V${project.approved_version}` : ""}</span></div>`;
}

function showCampaignStep(step, creating = false) {
  campaignState.step = step;
  document.querySelectorAll("[data-campaign-step]").forEach(button => {
    button.classList.toggle("active", button.dataset.campaignStep === step);
  });
  updateCampaignContext();
  if (step === "M1") return renderCampaignList();
  if (creating && step === "M2") return renderCampaignBasic(null);
  if (!campaignState.current) {
    document.getElementById("campaign-panel").innerHTML = `
      <div class="empty-page"><div><h2>Select a campaign first</h2><p>Open a campaign from the M1 overview to continue.</p><button class="tb-btn teal" id="campaign-back-list" type="button">Back to campaign overview</button></div></div>`;
    document.getElementById("campaign-back-list").addEventListener("click", () => showCampaignStep("M1"));
    return;
  }
  if (step === "M2") renderCampaignBasic(campaignState.current);
  if (step === "M3") renderCampaignStrategy();
  if (step === "M4") renderCampaignMeasurement();
  if (step === "M5") renderCampaignRequirements();
  if (step === "M6") renderCampaignApproval().catch(error => showStatus(error.message, true));
}

async function loadCampaigns(query = "") {
  const data = await campaignRequest(`/campaigns${query}`);
  campaignState.items = data.items;
  if (campaignState.step === "M1") renderCampaignList();
  return data;
}

function renderCampaignList() {
  const panel = document.getElementById("campaign-panel");
  const items = campaignState.items;
  const count = status => items.filter(item => item.status === status).length;
  panel.innerHTML = `
    <div class="metrics campaign-metrics">
      <article class="metric-card"><span>Total campaigns</span><strong>${items.length}</strong><small>Current filtered results</small></article>
      <article class="metric-card"><span>Drafts</span><strong>${count("draft")}</strong><small>Configuration still needs to be completed</small></article>
      <article class="metric-card"><span>Pending review</span><strong>${count("pending_approval")}</strong><small>Awaiting a decision</small></article>
      <article class="metric-card"><span>Approved</span><strong>${count("approved")}</strong><small>Ready to publish downstream handoffs</small></article>
    </div>
    <form id="campaign-filter" class="filter-bar">
      <input name="q" placeholder="Search by campaign name or ID">
      <select name="brand"><option value="">Allbrand</option><option>BYD</option><option>XPENG</option></select>
      <select name="market"><option value="">All markets</option><option value="DE">Germany DE</option><option value="GB">United Kingdom GB</option></select>
      <select name="status"><option value="">All statuses</option><option value="draft">Draft</option><option value="pending_approval">Pending review</option><option value="approved">Approved</option></select>
      <button class="tb-btn" type="submit">Filter</button>
      <button class="tb-btn" id="campaign-filter-reset" type="button">Reset</button>
    </form>
    <article class="content-card">
      <div class="card-hd"><h2>Campaigns <span class="count">${items.length}</span></h2><span class="campaign-muted">Showing active campaigns only</span></div>
      <div class="table-wrap"><table class="campaign-table"><thead><tr><th>Campaign</th><th>Brand & Market</th><th>Budget</th><th>Status</th><th>Version</th><th>Owner</th><th>Actions</th></tr></thead><tbody id="campaign-list-body"></tbody></table></div>
      ${items.length ? "" : '<div class="empty-state">No campaigns yet. Select “New Campaign” above to begin setup.</div>'}
    </article>`;
  const body = document.getElementById("campaign-list-body");
  items.forEach(item => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${campaignEscape(item.project_name)}</strong><small>${campaignEscape(item.campaign_id)}</small></td>
      <td>${campaignEscape(item.brand)} · ${campaignEscape(item.vehicle_model)}<small>${item.markets.map(m => campaignEscape(m)).join(" / ")}</small></td>
      <td>${new Intl.NumberFormat("en-US").format(item.budget_total)} ${campaignEscape(item.currency)}</td>
      <td><span class="campaign-status status-${campaignEscape(item.status)}">${CAMPAIGN_STATUS[item.status] || item.status}</span></td>
      <td>V${item.current_version}<small>Completeness ${item.completion}%</small></td>
      <td>${campaignEscape(item.owner)}</td>
      <td><button class="text-btn campaign-open" type="button">Open</button></td>`;
    row.querySelector(".campaign-open").addEventListener("click", () => openCampaign(item.campaign_id));
    body.append(row);
  });
  document.getElementById("campaign-filter").addEventListener("submit", event => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(event.currentTarget));
    [...params.keys()].forEach(key => { if (!params.get(key)) params.delete(key); });
    loadCampaigns(params.toString() ? `?${params}` : "").catch(error => showStatus(error.message, true));
  });
  document.getElementById("campaign-filter-reset").addEventListener("click", () => {
    loadCampaigns().catch(error => showStatus(error.message, true));
  });
}

async function openCampaign(campaignId, step = "M2") {
  campaignState.current = await campaignRequest(`/campaigns/${campaignId}`);
  showCampaignStep(step);
}

function campaignFormActions(label) {
  return `<div class="campaign-form-actions"><button class="tb-btn" data-back-m1 type="button">Back to overview</button><button class="tb-btn teal" type="submit">${label}</button></div>`;
}

function bindBackToList(panel) {
  panel.querySelector("[data-back-m1]")?.addEventListener("click", () => showCampaignStep("M1"));
}

function renderCampaignBasic(project) {
  const panel = document.getElementById("campaign-panel");
  const basic = project?.configuration?.basic || {};
  const isNew = !project;
  const markets = project?.markets || ["GB"];
  const milestones = basic.milestones || [];
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
    <div class="card-hd"><div><h2>M2 Campaign Details & Timeline</h2><p>${isNew ? "Complete the required fields to create a campaign draft." : "Drafts can be saved step by step. Editing an approved campaign creates a new version."}</p></div><span class="campaign-save-state">${isNew ? "Not created" : `Revision ${project.revision}`}</span></div>
      <form id="campaign-basic-form" class="campaign-form">
        <div class="campaign-form-grid">
          <label class="wide">Campaign name<input name="project_name" maxlength="100" required value="${campaignEscape(project?.project_name)}" placeholder="e.g., XPENG G6 test-drive reach in the United Kingdom"></label>
          <label>Client brand<select name="brand" required><option ${project?.brand === "BYD" ? "selected" : ""}>BYD</option><option ${project?.brand === "XPENG" || !project ? "selected" : ""}>XPENG</option></select></label>
          <label>Target vehicle model<input name="vehicle_model" required value="${campaignEscape(project?.vehicle_model)}" placeholder="e.g., G6"></label>
          <fieldset class="wide campaign-fieldset"><legend>Target markets</legend><label><input type="checkbox" name="markets" value="DE" ${markets.includes("DE") ? "checked" : ""}> Germany DE</label><label><input type="checkbox" name="markets" value="GB" ${markets.includes("GB") ? "checked" : ""}> United Kingdom GB</label></fieldset>
          <label>Primary market<select name="primary_market"><option value="DE" ${project?.primary_market === "DE" ? "selected" : ""}>Germany DE</option><option value="GB" ${project?.primary_market === "GB" || !project ? "selected" : ""}>United Kingdom GB</option></select></label>
          <label>Total budget<input name="budget_total" type="number" min="1" step="0.01" required value="${campaignEscape(project?.budget_total || 60000)}"></label>
          <label>Start date<input name="start_date" type="date" required value="${campaignEscape(project?.start_date)}"></label>
          <label>End date<input name="end_date" type="date" required value="${campaignEscape(project?.end_date)}"></label>
          <label>Campaign owner<input name="owner" required value="${campaignEscape(project?.owner)}"></label>
          <label>Collaborators<input name="collaborators" value="${campaignEscape((project?.collaborators || []).join(", "))}" placeholder="Separate with commas"></label>
          <label class="wide">Reach objectives<input name="objectives" value="${campaignEscape((project?.objectives || []).join(", "))}" placeholder="Awareness, product education, test drives, and lead generation"></label>
        </div>
        <div class="campaign-subsection"><div><h3>Key Milestones</h3><p>Format: milestone name | date | owner, one per line.</p></div></div>
    <textarea name="milestones" rows="5" placeholder="Campaign approval | 2026-10-02 | Campaign owner\nContent publication | 2026-11-01 | Content owner">${campaignEscape(milestones.map(item => `${item.name} | ${item.planned_date} | ${item.owner}`).join("\n"))}</textarea>
    ${campaignFormActions(isNew ? "Create Campaign Draft" : "Save Basic Information")}
      </form>
    </article>`;
  const form = document.getElementById("campaign-basic-form");
  bindBackToList(panel);
  form.addEventListener("submit", event => saveCampaignBasic(event, project));
}

function parseMilestones(text) {
  return campaignLines(text).map(line => {
    const [name, planned_date, owner] = line.split("｜").map(item => item?.trim());
    return {name, planned_date, owner, status: "pending"};
  }).filter(item => item.name && item.planned_date && item.owner);
}

async function saveCampaignBasic(event, project) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const payload = {
    project_name: data.get("project_name"),
    brand: data.get("brand"),
    vehicle_model: data.get("vehicle_model"),
    markets: data.getAll("markets"),
    primary_market: data.get("primary_market"),
    objectives: campaignList(data.get("objectives")),
    start_date: data.get("start_date"),
    end_date: data.get("end_date"),
    budget_total: Number(data.get("budget_total")),
    owner: data.get("owner"),
    collaborators: campaignList(data.get("collaborators")),
    milestones: parseMilestones(data.get("milestones")),
  };
  try {
    if (project) {
      payload.expected_revision = project.revision;
      campaignState.current = await campaignRequest(`/campaigns/${project.campaign_id}`, {method: "PATCH", body: JSON.stringify(payload)});
      showStatus("Campaign details saved.");
    } else {
      campaignState.current = await campaignRequest("/campaigns", {method: "POST", body: JSON.stringify(payload)});
  showStatus("Campaign draft created.");
    }
    await loadCampaigns();
    showCampaignStep("M3");
  } catch (error) { showStatus(error.message, true); }
}

function renderCampaignStrategy() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  const data = project.configuration.strategy || {};
  const audiences = (data.audiences || []).map(item => [item.name, item.market, item.language, item.purchase_stage, item.priority].join("｜")).join("\n");
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
      <div class="card-hd"><div><h2>M3 Target Audience & Content Strategy</h2><p>Define the audience, platforms, key messages, Call to Action (CTA), and compliance boundaries.</p></div><span class="campaign-save-state">Revision ${project.revision}</span></div>
      <form id="campaign-strategy-form" class="campaign-form">
        <label>Core Audiences <small>One per line: name | market code | language | decision stage | core/secondary/reach</small><textarea name="audiences" rows="5" placeholder="Urban UK families considering an EV | GB | English | Consideration | core">${campaignEscape(audiences)}</textarea></label>
        <div class="campaign-form-grid">
          <label>Target Platforms<input name="platforms" required value="${campaignEscape((data.platforms || []).join(", "))}" placeholder="YouTube, Instagram"></label>
          <label>Content Formats<input name="content_formats" required value="${campaignEscape((data.content_formats || []).join(", "))}" placeholder="In-depth test drive, short-form video"></label>
          <label class="wide">Required Messages<textarea name="message_pillars" rows="3" placeholder="One per line">${campaignEscape((data.message_pillars || []).join("\n"))}</textarea></label>
          <label class="wide">Prohibited Claims or Claims Requiring Legal Review<textarea name="prohibited_claims" rows="3" required placeholder="One per line">${campaignEscape((data.prohibited_claims || []).join("\n"))}</textarea></label>
          <label>Call to Action (CTA)<input name="cta" required value="${campaignEscape(data.cta)}" placeholder="Book a test drive"></label>
          <label>Risk & Compliance Reviewer<input name="risk_reviewer" required value="${campaignEscape(data.risk_reviewer)}"></label>
          <label class="wide">Paid Partnership Disclosure Requirements<textarea name="disclosure_rule" rows="2" required>${campaignEscape(data.disclosure_rule)}</textarea></label>
          <label>Content Usage Rights<input name="usage_rights_need" value="${campaignEscape(data.usage_rights_need)}"></label>
          <label>Competitor Exclusivity Requirements<input name="competitor_exclusivity" value="${campaignEscape(data.competitor_exclusivity)}"></label>
        </div>
        ${campaignFormActions("Save Audience & Content Strategy")}
      </form>
    </article>`;
  bindBackToList(panel);
  document.getElementById("campaign-strategy-form").addEventListener("submit", saveCampaignStrategy);
}

function parseAudiences(text) {
  return campaignLines(text).map(line => {
    const [name, market, language, purchase_stage, priority] = line.split("｜").map(item => item?.trim());
    return {name, market, language, purchase_stage, priority: priority || "core"};
  }).filter(item => item.name && item.market && item.language && item.purchase_stage);
}

async function saveCampaignStrategy(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const payload = {
    expected_revision: campaignState.current.revision,
    audiences: parseAudiences(data.get("audiences")),
    platforms: campaignList(data.get("platforms")),
    content_formats: campaignList(data.get("content_formats")),
    message_pillars: campaignLines(data.get("message_pillars")),
    prohibited_claims: campaignLines(data.get("prohibited_claims")),
    cta: data.get("cta"),
    disclosure_rule: data.get("disclosure_rule"),
    usage_rights_need: data.get("usage_rights_need") || null,
    competitor_exclusivity: data.get("competitor_exclusivity") || null,
    risk_reviewer: data.get("risk_reviewer"),
  };
  try {
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/strategy`, {method: "PUT", body: JSON.stringify(payload)});
    showStatus("Audience and content strategy saved.");
    showCampaignStep("M4");
  } catch (error) { showStatus(error.message, true); }
}

function metricRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-metric-row";
  row.innerHTML = `
    <input data-field="metric_code" placeholder="Metric code" value="${campaignEscape(item.metric_code)}">
    <input data-field="name" placeholder="Metric name" value="${campaignEscape(item.name)}">
    <input data-field="target_value" type="number" min="0" step="0.01" placeholder="Target value" value="${campaignEscape(item.target_value)}">
    <input data-field="unit" placeholder="Unit" value="${campaignEscape(item.unit)}">
    <input data-field="formula" placeholder="Definition or formula" value="${campaignEscape(item.formula)}">
    <input data-field="data_source" placeholder="Data Source" value="${campaignEscape(item.data_source)}">
    <input data-field="observation_window" placeholder="Observation window" value="${campaignEscape(item.observation_window)}">
    <input data-field="owner" placeholder="Owner" value="${campaignEscape(item.owner)}">
    <select data-field="refresh_frequency"><option ${item.refresh_frequency === "Daily" ? "selected" : ""}>Daily</option><option ${item.refresh_frequency === "Weekly" ? "selected" : ""}>Weekly</option><option ${item.refresh_frequency === "After campaign" ? "selected" : ""}>After campaign</option></select>
    <label class="campaign-check"><input data-field="is_primary" type="checkbox" ${item.is_primary ? "checked" : ""}> Primary</label>
    <button class="icon-btn" data-remove-row type="button">Remove</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function renderCampaignMeasurement() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  const items = project.configuration.measurement_plan?.items || [];
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
      <div class="card-hd"><div><h2>M4 KPIs & Measurement Plan</h2><p>Clicks, leads, test drives, and sales are tracked separately, not combined into total conversions.</p></div><button class="tb-btn" id="campaign-add-metric" type="button">+ Add KPI</button></div>
      <form id="campaign-measurement-form" class="campaign-form">
        <div class="campaign-repeat-head metric-head"><span>Code</span><span>Name</span><span>Target</span><span>Unit</span><span>Formula</span><span>Source</span><span>Window</span><span>Owner</span><span>Frequency</span><span>Primary</span><span></span></div>
        <div id="campaign-metric-rows" class="campaign-repeat-list"></div>
        ${campaignFormActions("Save KPI Plan")}
      </form>
    </article>`;
  const rows = document.getElementById("campaign-metric-rows");
  (items.length ? items : [{}]).forEach(item => rows.append(metricRow(item)));
  document.getElementById("campaign-add-metric").addEventListener("click", () => rows.append(metricRow()));
  bindBackToList(panel);
  document.getElementById("campaign-measurement-form").addEventListener("submit", saveCampaignMeasurement);
}

function collectRepeatRows(selector, fields) {
  return [...document.querySelectorAll(selector)].map(row => {
    const item = {};
    fields.forEach(field => {
      const input = row.querySelector(`[data-field="${field}"]`);
      if (!input) return;
      item[field] = input.type === "checkbox" ? input.checked : input.value;
    });
    return item;
  });
}

async function saveCampaignMeasurement(event) {
  event.preventDefault();
  const items = collectRepeatRows(".campaign-metric-row", ["metric_code", "name", "target_value", "unit", "formula", "data_source", "observation_window", "owner", "refresh_frequency", "is_primary"])
    .filter(item => item.metric_code)
    .map(item => ({...item, target_value: Number(item.target_value), data_status: "manual"}));
  try {
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/measurement-plan`, {method: "PUT", body: JSON.stringify({expected_revision: campaignState.current.revision, items})});
    showStatus("KPI measurement plan saved.");
    showCampaignStep("M5");
  } catch (error) { showStatus(error.message, true); }
}

function roleRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-role-row";
  row.innerHTML = `
    <input data-field="role_code" placeholder="Role code" value="${campaignEscape(item.role_code)}">
    <input data-field="role_name" placeholder="Role name" value="${campaignEscape(item.role_name)}">
    <select data-field="market"><option value="DE" ${item.market === "DE" ? "selected" : ""}>DE</option><option value="GB" ${item.market === "GB" || !item.market ? "selected" : ""}>GB</option></select>
    <input data-field="platform" placeholder="Platform" value="${campaignEscape(item.platform || "YouTube")}">
    <input data-field="required_count" type="number" min="1" placeholder="Number of creators" value="${campaignEscape(item.required_count || 1)}">
    <input data-field="content_format" placeholder="Content Formats" value="${campaignEscape(item.content_format)}">
    <input data-field="audience_requirement" placeholder="Audience requirements" value="${campaignEscape(item.audience_requirement)}">
    <input data-field="risk_threshold" placeholder="Risk threshold" value="${campaignEscape(item.risk_threshold || "Critical creator-level risk blocks the campaign")}">
    <input data-field="quote_cap" type="number" min="0" placeholder="Quote cap" value="${campaignEscape(item.quote_cap)}">
    <button class="icon-btn" data-remove-row type="button">Remove</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function budgetRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-budget-row";
  row.innerHTML = `
    <input data-field="category" placeholder="Budget item" value="${campaignEscape(item.category)}">
    <input data-field="amount" type="number" min="0" step="0.01" placeholder="Amount" value="${campaignEscape(item.amount)}">
    <label class="campaign-check"><input data-field="estimated" type="checkbox" ${item.estimated !== false ? "checked" : ""}> Estimated</label>
    <input data-field="assumption" placeholder="Estimate assumptions or notes" value="${campaignEscape(item.assumption)}">
    <button class="icon-btn" data-remove-row type="button">Remove</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function renderCampaignRequirements() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  const data = project.configuration.kol_requirements || {};
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
    <div class="card-hd"><div><h2>M5 Creator Roles & Budget</h2><p>Convert the strategy into filters and check whether the budget breakdown exceeds ${new Intl.NumberFormat("en-US").format(project.budget_total)} ${campaignEscape(project.currency)}.</p></div></div>
      <form id="campaign-requirements-form" class="campaign-form">
    <div class="campaign-subsection"><div><h3>Creator Role Requirements</h3><p>Markets and platforms must match the M2 and M3 setup.</p></div><button class="tb-btn" id="campaign-add-role" type="button">+ Add Role</button></div>
        <div class="campaign-repeat-head role-head"><span>Code</span><span>Role</span><span>Market</span><span>Platform</span><span>Number of creators</span><span>Format</span><span>Audience requirements</span><span>Risk threshold</span><span>Quote cap</span><span></span></div>
        <div id="campaign-role-rows" class="campaign-repeat-list"></div>
    <div class="campaign-subsection"><div><h3>Budget Breakdown</h3><p>Keep estimates clearly marked with their assumptions until quotes are received.</p></div><button class="tb-btn" id="campaign-add-budget" type="button">+ Add Budget Item</button></div>
    <div class="campaign-repeat-head budget-head"><span>Budget item</span><span>Amount</span><span>Status</span><span>Assumptions</span><span></span></div>
        <div id="campaign-budget-rows" class="campaign-repeat-list"></div>
        <div id="campaign-budget-summary" class="campaign-budget-summary"></div>
        ${campaignFormActions("Save Creator Requirements & Budget")}
      </form>
    </article>`;
  const roleRows = document.getElementById("campaign-role-rows");
  const budgetRows = document.getElementById("campaign-budget-rows");
  (data.roles?.length ? data.roles : [{}]).forEach(item => roleRows.append(roleRow(item)));
  (data.budget_items?.length ? data.budget_items : [{}]).forEach(item => budgetRows.append(budgetRow(item)));
  document.getElementById("campaign-add-role").addEventListener("click", () => roleRows.append(roleRow()));
  document.getElementById("campaign-add-budget").addEventListener("click", () => { budgetRows.append(budgetRow()); bindBudgetInputs(); });
  bindBackToList(panel);
  bindBudgetInputs();
  document.getElementById("campaign-requirements-form").addEventListener("submit", saveCampaignRequirements);
}

function bindBudgetInputs() {
  document.querySelectorAll(".campaign-budget-row [data-field='amount']").forEach(input => {
    input.oninput = updateBudgetSummary;
  });
  updateBudgetSummary();
}

function updateBudgetSummary() {
  const total = [...document.querySelectorAll(".campaign-budget-row [data-field='amount']")].reduce((sum, input) => sum + Number(input.value || 0), 0);
  const budget = campaignState.current?.budget_total || 0;
  const node = document.getElementById("campaign-budget-summary");
  if (!node) return;
  node.classList.toggle("over", total > budget);
  node.textContent = `Line-item total ${new Intl.NumberFormat("en-US").format(total)} / Total budget ${new Intl.NumberFormat("en-US").format(budget)} ${campaignState.current?.currency || ""}${total > budget ? `; over budget by ${new Intl.NumberFormat("en-US").format(total - budget)}` : ""}`;
}

async function saveCampaignRequirements(event) {
  event.preventDefault();
  const roles = collectRepeatRows(".campaign-role-row", ["role_code", "role_name", "market", "platform", "required_count", "content_format", "audience_requirement", "risk_threshold", "quote_cap"])
    .filter(item => item.role_code)
    .map(item => ({...item, required_count: Number(item.required_count), quote_cap: item.quote_cap === "" ? null : Number(item.quote_cap), score_preferences: [], estimated: true}));
  const budget_items = collectRepeatRows(".campaign-budget-row", ["category", "amount", "estimated", "assumption"])
    .filter(item => item.category)
    .map(item => ({...item, amount: Number(item.amount), assumption: item.assumption || null}));
  try {
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/kol-requirements`, {method: "PUT", body: JSON.stringify({expected_revision: campaignState.current.revision, roles, budget_items})});
    showStatus("Creator requirements and budget saved.");
    showCampaignStep("M6");
  } catch (error) { showStatus(error.message, true); }
}

async function renderCampaignApproval() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  updateCampaignContext();
  panel.innerHTML = '<div class="empty-state">Running pre-approval checks…</div>';
  let validation;
  try { validation = await campaignRequest(`/campaigns/${project.campaign_id}/validate`, {method: "POST"}); }
  catch (error) { panel.innerHTML = `<div class="empty-state">${campaignEscape(error.message)}</div>`; return; }
  const issues = [...validation.errors, ...validation.warnings];
  const approvals = project.approvals || [];
  const handoffs = project.handoffs || [];
  panel.innerHTML = `
    <div class="campaign-approval-grid">
      <article class="content-card campaign-check-card">
        <div class="card-hd"><div><h2>M6 Pre-approval Checks</h2><p>Completeness ${validation.completion}% · V${validation.version_number}</p></div><span class="campaign-validation ${validation.valid ? "pass" : "fail"}">${validation.valid ? "Checks passed" : `${validation.errors.length}blocking issue(s)`}</span></div>
        <div class="campaign-issue-list">${issues.length ? issues.map(issue => `<button type="button" data-issue-page="${campaignEscape(issue.page)}" class="campaign-issue ${issue.severity}"><b>${campaignEscape(issue.page)}</b><span>${campaignEscape(issue.message)}</span></button>`).join("") : '<div class="campaign-success">All pre-approval checks passed.</div>'}</div>
      </article>
      <article class="content-card campaign-decision-card">
        <div class="card-hd"><h2>Approval & Publication</h2><span class="campaign-status status-${campaignEscape(project.status)}">${CAMPAIGN_STATUS[project.status] || project.status}</span></div>
        <div class="campaign-decision-body">
          <p>The brand owner approves the campaign. When compliance boundaries apply, risk and compliance sign-off is required.</p>
          <label class="campaign-check"><input id="campaign-risk-signoff" type="checkbox"> Risk and compliance sign-off completed</label>
          <div class="campaign-decision-actions">
            ${project.status === "draft" ? '<button id="campaign-submit" class="tb-btn teal" type="button">Submit for Approval</button>' : ""}
            ${project.status === "pending_approval" ? '<button id="campaign-return" class="tb-btn" type="button">Return for Changes</button><button id="campaign-reject" class="tb-btn" type="button">Reject</button><button id="campaign-approve" class="tb-btn teal" type="button">Approve & Freeze Version</button>' : ""}
            ${project.status === "approved" ? '<button id="campaign-publish" class="tb-btn teal" type="button">Publish Downstream Handoff</button>' : ""}
          </div>
        </div>
      </article>
    </div>
    <div class="campaign-audit-grid">
      <article class="content-card"><div class="card-hd"><h2>Versions & Approval History</h2></div><div class="table-wrap"><table><thead><tr><th>Version</th><th>Status</th><th>Created by</th><th>Submitted / Approved</th></tr></thead><tbody>${(project.versions || []).map(item => `<tr><td>V${item.version_number}</td><td>${campaignEscape(item.status)}</td><td>${campaignEscape(item.created_by)}</td><td>${campaignEscape(item.approved_at || item.submitted_at || "—")}</td></tr>`).join("")}</tbody></table></div><div class="campaign-audit-list">${approvals.map(item => `<p><b>${campaignEscape(item.action)}</b><span>V${item.version_number} · ${campaignEscape(item.actor)} · ${campaignEscape(item.reason || "No additional notes")}</span></p>`).join("") || '<div class="empty-state">No approval history yet.</div>'}</div></article>
    <article class="content-card"><div class="card-hd"><h2>Downstream Handoffs</h2><span>${handoffs.length} module(s)</span></div><div class="campaign-handoff-list">${handoffs.map(item => `<div><b>${campaignEscape(item.target_label)}</b><span>V${item.version_number} · ${campaignEscape(item.status)} · Attempt ${item.attempts}</span></div>`).join("") || '<div class="empty-state">Publish the handoff package after approval.</div>'}</div></article>
    </div>`;
  panel.querySelectorAll("[data-issue-page]").forEach(button => button.addEventListener("click", () => showCampaignStep(button.dataset.issuePage)));
  document.getElementById("campaign-submit")?.addEventListener("click", submitCurrentCampaign);
  document.getElementById("campaign-approve")?.addEventListener("click", () => decideCurrentCampaign("approve"));
  document.getElementById("campaign-return")?.addEventListener("click", () => decideCurrentCampaign("return"));
  document.getElementById("campaign-reject")?.addEventListener("click", () => decideCurrentCampaign("reject"));
  document.getElementById("campaign-publish")?.addEventListener("click", publishCurrentCampaign);
}

async function submitCurrentCampaign() {
  try {
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/submit`, {method: "POST", body: JSON.stringify({expected_revision: campaignState.current.revision, actor: "Campaign owner", actor_role: "project_owner"})});
    showStatus("Campaign submitted for approval; the current version is locked.");
    renderCampaignApproval();
  } catch (error) {
    showStatus(error.message, true);
    if (error.issues?.[0]?.page) showCampaignStep(error.issues[0].page);
  }
}

async function decideCurrentCampaign(decision) {
  const reason = decision === "approve" ? null : window.prompt(decision === "return" ? "Enter a reason for returning the campaign." : "Enter a reason for rejecting the campaign.");
  if (decision !== "approve" && !reason) return;
  const riskSignoff = Boolean(document.getElementById("campaign-risk-signoff")?.checked);
  try {
  campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/decision`, {method: "POST", body: JSON.stringify({expected_revision: campaignState.current.revision, decision, reason, risk_signoff: riskSignoff, actor: "Brand owner", actor_role: "brand_owner"})});
  showStatus(decision === "approve" ? "Campaign approved and version frozen." : "Approval decision recorded.");
    renderCampaignApproval();
  } catch (error) { showStatus(error.message, true); }
}

async function publishCurrentCampaign() {
  try {
    await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/publish`, {method: "POST", body: JSON.stringify({actor: "Campaign owner", actor_role: "project_owner"})});
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}`);
  showStatus("Handoff package published to creator selection, contracts, monitoring, reviews, and assets.");
    renderCampaignApproval();
  } catch (error) { showStatus(error.message, true); }
}
