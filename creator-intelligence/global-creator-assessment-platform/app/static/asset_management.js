"use strict";

const assetState = {view: "overview", kol: null, campaignId: null, initialized: false};

function assetEscape(value) {
  return String(value ?? "Unavailable").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function assetNumber(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  return new Intl.NumberFormat("en-US", {notation: "compact", maximumFractionDigits: 2}).format(Number(value));
}

function assetDisplay(value) {
  return value === null || value === undefined || value === "" ? "Unavailable" : assetEscape(value);
}

function assetScore(value) {
  return value === null || value === undefined ? "Unavailable" : `${assetNumber(value)}/100`;
}

function assetPercent(value) {
  return value === null || value === undefined ? "Unavailable" : `${assetNumber(value)}%`;
}

function assetCampaignQuery() {
  return assetState.campaignId ? `?campaign_id=${encodeURIComponent(assetState.campaignId)}` : "";
}

function assetStatusClass(status) {
  if (["Preferred"].includes(status)) return "good";
  if (["Conditional"].includes(status)) return "conditional";
  if (["Paused", "Blocked"].includes(status)) return "blocked";
  return "watch";
}

function initAssetModule() {
  if (assetState.initialized) return;
  assetState.initialized = true;
  document.querySelectorAll("[data-asset-view]").forEach(button => {
    button.addEventListener("click", () => switchAssetView(button.dataset.assetView).catch(error => showStatus(error.message, true)));
  });
}

function setAssetTab(view) {
  assetState.view = view;
  document.querySelectorAll("[data-asset-view]").forEach(button => button.classList.toggle("active", button.dataset.assetView === view));
  document.querySelectorAll(".asset-panel").forEach(panel => panel.classList.toggle("active", panel.id === `asset-${view}`));
}

async function switchAssetView(view, options = {}) {
  initAssetModule();
  if (options.kol) assetState.kol = options.kol;
  setAssetTab(view);
  if (view === "overview") await loadAssetOverview();
  if (view === "archive") await loadAssetArchive(assetState.kol);
  if (view === "evaluation") await loadAssetEvaluation(assetState.kol);
  if (view === "portfolio") await loadAssetPortfolio();
  if (view === "governance") await loadAssetGovernance();
  if (view === "actions") await loadAssetActions();
}

async function loadAssetOverview(filters = {}) {
  initAssetModule();
  setAssetTab("overview");
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  const data = await api(`/reinvestment/overview${query.toString() ? `?${query}` : ""}`);
  const m = data.metrics;
  const root = document.getElementById("asset-overview");
  root.innerHTML = `
    <article class="content-card monitor-context"><div><strong>Creator partnership asset pool</strong><small>Review historical partnership results, list status, Risks, and data completeness in one place</small></div><span>Updated ${assetEscape(String(data.updated_at).slice(0, 10))}</span></article>
    <div class="monitor-metrics">
      ${monitorMetric("Creators in asset pool", m.total, "Current asset pool")}
      ${monitorMetric("Preferred", m.preferred, "Long-term partnership eligibility")}
      ${monitorMetric("Conditional", m.conditional, "Partnership conditions apply")}
      ${monitorMetric("Watch", m.watch, "Continue gathering evidence")}
      ${monitorMetric("Paused / Blocked", m.blocked, "Cannot proceed yet", m.blocked > 0)}
      ${monitorMetric("Major Risks", m.major_risk, "Requires manual review", m.major_risk > 0)}
    </div>
    <form id="asset-filter-form" class="filter-bar asset-filter">
      <select name="country"><option value="">All markets</option><option value="GB">United Kingdom</option><option value="DE">Germany</option><option value="FR">France</option></select>
      <select name="platform"><option value="">All platforms</option><option>YouTube</option><option>Instagram</option><option>TikTok</option></select>
      <select name="status"><option value="">All statuses</option><option>Preferred</option><option>Conditional</option><option>Watch</option><option>Paused</option><option>Blocked</option></select>
      <button class="tb-btn" type="submit">Filter</button><button id="asset-filter-reset" class="tb-btn" type="button">Reset</button>
    </form>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Asset List</h3><span>${data.assets.length} creators</span></div>
        <div class="table-wrap"><table class="monitor-table"><thead><tr><th>KOL</th><th>Market / Platform</th><th>Partnerships</th><th>Most recent campaign</th><th>Recent results</th><th>List status</th><th>Risk</th><th>Completeness</th></tr></thead><tbody>
        ${data.assets.map(item => `<tr class="asset-row" data-asset-kol="${assetEscape(item.kol_id)}"><td><strong>${assetEscape(item.name)}</strong><small>${assetEscape(item.handle)}</small></td><td>${assetEscape(item.market)} · ${assetEscape(item.platform)}</td><td>${item.collaborations}</td><td>${assetDisplay(item.recent_project)}</td><td>${assetScore(item.recent_score)}</td><td><span class="asset-status ${assetStatusClass(item.list_status)}">${assetEscape(item.list_status)}</span></td><td>${assetEscape(item.risk)}</td><td>${item.data_completeness}%</td></tr>`).join("") || `<tr><td colspan="8">No creator records available.</td></tr>`}
        </tbody></table></div>
      </article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Items to Review</h3></div><div class="monitor-list">${(data.attention || []).map(item => `<div class="monitor-list-row"><span><strong>${assetEscape(item.type)}</strong><small>${assetEscape(item.text)}</small></span></div>`).join("") || `<div class="empty-state">No outstanding items.</div>`}</div></article>
    </div>`;
  const form = document.getElementById("asset-filter-form");
  form.country.value = data.filters.country;
  form.platform.value = data.filters.platform;
  form.status.value = data.filters.status;
  form.addEventListener("submit", event => {
    event.preventDefault();
    loadAssetOverview(Object.fromEntries(new FormData(form).entries())).catch(error => showStatus(error.message, true));
  });
  document.getElementById("asset-filter-reset").addEventListener("click", () => loadAssetOverview().catch(error => showStatus(error.message, true)));
  root.querySelectorAll("[data-asset-kol]").forEach(row => row.addEventListener("click", () => switchAssetView("archive", {kol: row.dataset.assetKol}).catch(error => showStatus(error.message, true))));
}

async function loadAssetArchive(kolKey = assetState.kol) {
  if (!kolKey) { document.getElementById("asset-archive").innerHTML = `<div class="empty-state">Select a creator from the asset list to view recorded history.</div>`; return; }
  const data = await api(`/reinvestment/archives/${encodeURIComponent(kolKey)}`);
  assetState.kol = String(data.identity.kol_id);
  const m = data.metrics;
  const root = document.getElementById("asset-archive");
  root.innerHTML = `
    <article class="content-card monitor-review-head"><div><small>${assetEscape(data.identity.market)} · ${assetEscape(data.identity.platform)} · ${assetEscape(data.identity.handle)}</small><h3>${assetEscape(data.identity.name)}</h3></div><div class="monitor-head-badges"><span class="asset-status ${assetStatusClass(data.identity.list_status)}">${assetEscape(data.identity.list_status)}</span><span>Data completeness ${data.data_completeness}%</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("Partnerships", m.collaborations, "Across campaigns")}${monitorMetric("Markets covered", m.markets, "Historical markets")}${monitorMetric("Content assets", m.content_assets, "Traceable records")}${monitorMetric("Average engagement rate", assetPercent(m.avg_engagement), "Historical reference")}${monitorMetric("Conversions", assetNumber(m.conversions), "Known historical conversions")}${monitorMetric("Content quality", assetScore(m.content_quality), "Review records")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Campaign History</h3><span>${assetEscape(data.trend_note)}</span></div><table class="monitor-table"><thead><tr><th>Campaign</th><th>Date</th><th>Platform</th><th>Result</th><th>Review score</th></tr></thead><tbody>${data.project_history.map(row => `<tr><td><strong>${assetEscape(row.project)}</strong><small>${assetEscape(row.note)}</small></td><td>${assetEscape(row.date)}</td><td>${assetEscape(row.platform)}</td><td>${assetEscape(row.result)}</td><td>${row.score ?? "—"}</td></tr>`).join("")}</tbody></table></article>
      <div class="monitor-stack">
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Reusable Assets</h3></div><ul>${data.reusable_assets.map(item => `<li>${assetEscape(item)}</li>`).join("")}</ul></article>
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Risks & Constraints</h3></div><ul>${data.risks.map(item => `<li>${assetEscape(item)}</li>`).join("")}</ul></article>
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Audit Log</h3></div><div class="monitor-timeline">${data.audit.map(item => `<div><time>Recorded</time><b>•</b><span>${assetEscape(item)}</span></div>`).join("")}</div></article>
      </div>
    </div>
    <div class="monitor-actions"><button id="asset-to-evaluation" class="tb-btn teal" type="button">Evaluate reinvestment for this campaign →</button></div>`;
  document.getElementById("asset-to-evaluation").addEventListener("click", () => switchAssetView("evaluation", {kol: String(data.identity.kol_id)}).catch(error => showStatus(error.message, true)));
}

async function loadAssetEvaluation(kolKey = assetState.kol) {
  if (!kolKey) { document.getElementById("asset-evaluation").innerHTML = `<div class="empty-state">Select a creator from the asset list to review assessment evidence.</div>`; return; }
  const data = await api(`/reinvestment/evaluations/${encodeURIComponent(kolKey)}${assetCampaignQuery()}`);
  assetState.kol = String(data.kol.kol_id);
  const root = document.getElementById("asset-evaluation");
  root.innerHTML = `
    <article class="content-card monitor-context"><div><strong>${assetEscape(data.project?.name ?? "Campaign not selected")}</strong><small>${assetEscape(data.project?.brand)} ${assetEscape(data.project?.model)} · ${assetEscape(data.project?.market)} · ${assetEscape(data.project?.objective)}</small></div><span>${assetEscape(data.kol.handle)}</span></article>
    <div class="monitor-metrics">
      ${monitorMetric("Recommendation score", assetScore(data.suggestion_score), "Project-specific evidence required")}${monitorMetric("Historical assessment", assetScore(data.historical_score), "Persisted scores with manual overrides")}${monitorMetric("Suggested status", data.suggestion_status, "Current campaign")}${monitorMetric("Data completeness", `${data.data_completeness}%`, "Missing does not mean zero")}${monitorMetric("Major Risks", data.major_risk ? "Blocked" : "No recorded blockers", "Independent of the total score", data.major_risk)}
    </div>
    <div class="asset-score-grid">${data.dimensions.map(item => `<article class="content-card monitor-pad"><div class="monitor-card-title"><h3>${assetEscape(item.name)}</h3><strong>${assetScore(item.score)}</strong></div><div class="asset-score-bar"><i style="width:${item.score ?? 0}%"></i></div><p>${assetEscape(item.evidence)}</p><small>${assetEscape(item.limitation)}</small></article>`).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Partnership Conditions</h3></div><div class="monitor-owner-list"><div><span>Quote cap</span><strong>${assetNumber(data.conditions.quote_cap)} ${assetEscape(data.conditions.currency)}</strong></div><div><span>Content format</span><strong>${assetEscape(data.conditions.content_format)}</strong></div><div><span>Availability</span><strong>${assetEscape(data.conditions.schedule)}</strong></div><div><span>Ad disclosure</span><strong>${assetEscape(data.conditions.disclosure)}</strong></div><div><span>Competitor exclusivity</span><strong>${assetEscape(data.conditions.exclusivity)}</strong></div><div><span>Additional data</span><strong>${assetEscape(data.conditions.data_required)}</strong></div></div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Manual Approval</h3><span>${assetEscape(data.approval.decision)}</span></div><form id="asset-approval-form"><label>Approval decision<select name="decision"><option>Approved</option><option>Conditionally Approved</option><option>Returned for More Information</option><option>Rejected</option></select></label><label>Notes<textarea name="note" rows="4">${assetEscape(data.approval.note || "")}</textarea></label><div class="monitor-actions"><button class="tb-btn teal" type="submit">Save Approval</button></div></form><div class="asset-callout">${assetEscape(data.note)}</div></article>
    </div>
    <div class="monitor-actions"><button id="asset-to-portfolio" class="tb-btn teal" type="button">Open Portfolio & Budget →</button></div>`;
  const form = document.getElementById("asset-approval-form");
  if (Array.from(form.decision.options).some(option => option.value === data.approval.decision)) form.decision.value = data.approval.decision;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    await api(`/reinvestment/evaluations/${encodeURIComponent(assetState.kol)}/approval${assetCampaignQuery()}`, {method: "POST", body: JSON.stringify(payload)});
    showStatus("Reinvestment approval saved.");
    await loadAssetEvaluation(assetState.kol);
  });
  document.getElementById("asset-to-portfolio").addEventListener("click", () => switchAssetView("portfolio").catch(error => showStatus(error.message, true)));
}

async function loadAssetPortfolio() {
  const [data, campaigns] = await Promise.all([api(`/reinvestment/portfolio${assetCampaignQuery()}`), api("/campaigns")]);
  const root = document.getElementById("asset-portfolio");
  root.innerHTML = `
    <label>Campaign <select id="asset-campaign-select"><option value="">Select a recorded campaign</option>${campaigns.items.map(item => `<option value="${assetEscape(item.campaign_id)}" ${item.campaign_id === assetState.campaignId ? "selected" : ""}>${assetEscape(item.project_name)}</option>`).join("")}</select></label>
    <article class="content-card monitor-context"><div><strong>${assetEscape(data.project?.name ?? "Campaign not selected")}</strong><small>Total budget ${assetNumber(data.project?.budget)} ${assetEscape(data.project?.currency)} · ${assetEscape(data.project?.period)}</small></div><span>Forecasts unavailable without measured evidence</span></article>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Candidate Pool</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>Market / Platform</th><th>Fit recommendation</th><th>Recommendation score</th><th>Quote cap</th><th>Availability</th><th>Risk</th></tr></thead><tbody>${data.candidates.map(item => `<tr><td>${assetEscape(item.handle)}</td><td>${assetEscape(item.market)} · ${assetEscape(item.platform)}</td><td><span class="asset-status ${assetStatusClass(item.recommendation)}">${assetEscape(item.recommendation)}</span></td><td>${assetScore(item.score)}</td><td>${assetNumber(item.quote_cap)} ${assetEscape(item.currency)}</td><td>${assetEscape(item.availability)}</td><td>${assetEscape(item.risk)}</td></tr>`).join("")}</tbody></table></article>
    <div class="asset-budget-grid">${data.scenarios.map(row => `<article class="content-card monitor-pad asset-scenario ${row.selected ? "selected" : ""}"><div class="monitor-card-title"><h3>Scenario ${row.id} · ${assetEscape(row.name)}</h3><strong>${row.budget_usage}%</strong></div><p><strong>${row.kols.map(assetEscape).join(" + ")}</strong></p><div class="asset-range"><span>Budget</span><b>${assetNumber(row.cost)} ${assetEscape(data.project?.currency)}</b></div><div class="asset-range"><span>Estimated reach</span><b>${assetEscape(row.reach_range)}</b></div><div class="asset-range"><span>Estimated engagements</span><b>${assetEscape(row.engagement_range)}</b></div><div class="asset-range"><span>Confidence</span><b>${assetEscape(row.confidence)}</b></div><small>${assetEscape(row.note)}; ${assetEscape(row.assumption)}</small><div class="monitor-actions"><button class="tb-btn ${row.selected ? "" : "teal"}" data-select-scenario="${row.id}" type="button">${row.selected ? "Current scenario" : "Select scenario"}</button></div></article>`).join("") || `<div class="empty-state">No portfolio proposals available. Record a campaign, project-specific quotes and a proposal before selecting a scenario.</div>`}</div>
    <div class="monitor-grid monitor-grid-main"><article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Portfolio Checks</h3></div><div class="monitor-list">${data.checks.map(item => `<div class="monitor-list-row"><span><strong>${assetEscape(item.name)}</strong><small>${assetEscape(item.detail)}</small></span><em>${assetEscape(item.status)}</em></div>`).join("")}</div></article><article class="content-card monitor-pad"><div class="asset-callout">${assetEscape(data.prediction_note)}</div><div class="monitor-actions"><button id="asset-to-governance" class="tb-btn teal" type="button">Open List Governance →</button></div></article></div>`;
  document.getElementById("asset-campaign-select").addEventListener("change", async event => {
    assetState.campaignId = event.target.value || null;
    await loadAssetPortfolio();
  });
  root.querySelectorAll("[data-select-scenario]").forEach(button => button.addEventListener("click", async () => {
    await api("/reinvestment/portfolio/select", {method: "POST", body: JSON.stringify({scenario_id: button.dataset.selectScenario})});
    showStatus(`Selected scenario ${button.dataset.selectScenario}`);
    await loadAssetPortfolio();
  }));
  document.getElementById("asset-to-governance").addEventListener("click", () => switchAssetView("governance").catch(error => showStatus(error.message, true)));
}

async function loadAssetGovernance() {
  const data = await api("/reinvestment/governance");
  const root = document.getElementById("asset-governance");
  root.innerHTML = `
    ${data.risk_banner.visible ? `<article class="content-card asset-Risk-banner"><strong>${assetEscape(data.risk_banner.title)}</strong><span>${assetEscape(data.risk_banner.kol)} · ${assetEscape(data.risk_banner.fact)}</span></article>` : ""}
    <div class="monitor-metrics">${["Preferred","Conditional","Watch","Paused","Blocked"].map(name => monitorMetric(name, data.metrics[name] || 0, "List status", ["Paused","Blocked"].includes(name))).join("")}${monitorMetric("Pending review", data.metrics.pending_approval, "Requires approval / review")}</div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Partnership Eligibility List</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>Status</th><th>Scope</th><th>Reason</th><th>Affected campaigns</th><th>Owner</th><th>Review</th></tr></thead><tbody>${data.rows.map(row => `<tr><td><strong>${assetEscape(row.handle)}</strong></td><td><span class="asset-status ${assetStatusClass(row.status)}">${assetEscape(row.status)}</span></td><td>${assetEscape(row.scope)}</td><td>${assetEscape(row.reason)}</td><td>${assetDisplay(row.affected_projects)}</td><td>${assetEscape(row.owner)}</td><td>${assetDisplay(row.review_at)}</td></tr>`).join("")}</tbody></table></article>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Update Partnership Eligibility</h3><span>A reason is required</span></div><form id="asset-governance-form" class="asset-form-grid"><label>KOL<select name="kol">${data.rows.map(row => `<option value="${assetEscape(row.kol_id)}">${assetEscape(row.handle)}</option>`).join("")}</select></label><label>Status<select name="status"><option>Preferred</option><option>Conditional</option><option>Watch</option><option>Paused</option><option>Blocked</option></select></label><label>Scope<input name="scope" placeholder="Specify the applicable scope"></label><label>Review date<input name="review_at" placeholder="e.g., 2026-09-15 / review by campaign"></label><label class="wide">Reason<input name="reason" required placeholder="Describe the evidence, restrictions, or approval rationale"></label><div class="monitor-actions wide"><button class="tb-btn teal" type="submit" ${data.rows.length ? "" : "disabled"}>Save status</button></div></form><div class="asset-callout">${assetEscape(data.rule)}</div></article>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Recent Audit Log</h3></div><div class="monitor-timeline">${data.timeline.map(row => `<div><time>${assetEscape(String(row.time).slice(5, 16).replace("T", " "))}</time><b>•</b><span>${assetEscape(row.kol)} · ${assetEscape(row.event)}: ${assetEscape(row.reason)}</span></div>`).join("") || `<div class="empty-state">No manual status changes yet.</div>`}</div></article>
    </div>
    <div class="monitor-actions"><button id="asset-to-actions" class="tb-btn teal" type="button">Open Action Tracking →</button></div>`;
  document.getElementById("asset-governance-form").addEventListener("submit", async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    const kol = payload.kol; delete payload.kol;
    await api(`/reinvestment/governance/${encodeURIComponent(kol)}`, {method: "POST", body: JSON.stringify(payload)});
    showStatus("List status saved.");
    await loadAssetGovernance();
  });
  document.getElementById("asset-to-actions").addEventListener("click", () => switchAssetView("actions").catch(error => showStatus(error.message, true)));
}

async function loadAssetActions() {
  const data = await api(`/reinvestment/actions${assetCampaignQuery()}`);
  const root = document.getElementById("asset-actions");
  root.innerHTML = `
    <article class="content-card monitor-review-head"><div><small>${assetEscape(data.source_plan)}</small><h3>${assetEscape(data.project?.name ?? "Campaign not selected")}</h3></div><div class="monitor-head-badges"><span>Budget ${assetNumber(data.expected_budget)} ${assetEscape(data.currency)}</span><span>${assetEscape(data.milestone)}</span><span>Next due date ${assetDisplay(data.next_deadline)}</span></div></article>
    <div class="asset-pipeline">${Object.entries(data.pipeline).map(([name, count]) => `<div><span>${assetEscape(name)}</span><strong>${count}</strong></div>`).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Candidate Progress</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>Stage</th><th>Quote</th><th>Availability</th><th>Partnership Conditions</th><th>Blocker</th></tr></thead><tbody>${data.candidates.map(row => `<tr><td>${assetEscape(row.handle)}</td><td><span class="monitor-pill">${assetEscape(row.stage)}</span></td><td>${assetEscape(row.quote)}</td><td>${assetEscape(row.schedule)}</td><td>${assetEscape(row.conditions)}</td><td>${assetEscape(row.blocker)}</td></tr>`).join("")}</tbody></table></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Handoff & Write-back</h3></div><div class="asset-callout">${assetEscape(data.writeback_note)}</div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Task Center</h3><span>Owner ${assetEscape(data.owner)}</span></div><table class="monitor-table"><thead><tr><th>Task</th><th>KOL</th><th>Owner</th><th>Due date</th><th>Dependency</th><th>Status</th></tr></thead><tbody>${data.tasks.map(row => `<tr><td><strong>${assetEscape(row.task)}</strong><small>${assetEscape(row.task_code)}</small></td><td>${assetEscape(row.kol)}</td><td>${assetEscape(row.owner)}</td><td>${assetDisplay(row.due_at)}</td><td>${assetEscape(row.dependency)}</td><td><select class="asset-task-status" data-task-code="${assetEscape(row.task_code)}">${["To Do", "In Progress", "Completed", "Blocked"].includes(row.status) ? "" : `<option selected disabled>${assetEscape(row.status)}</option>`}<option ${row.status === "To Do" ? "selected" : ""}>To Do</option><option ${row.status === "In Progress" ? "selected" : ""}>In Progress</option><option ${row.status === "Completed" ? "selected" : ""}>Completed</option><option ${row.status === "Blocked" ? "selected" : ""}>Blocked</option></select></td></tr>`).join("")}</tbody></table></article>`;
  root.querySelectorAll("[data-task-code]").forEach(select => select.addEventListener("change", async () => {
    await api(`/reinvestment/actions/${encodeURIComponent(select.dataset.taskCode)}`, {method: "POST", body: JSON.stringify({status: select.value})});
    showStatus(`${select.dataset.taskCode} updated to ${select.value}`);
  }));
}
