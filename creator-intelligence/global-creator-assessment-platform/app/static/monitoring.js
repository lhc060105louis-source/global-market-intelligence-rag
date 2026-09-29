"use strict";

const monitoringState = {view: "overview", taskCode: null, riskCode: null, initialized: false};

function monitorEscape(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function monitorDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-GB", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false}).format(date);
}

function monitorNumber(value) {
  return new Intl.NumberFormat("en-US", {notation: "compact", maximumFractionDigits: 1}).format(Number(value || 0));
}

function monitorRiskClass(level) {
  if (String(level).includes("Critical") || String(level).includes("High")) return "high";
  if (String(level).includes("Medium")) return "medium";
  if (String(level).includes("Low")) return "low";
  return "none";
}

function initMonitoringModule() {
  if (monitoringState.initialized) return;
  monitoringState.initialized = true;
  const platformFilter = document.getElementById("monitor-platform-filter");
  ["Instagram", "TikTok"].forEach(name => { const option = document.createElement("option"); option.value = name; option.textContent = name; platformFilter.append(option); });
  document.querySelectorAll("[data-monitor-view]").forEach(button => {
    button.addEventListener("click", () => switchMonitoringView(button.dataset.monitorView));
  });
  document.getElementById("monitor-task-filter").addEventListener("submit", event => {
    event.preventDefault();
    loadMonitoringTasks().catch(error => showStatus(error.message, true));
  });
  document.getElementById("monitor-filter-reset").addEventListener("click", () => {
    document.getElementById("monitor-task-filter").reset();
    loadMonitoringTasks().catch(error => showStatus(error.message, true));
  });
  document.getElementById("monitoring-tasks").addEventListener("click", event => {
    const button = event.target.closest("[data-task-code]");
    if (!button) return;
    switchMonitoringView("review", {taskCode: button.dataset.taskCode});
  });
  document.getElementById("monitoring-overview").addEventListener("click", event => {
    const task = event.target.closest("[data-task-code]");
    const risk = event.target.closest("[data-risk-code]");
    if (task) switchMonitoringView("review", {taskCode: task.dataset.taskCode});
    if (risk) switchMonitoringView("risk", {riskCode: risk.dataset.riskCode});
  });
}

function setMonitoringTab(view) {
  monitoringState.view = view;
  document.querySelectorAll("[data-monitor-view]").forEach(button => button.classList.toggle("active", button.dataset.monitorView === view));
  document.querySelectorAll(".monitor-panel").forEach(panel => panel.classList.toggle("active", panel.id === `monitoring-${view}`));
}

async function switchMonitoringView(view, options = {}) {
  initMonitoringModule();
  setMonitoringTab(view);
  if (options.taskCode) monitoringState.taskCode = options.taskCode;
  if (options.riskCode) monitoringState.riskCode = options.riskCode;
  if (view === "overview") await loadMonitoringOverview();
  if (view === "tasks") await loadMonitoringTasks();
  if (view === "review") await loadMonitoringReview(monitoringState.taskCode);
  if (view === "risk") await loadMonitoringRisk(monitoringState.riskCode);
  if (view === "crisis") await loadCrisisWorkspace();
}

async function loadMonitoringOverview() {
  initMonitoringModule();
  const data = await api("/monitoring/overview");
  const root = document.getElementById("monitoring-overview");
  const m = data.metrics;
  const p = data.project;
  const total = Math.max(1, m.total_tasks);
  root.innerHTML = `
    <article class="content-card monitor-context">
      <div><strong>${monitorEscape(p.name)}</strong><small>${monitorEscape(p.brand)} · ${monitorEscape(p.market)} · ${monitorEscape(p.period)}</small></div>
      <span>Data updated ${monitorDate(p.updated_at)}</span>
    </article>
    <div class="monitor-metrics">
      ${monitorMetric("Content tasks", m.total_tasks, "Current campaign")}
      ${monitorMetric("On-time rate", `${m.on_time_rate}%`, "Completed as scheduled")}
      ${monitorMetric("Pending Review", m.pending_review, "Awaiting action")}
      ${monitorMetric("Ready to publish", m.pending_publish, "Awaiting publication")}
      ${monitorMetric("Published", m.published, "Live")}
      ${monitorMetric("Open risks", m.open_risks, "Needs follow-up", true)}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Content Stage Progress</h3><button class="text-btn" data-monitor-view="tasks" type="button">View Tasks</button></div>
        <div class="monitor-stage-strip">${data.stages.map(stage => `<div style="flex:${Math.max(stage.count, .35)}"><span>${monitorEscape(stage.name)}</span><strong>${stage.count}</strong><i style="width:${Math.max(6, stage.count / total * 100)}%"></i></div>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Risks & Action Items</h3><span>${data.risks.length} item(s)</span></div>
        <div class="monitor-list">${data.risks.map(risk => `<button class="monitor-list-row" data-risk-code="${monitorEscape(risk.risk_code)}" type="button"><b class="risk-dot ${monitorRiskClass(risk.level)}"></b><span><strong>${monitorEscape(risk.title)}</strong><small>${monitorEscape(risk.risk_code)} · ${monitorEscape(risk.status)}</small></span><em>${monitorEscape(risk.level)}risk</em></button>`).join("")}</div>
      </article>
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Publishing Schedule: Next 14 Days</h3></div>
        <div class="monitor-list">${data.upcoming.map(task => `<button class="monitor-list-row schedule" data-task-code="${monitorEscape(task.task_code)}" type="button"><time>${monitorDate(task.planned_publish_at)}</time><span><strong>${monitorEscape(task.kol)}</strong><small>${monitorEscape(task.platform)} · ${monitorEscape(task.content_type)}</small></span><em>${monitorEscape(task.execution_stage)}</em></button>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Published Content Performance</h3><span>${m.published} item(s)</span></div>
        <div class="monitor-performance">
          <div><span>Views / Impressions</span><strong>${monitorNumber(data.performance.impressions)}</strong></div>
          <div><span>Average engagement rate</span><strong>${data.performance.average_engagement_rate}%</strong></div>
          <div><span>Positive sentiment</span><strong>${data.performance.positive_sentiment}%</strong></div>
        </div>
      </article>
    </div>`;
  root.querySelectorAll("[data-monitor-view]").forEach(button => button.addEventListener("click", () => switchMonitoringView(button.dataset.monitorView)));
}

function monitorMetric(label, value, note, danger = false) {
  return `<article class="metric-card ${danger ? "warning" : ""}"><span>${monitorEscape(label)}</span><strong>${monitorEscape(value)}</strong><small>${monitorEscape(note)}</small></article>`;
}

async function loadMonitoringTasks() {
  initMonitoringModule();
  const form = new FormData(document.getElementById("monitor-task-filter"));
  const query = new URLSearchParams();
  for (const [key, value] of form.entries()) if (String(value).trim()) query.set(key, value);
  const data = await api(`/monitoring/tasks${query.toString() ? `?${query}` : ""}`);
  const container = document.getElementById("monitor-task-table");
  if (!data.items.length) {
    container.innerHTML = `<div class="empty-state">No content tasks match the current filters.</div>`;
    return;
  }
  container.innerHTML = `<table class="monitor-table"><thead><tr><th>Task / Creator</th><th>Platform / Content</th><th>Execution stage</th><th>Scheduled publication</th><th>Review</th><th>Monitoring</th><th>risk</th><th></th></tr></thead><tbody>${data.items.map(task => `
    <tr>
      <td><strong>${monitorEscape(task.title)}</strong><small>${monitorEscape(task.task_code)} · ${monitorEscape(task.kol)}</small></td>
      <td>${monitorEscape(task.platform)}<small>${monitorEscape(task.content_type)}</small></td>
      <td><span class="monitor-pill">${monitorEscape(task.execution_stage)}</span></td>
      <td>${monitorDate(task.planned_publish_at)}</td>
      <td>${monitorEscape(task.review_status)}</td>
      <td>${monitorEscape(task.monitoring_status)}</td>
      <td><span class="risk-label ${monitorRiskClass(task.risk_level)}">${monitorEscape(task.risk_level)}</span></td>
      <td><button class="text-btn" data-task-code="${monitorEscape(task.task_code)}" type="button">View details →</button></td>
    </tr>`).join("")}</tbody></table>`;
  document.getElementById("monitor-task-count").textContent = data.total;
}

async function loadMonitoringReview(taskCode) {
  initMonitoringModule();
  const root = document.getElementById("monitoring-review");
  if (!taskCode) {
    const tasks = await api("/monitoring/tasks?stage=Under Review");
    taskCode = tasks.items[0]?.task_code || (await api("/monitoring/tasks")).items[0]?.task_code;
    monitoringState.taskCode = taskCode;
  }
  if (!taskCode) {
    root.innerHTML = `<div class="empty-state">No content tasks are awaiting review.</div>`;
    return;
  }
  const task = await api(`/monitoring/tasks/${encodeURIComponent(taskCode)}`);
  monitoringState.taskCode = task.task_code;
  const crisisList = await api("/post-campaign/crises");
  const crisis = crisisList.items.find(item => item.kol === task.kol);
  const briefPassed = Object.values(task.brief_checks || {}).filter(Boolean).length;
  const briefTotal = Object.keys(task.brief_checks || {}).length;
  const canApprove = !crisis && task.risks.length === 0 && Object.values(task.brief_checks || {}).every(Boolean) && Object.values(task.final_checks || {}).every(Boolean);
  root.innerHTML = `
    <article class="content-card monitor-review-head">
      <div><small>${monitorEscape(task.task_code)} · ${monitorEscape(task.kol)} · ${monitorEscape(task.platform)} ${monitorEscape(task.content_type)}</small><h3>${monitorEscape(task.title)}</h3></div>
      <div class="monitor-head-badges"><span class="monitor-pill">${monitorEscape(task.execution_stage)}</span><span class="risk-label ${monitorRiskClass(task.risk_level)}">${monitorEscape(task.risk_level)}</span><span>${monitorEscape(task.version_label)}</span><time>${monitorDate(task.planned_publish_at)}</time></div>
    </article>
    <div class="monitor-review-grid">
      <div class="monitor-stack">
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Submitted Content & Version</h3><span>${monitorEscape(task.version_label)}</span></div>
          <div class="monitor-content-preview"><div class="monitor-preview-box">${monitorEscape(task.platform)} ${monitorEscape(task.content_type)}<strong>${monitorEscape(task.title)}</strong></div><dl><dt>Content URL</dt><dd>${monitorEscape(task.content_url || "Not provided")}</dd><dt>Duration / Resolution</dt><dd>${task.duration_seconds || "—"}s · ${monitorEscape(task.resolution || "—")}</dd><dt>Caption</dt><dd>${monitorEscape(task.caption || "—")}</dd></dl></div>
        </article>
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Brief Checks</h3><strong>${briefPassed}/${briefTotal} Passed</strong></div>
          <div class="monitor-check-grid">${Object.entries(task.brief_checks || {}).map(([name, ok]) => monitorCheck(name, ok)).join("")}</div>
        </article>
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Version History</h3><span>${task.version_history.length} version(s)</span></div>
          <div class="monitor-timeline">${task.version_history.map(item => `<div><time>${monitorEscape(item.time)}</time><b>${monitorEscape(item.version)}</b><span>${monitorEscape(item.note)}</span></div>`).join("")}</div>
        </article>
      </div>
      <div class="monitor-stack">
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Final Review Checklist</h3></div>
          <div class="monitor-final-list">${Object.entries(task.final_checks || {}).map(([name, ok]) => monitorCheck(name, ok)).join("")}</div>
          ${task.risks.length ? `<div class="monitor-risk-alert"><strong>${monitorEscape(task.risks[0].title)}</strong><span>Resolve the risk event first.</span></div>` : ""}
          ${crisis ? `
            <div class="monitor-risk-alert">
               <strong>This creator has an open major incident.</strong>
              <span>${monitorEscape(crisis.title)}</span>
              <button id="monitor-open-crisis" class="text-btn" type="button">
                View incident
              </button>
            </div>
          ` : ""}
          <div class="monitor-actions">
            <button id="monitor-request-changes" class="tb-btn" type="button">Changes Requested</button>
            ${task.risks.length ? `<button id="monitor-open-risk" class="tb-btn" type="button">Risk Details</button>` : ""}
            <button id="monitor-approve" class="tb-btn teal" type="button" ${canApprove ? "" : "disabled"}>Approve for Publication</button>
          </div>
        </article>
      </div>
    </div>`;
  document.getElementById("monitor-request-changes").addEventListener("click", async () => {
    await api(`/monitoring/tasks/${encodeURIComponent(task.task_code)}/request-changes`, {method: "POST"});
    showStatus("Changes requested.");
    await loadMonitoringReview(task.task_code);
  });
  const riskButton = document.getElementById("monitor-open-risk");
  if (riskButton) riskButton.addEventListener("click", () => switchMonitoringView("risk", {riskCode: task.risks[0].risk_code}));
  const crisisButton = document.getElementById("monitor-open-crisis");
  if (crisisButton) crisisButton.addEventListener("click", () => switchMonitoringView("crisis"));
  document.getElementById("monitor-approve").addEventListener("click", async () => {
    try {
      await api(`/monitoring/tasks/${encodeURIComponent(task.task_code)}/approve`, {method: "POST"});
      showStatus("Approved. The task is ready to publish.");
      await loadMonitoringReview(task.task_code);
      await loadMonitoringOverview();
    } catch (error) {
      showStatus(error.message, true);
    }
  });
}

function monitorCheck(name, ok) {
  return `<div class="monitor-check ${ok ? "pass" : "fail"}"><b>${ok ? "✓" : "!"}</b><span>${monitorEscape(name)}</span><em>${ok ? "Passed" : "Failed"}</em></div>`;
}

async function loadMonitoringRisk(riskCode) {
  initMonitoringModule();
  const root = document.getElementById("monitoring-risk");
  if (!riskCode) {
    const list = await api("/monitoring/risks");
    riskCode = list.items[0]?.risk_code;
    monitoringState.riskCode = riskCode;
  }
  if (!riskCode) {
    root.innerHTML = `<div class="empty-state">There are no open risk events.</div>`;
    return;
  }
  const risk = await api(`/monitoring/risks/${encodeURIComponent(riskCode)}`);
  monitoringState.riskCode = risk.risk_code;
  const done = risk.remediation_steps.filter(step => step.done).length;
  root.innerHTML = `
    <article class="content-card monitor-review-head risk-head">
      <div><small>${monitorEscape(risk.risk_code)} · ${monitorEscape(risk.task?.kol || "")}</small><h3>${monitorEscape(risk.title)}</h3></div>
        <div class="monitor-head-badges"><span class="risk-label ${monitorRiskClass(risk.level)}">${monitorEscape(risk.level)}</span><span>${monitorEscape(risk.status)}</span><span>${risk.blocked ? "Publication blocked" : "Not blocked"}</span></div>
    </article>
    <div class="monitor-review-grid">
      <div class="monitor-stack">
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Incident Evidence</h3><span>Confidence ${risk.confidence ?? "—"}%</span></div>
          <dl class="monitor-evidence"><dt>Trigger channel</dt><dd>${monitorEscape(risk.channel)}</dd><dt>Detection method</dt><dd>${monitorEscape(risk.detection_method)}</dd><dt>Triggering version</dt><dd>${monitorEscape(risk.trigger_version)}</dd><dt>Affected step</dt><dd>${monitorEscape(risk.impacted_node)}</dd></dl>
          <div class="monitor-evidence-box">${monitorEscape(risk.evidence_excerpt || "—")}</div>
        </article>
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Matched Rules</h3><span>${risk.rules.length} item(s)</span></div>
          <div class="monitor-rule-list">${risk.rules.map(rule => `<div><b>${monitorEscape(rule.name)}</b><span>${monitorEscape(rule.detail)}</span><em class="${String(rule.status).includes("Failed") ? "fail" : String(rule.status).includes("Passed") ? "pass" : ""}">${monitorEscape(rule.status)}</em></div>`).join("")}</div>
        </article>
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Action History</h3></div>
          <div class="monitor-timeline">${risk.timeline.map(item => `<div><time>${monitorEscape(item.time)}</time><b>•</b><span>${monitorEscape(item.event)}</span></div>`).join("")}</div>
        </article>
      </div>
      <div class="monitor-stack">
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Owner</h3><span>${monitorEscape(risk.status)}</span></div>
          <div class="monitor-owner-list">${Object.entries(risk.owners || {}).map(([role, name]) => `<div><span>${monitorEscape(role)}</span><strong>${monitorEscape(name)}</strong></div>`).join("")}</div>
        </article>
        <article class="content-card monitor-pad">
          <div class="monitor-card-title"><h3>Remediation Tasks</h3><strong>${done}/${risk.remediation_steps.length} Complete</strong></div>
          <div class="monitor-remediation">${risk.remediation_steps.map(step => `<div class="${step.done ? "done" : ""}"><b>${step.done ? "✓" : "○"}</b><span>${monitorEscape(step.label)}</span>${!step.done ? riskActionButton(step.key) : ""}</div>`).join("")}</div>
          <div class="monitor-actions"><button id="monitor-back-task" class="tb-btn" type="button">Back to Content Review</button></div>
        </article>
      </div>
    </div>`;
  root.querySelectorAll("[data-risk-action]").forEach(button => button.addEventListener("click", async () => {
    try {
      await api(`/monitoring/risks/${encodeURIComponent(risk.risk_code)}/actions/${encodeURIComponent(button.dataset.riskAction)}`, {method: "POST"});
      showStatus("Updated.");
      await loadMonitoringRisk(risk.risk_code);
      await loadMonitoringOverview();
    } catch (error) {
      showStatus(error.message, true);
    }
  }));
  document.getElementById("monitor-back-task").addEventListener("click", () => switchMonitoringView("review", {taskCode: risk.task?.task_code}));
}

function riskActionButton(key) {
  const labels = {notify: "Send Reminder", "new-version": "Confirm New Version", "legal-review": "Legal Review", "product-review": "Product Review", recheck: "Run Checks Again"};
  if (!labels[key]) return "";
  return `<button class="text-btn" data-risk-action="${monitorEscape(key)}" type="button">${labels[key]}</button>`;
}
