const state = {
  tasks: [],
  selectedJobId: "",
  selectedTask: null,
  insights: null,
  standardData: null,
  dataOffset: 0,
  page: "tasks",
  tab: "overview",
  activeJobId: "",
  pollTimer: null,
};

const evModels = {
  "BYD": ["Atto 2", "Atto 3", "Dolphin", "Seal", "Sealion 7", "Seal U DM-i"],
  "MG": ["MG4 EV", "MG5 EV", "MG ZS EV", "Cyberster"],
  "Volkswagen": ["ID.3", "ID.4", "ID.5", "ID.7", "ID.7 Tourer"],
  "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
  "BMW": ["iX1", "iX2", "i4", "i5", "i7", "iX", "iX3"],
  "Mercedes-Benz": ["EQA", "EQB", "EQE", "EQS", "EQE SUV", "EQS SUV"],
  "Audi": ["Q4 e-tron", "Q6 e-tron", "A6 e-tron", "e-tron GT"],
  "Volvo": ["EX30", "EX40", "EC40", "EX90"],
  "Polestar": ["Polestar 2", "Polestar 3", "Polestar 4"],
  "Renault": ["Renault 5 E-Tech", "Megane E-Tech", "Scenic E-Tech"],
  "Peugeot": ["E-208", "E-2008", "E-3008", "E-5008"],
  "Citroën": ["ë-C3", "ë-C4", "ë-C4 X"],
  "Škoda": ["Enyaq", "Enyaq Coupé", "Elroq"],
  "Cupra": ["Born", "Tavascan"],
  "Hyundai": ["Kona Electric", "IONIQ 5", "IONIQ 6", "IONIQ 9"],
  "Kia": ["Niro EV", "EV3", "EV4", "EV5", "EV6", "EV9"]
};

const brandSelect = document.getElementById("brandSelect");
const modelSelect = document.getElementById("modelSelect");

brandSelect.addEventListener("change", () => {
  const brand = brandSelect.value;

  modelSelect.innerHTML = '<option value="">Select a vehicle model</option>';

  if (!brand || !evModels[brand]) return;

  evModels[brand].forEach(model => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    modelSelect.appendChild(option);
  });
});
function $(id) {
  return document.getElementById(id);
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 2800);
}

function latestLog(task, step) {
  const logs = task?.logs || [];
  for (let index = logs.length - 1; index >= 0; index -= 1) {
    if (!step || logs[index].step === step) return logs[index];
  }
  return null;
}

function logPayload(log) {
  if (!log) return {};
  try {
    return typeof log.payload === "string" ? JSON.parse(log.payload || "{}") : (log.payload || {});
  } catch {
    return {};
  }
}

function taskProgress(task) {
  const analysisLog = latestLog(task, "analysis_progress");
  const analysisPayload = logPayload(analysisLog);
  if (task?.status === "failed") return { label: "Failed", percent: 100 };
  if (analysisPayload.total) {
    return {
      label: `Analyzing ${analysisPayload.done}/${analysisPayload.total} records`,
      percent: Math.round(analysisPayload.done / Math.max(1, analysisPayload.total) * 100),
    };
  }
  if (task?.status === "queued") return { label: "Task created; waiting to start", percent: 8 };
  if (task?.status === "running") {
    const logs = task.logs || [];
    if (logs.some(log => log.step === "cleaned_items")) return { label: "Cleaning complete; preparing analysis", percent: 68 };
    if (logs.some(log => log.step === "raw_items")) return { label: "Collection complete; cleaning records", percent: 52 };
    const runningSource = [...logs].reverse().find(log => log.status === "running" && String(log.step || "").startsWith("collect_"));
    return { label: runningSource ? `Collecting: ${runningSource.step.replace("collect_", "")}` : "Running in background", percent: 28 };
  }
  if (task?.status === "completed") return { label: "Completed", percent: 100 };
  if (task?.status === "partial_failed") return { label: "Partially completed; check errors", percent: 100 };
  return { label: "Waiting to start", percent: 0 };
}

function progressMarkup(task, compact = false) {
  const progress = taskProgress(task);
  const failed = ["failed", "partial_failed"].includes(task?.status);
  return `
    <div class="progressBlock ${failed ? "failed" : ""} ${compact ? "compact" : ""}">
      <div class="progressText"><span>${escapeHtml(progress.label)}</span><strong>${progress.percent}%</strong></div>
      <div class="progressTrack"><i style="width:${Math.max(4, Math.min(100, progress.percent))}%"></i></div>
    </div>
  `;
}

function renderActiveTaskProgress(task) {
  const panel = $("activeTaskProgress");
  if (!panel) return;
  if (!task || !["queued", "running", "failed", "partial_failed"].includes(task.status)) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <div>
      <span class="eyebrow">Current Task</span>
      <h3>${escapeHtml(taskTitle(task))} · #${task.id}</h3>
      <p>${escapeHtml(task.error_message || "Collection, cleaning, and analysis are running in the background.")}</p>
    </div>
    ${progressMarkup(task)}
  `;
}

function startPolling(jobId = "") {
  if (jobId) state.activeJobId = String(jobId);
  if (state.pollTimer) return;
  state.pollTimer = setInterval(() => {
    refresh({ silent: true }).catch(err => toast(err.message));
  }, 1000);
}

function stopPollingIfIdle() {
  const active = state.tasks.some(task => ["queued", "running"].includes(task.status));
  if (!active && state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function lines(value) {
  return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

const topicNames = {
  range_lower_than_claimed: "Real-world range below claims",
  other_unclassified: "Other unclassified issue",
  charging_cost: "Charging cost",
  service_no_response: "No after-sales response",
  charging_failure: "Charging failure",
  cabin_noise: "Cabin noise",
  safety_warning: "Safety warning",
};

const journeyNames = {
  full_journey: "Full customer journey",
  pre_sales_awareness: "Pre-purchase research",
  purchase_consideration: "Vehicle comparison",
  purchase_delivery: "Purchase and delivery",
  product_usage: "Daily use",
  after_sales_service: "After-sales service",
  unknown: "Unidentified stage",
};

function humanName(value, dictionary = {}) {
  const key = String(value || "unknown");
  return dictionary[key] || key.replaceAll("_", " ");
}

function sourceNames(task) {
  const values = [];
  try { values.push(...JSON.parse(task?.sources || "[]")); } catch { /* malformed legacy config */ }
  values.push(task?.source || "");
  const joined = values.join(" ").toLowerCase();
  const names = [];
  if (joined.includes("youtube")) names.push("YouTube");
  if (joined.includes("autohome")) names.push("Autohome");
  return names;
}

function taskTitle(task) {
  const config = safeJson(task?.config);
  if (task?.job_type === "file_import") return `File import · ${config.filename || "Untitled file"}`;
  const names = sourceNames(task);
  const mode = Object.prototype.hasOwnProperty.call(config, "interval_minutes") ? "Scheduled collection" : "Live collection";
  return `${names.length ? names.join(" + ") : "Online data"} · ${mode}`;
}

function taskStatus(task) {
  const pending = (task.cleaned_count || 0) > (task.analyzed_count || 0);
  if (task.status === "failed") return "Failed";
  if (pending && !["queued", "running", "failed"].includes(task.status)) return "Pending analysis";
  return statusText(task.status);
}

function taskStatusClass(task) {
  const pending = (task.cleaned_count || 0) > (task.analyzed_count || 0);
  return pending && !["queued", "running", "failed"].includes(task.status) ? "pending" : task.status;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("en-US", { hour12: false });
}

function activeSources() {
  return [...document.querySelectorAll(".sourceCheck:checked")].map(item => item.value);
}

function statusText(status) {
  const map = {
    completed: "Completed",
    partial_failed: "Partially completed",
    failed: "Failed",
    running: "Running",
    queued: "Queued",
  };
  return map[status] || status || "Unknown";
}

function pageTitle(page) {
  if (page === "result") return ["Results", "Each task has its own results page, showing only its data"];
  return ["Task Center", "Create a CSV/XLSX import, live collection, or scheduled collection task"];
}

function setPage(page, jobId = "") {
  state.page = page;
  if (jobId) state.selectedJobId = String(jobId);
  const [title, meta] = pageTitle(page);
  $("pageTitle").textContent = title;
  $("pageMeta").textContent = meta;
  $("tasksPage").classList.toggle("active", page === "tasks");
  $("resultPage").classList.toggle("active", page === "result");
  document.querySelectorAll(".nav").forEach(button => {
    button.classList.toggle("active", button.dataset.page === page);
  });
  history.replaceState(null, "", page === "result" && state.selectedJobId ? `#/results/${state.selectedJobId}` : "#/tasks");
  renderResultShell();
}

function setTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(button => button.classList.toggle("active", button.dataset.tab === tab));
  document.querySelectorAll(".tabPage").forEach(page => page.classList.toggle("active", page.id === `${tab}Tab`));
}

function renderTaskSummary() {
  const total = state.tasks.length;
  const running = state.tasks.filter(task => ["running", "queued"].includes(task.status)).length;
  const completed = state.tasks.filter(task => task.status === "completed").length;
  $("taskSummary").innerHTML = [
    ["Total Tasks", total],
    ["In Progress", running],
    ["Completed", completed],
  ].map(([label, value]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join("");
}

function renderTasks() {
  renderTaskSummary();
  const sequenceById = new Map(
    [...state.tasks]
      .sort((left, right) => {
        const leftTime = Date.parse(left.started_at || "") || 0;
        const rightTime = Date.parse(right.started_at || "") || 0;
        return leftTime - rightTime || Number(left.id || 0) - Number(right.id || 0);
      })
      .map((task, index) => [String(task.id), index + 1])
  );
  const orderedTasks = [...state.tasks].sort((left, right) => {
    const rank = task => {
      const pending = (task.cleaned_count || 0) > (task.analyzed_count || 0);
      if (["queued", "running"].includes(task.status)) return 0;
      if (pending && task.status !== "failed") return 1;
      if (task.status === "completed") return 2;
      if (task.status === "partial_failed") return 3;
      if (task.status === "failed") return 4;
      return 5;
    };
    return rank(left) - rank(right) || Number(right.id || 0) - Number(left.id || 0);
  });
  $("taskList").innerHTML = orderedTasks.map(task => {
    const canAnalyze = (task.cleaned_count || 0) > (task.analyzed_count || 0)
      && !["queued", "running"].includes(task.status);
    return `
      <article class="taskCard ${task.status === "failed" ? "failedTask" : ""}">
        <div class="taskMain">
          <strong>#${sequenceById.get(String(task.id)) || ""}</strong>
          <div>
            <h4>${escapeHtml(taskTitle(task))}</h4>
            <p>Created ${escapeHtml(formatTime(task.started_at))}</p>
          </div>
        </div>
        <div class="taskMetrics">
          <span>Cleaned <strong>${Math.max(task.cleaned_count || 0, task.analyzed_count || 0)}</strong></span>
          <span>Duplicates <strong>${task.duplicate_count || 0}</strong></span>
          <span>Analyzed <strong>${task.analyzed_count || 0}</strong></span>
        </div>
        ${progressMarkup(task, true)}
        <span class="status ${taskStatusClass(task)}">${taskStatus(task)}</span>
        <div class="taskActions">
          ${canAnalyze ? `<button data-job="${task.id}" class="analyzeTask primaryBtn">Analyze</button>` : ""}
          <button data-job="${task.id}" class="openResult">Open Results</button>
          <button data-job="${task.id}" class="deleteTask iconBtn" title="Delete Task" aria-label="Delete Task">Delete</button>
        </div>
      </article>
    `;
  }).join("") || `<div class="emptyLine">No tasks yet. Upload a file or create a collection task.</div>`;
}

function safeJson(value) {
  try {
    return JSON.parse(value || "{}");
  } catch {
    return {};
  }
}

function renderResultShell() {
  const hasTask = state.page === "result" && state.selectedJobId;
  $("emptyResult").style.display = hasTask ? "none" : "grid";
  $("resultContent").style.display = hasTask ? "block" : "none";
}

function sentimentGroup(label) {
  const value = String(label || "").toLowerCase();
  if (value.includes("negative")) return "negative";
  if (value.includes("positive")) return "positive";
  if (value.includes("neutral")) return "neutral";
  return "mixed";
}

function groupedSentiments(distribution) {
  const grouped = { positive: 0, neutral: 0, negative: 0, mixed: 0 };
  Object.entries(distribution || {}).forEach(([label, count]) => { grouped[sentimentGroup(label)] += Number(count || 0); });
  return grouped;
}

function renderDonut(target, distribution) {
  const grouped = groupedSentiments(distribution);
  const labels = { positive: "Positive", neutral: "Neutral", negative: "Negative", mixed: "Mixed" };
  const colors = { positive: "#16876b", neutral: "#7c8da6", negative: "#d64545", mixed: "#e2a93b" };
  const total = Object.values(grouped).reduce((sum, value) => sum + value, 0);
  let cursor = 0;
  const segments = Object.entries(grouped).map(([key, count]) => {
    const start = cursor;
    cursor += total ? count / total * 100 : 0;
    return `${colors[key]} ${start}% ${cursor}%`;
  });
  $(target).innerHTML = `
    <div class="donutLayout">
      <div class="donut" style="background:${total ? `conic-gradient(${segments.join(",")})` : "#eef1f5"}">
        <div><strong>${total}</strong><span>records</span></div>
      </div>
      <div class="chartLegend">${Object.entries(grouped).map(([key, count]) => `
        <div><i style="background:${colors[key]}"></i><span>${labels[key]}</span><strong>${count}</strong><small>${total ? Math.round(count / total * 100) : 0}%</small></div>
      `).join("")}</div>
    </div>`;
}

function renderBarChart(target, items, dictionary = {}) {
  const rows = items || [];
  const max = Math.max(1, ...rows.map(item => Number(item.count || 0)));
  $(target).innerHTML = rows.map((item, index) => `
    <div class="barRow">
      <span class="barRank">${index + 1}</span>
      <div class="barContent"><div><strong>${escapeHtml(humanName(item.name, dictionary))}</strong><span>${item.count} mentions</span></div>
      <div class="barTrack"><i style="width:${Math.max(4, item.count / max * 100)}%"></i></div></div>
    </div>
  `).join("") || `<div class="clearState"><strong>No ranked issues</strong><span>No clear complaint topics were extracted from this task.</span></div>`;
}

function renderStackedRows(target, rows, dictionary = {}) {
  const colors = { positive: "#16876b", neutral: "#7c8da6", negative: "#d64545", mixed: "#e2a93b" };
  const entries = Object.entries(rows || {});
  $(target).innerHTML = entries.map(([name, distribution]) => {
    const grouped = groupedSentiments(distribution);
    const total = Object.values(grouped).reduce((sum, value) => sum + value, 0);
    return `<div class="stackRow"><div><strong>${escapeHtml(humanName(name, dictionary))}</strong><span>${total} records</span></div>
      <div class="stackBar">${Object.entries(grouped).filter(([, count]) => count).map(([key, count]) => (
        `<i title="${key} ${count}" style="width:${count / total * 100}%;background:${colors[key]}"></i>`
      )).join("")}</div></div>`;
  }).join("") || `<div class="clearState"><strong>No stage data</strong><span>No customer journey stages were identified in this feedback.</span></div>`;
}

function renderOriginals(target, items, emptyMessage = "No high-risk feedback was flagged for this task.") {
  $(target).innerHTML = (items || []).map(item => `
    <article class="original">
      <strong>${escapeHtml(item.sentiment_label || "Risk feedback")}</strong>
      <p>${escapeHtml(item.text || "")}</p>
      <span>Task #${item.job_id || ""} · ${escapeHtml(item.brand || "Brand not specified")} ${escapeHtml(item.model || "")} · ${escapeHtml(item.region || "Region not specified")}</span>
      ${/^https?:\/\/\S+$/i.test(item.source_url || "") ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">View original</a>` : ""}
    </article>
  `).join("") || `<div class="clearState"><strong>No high-risk feedback found</strong><span>${emptyMessage}</span></div>`;
}

function renderTrend(target, rows) {
  const values = rows || [];
  const max = Math.max(1, ...values.map(item => Number(item.total || 0)));
  $(target).innerHTML = values.length ? `<div class="trendChart">${values.map(item => {
    const totalHeight = Math.max(8, item.total / max * 150);
    const negativeHeight = item.total ? item.negative / item.total * totalHeight : 0;
    return `<div class="trendColumn" title="${item.date}: ${item.total} total, ${item.negative} negative">
      <div class="trendBars" style="height:${totalHeight}px"><i style="height:${negativeHeight}px"></i></div>
      <strong>${item.negative}</strong><span>${escapeHtml(String(item.date).slice(5))}</span>
    </div>`;
  }).join("")}</div><div class="trendLegend"><span><i class="all"></i>All feedback</span><span><i class="negative"></i>Negative feedback</span></div>`
    : `<div class="clearState"><strong>No trend data</strong><span>Feedback trends by publication date will appear after analysis.</span></div>`;
}

function renderInsights() {
  if (!state.selectedJobId || !state.insights) {
    renderResultShell();
    return;
  }
  const task = state.selectedTask || state.tasks.find(item => String(item.id) === String(state.selectedJobId));
  const overview = state.insights.overview || {};
  const six = state.insights.six_dimensions || {};
  const crisis = state.insights.crisis_monitoring || {};

  $("resultTitle").textContent = task ? `${taskTitle(task)} · #${task.id}` : `Task #${state.selectedJobId}`;
  $("resultMeta").textContent = task ? `${taskStatus(task)} · Created ${formatTime(task.started_at)} · Cleaned ${Math.max(task.cleaned_count || 0, state.standardData?.total || 0)} · Analyzed ${task.analyzed_count || 0}` : "Showing data for the selected task only";
  const resultProgress = $("resultProgress");
  if (task && ["queued", "running", "failed", "partial_failed"].includes(task.status)) {
    resultProgress.hidden = false;
    resultProgress.innerHTML = progressMarkup(task);
  } else {
    resultProgress.hidden = true;
    resultProgress.innerHTML = "";
  }
  const canAnalyze = task && (task.cleaned_count || 0) > (task.analyzed_count || 0)
    && !["queued", "running"].includes(task.status);
  $("resultAnalyzeBtn").style.display = canAnalyze ? "inline-flex" : "none";
  const findings = overview.key_findings || {};
  const grouped = groupedSentiments(overview.sentiment_distribution);
  $("resultStats").innerHTML = [
    ["Cleaned Records", Math.max(task?.cleaned_count || 0, state.standardData?.total || 0), "Records ready for analysis"],
    ["Analyzed Records", overview.analysis_completed_count || 0, "Feedback with generated insights"],
    ["Negative Feedback", findings.negative_count ?? grouped.negative, "Records expressing dissatisfaction"],
    ["High-Risk Signals", overview.high_risk_count || 0, "Records matching risk criteria"],
  ].map(([label, value, help]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${help}</small></div>`).join("");

  $("overviewSummary").innerHTML = [
    ["Dominant Sentiment", findings.dominant_sentiment || "None"],
    ["Negative Share", `${findings.negative_ratio || 0}%`],
    ["Top Issue", humanName(findings.top_complaint?.name || "None", topicNames)],
    ["Top Vehicle Model", findings.top_model?.name || "None"],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  renderDonut("sentimentChart", overview.sentiment_distribution);
  $("overviewFindings").innerHTML = [
    ["Sample Size", `${overview.total_results || 0} feedback records analyzed`],
    ["Negative Feedback", `${findings.negative_count || 0} negative records (${findings.negative_ratio || 0}%)`],
    ["Top Issue", findings.top_complaint?.count ? `${humanName(findings.top_complaint.name, topicNames)} was mentioned ${findings.top_complaint.count} times` : "No dominant issue was extracted"],
    ["Risk Assessment", overview.high_risk_count ? `${overview.high_risk_count} high-risk signals found` : "No high-risk signals found"],
  ].map(([label, value]) => `<div class="findingRow"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");

  renderStackedRows("journeyCurve", six.journey_sentiment_curve, journeyNames);
  const score = six.nps_prediction?.score ?? 0;
  $("npsBox").innerHTML = `<div class="nps"><div><strong>${score}</strong><span>/ 100</span></div><div class="scoreTrack"><i style="width:${Math.max(0, Math.min(100, score))}%"></i></div><p>Sentiment estimate based on ${six.nps_prediction?.basis || 0} records; not a formal NPS survey result.</p></div>`;
  renderBarChart("sixComplaints", six.complaint_ranking, topicNames);
  renderStackedRows("brandAttitude", six.brand_attitude);
  renderOriginals("recallWarning", six.recall_warning?.items, "No recall or batch-safety language was found in this feedback.");
  renderOriginals("rightsRisk", six.rights_risk?.items, "No complaint, legal action, or collective claim language was found.");

  $("riskBanner").className = `riskBanner ${crisis.risk_level || "normal"}`;
  $("riskBanner").innerHTML = `<div><span>${crisis.risk_level === "alert" ? "Risk Alert" : crisis.risk_level === "watch" ? "Monitor" : "Normal"}</span><h3>${escapeHtml(crisis.risk_title || "No current crisis signals")}</h3><p>${escapeHtml(crisis.risk_reason || "")}</p></div>`;
  const crisisSummary = crisis.summary || {};
  $("crisisSummary").innerHTML = [
    ["Negative Feedback", crisisSummary.negative_count || 0, `${crisisSummary.negative_ratio || 0}%`],
    ["High Risk", crisisSummary.high_risk_count || 0, crisisSummary.high_risk_count ? "Review first" : "Not triggered"],
    ["Recall Signals", crisisSummary.recall_count || 0, crisisSummary.recall_count ? "Safety or batch issue" : "Not triggered"],
    ["Consumer Rights Signals", crisisSummary.rights_count || 0, crisisSummary.rights_count ? "Complaint or legal action" : "Not triggered"],
  ].map(([label, value, note]) => `<div><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join("");
  renderTrend("negativeTrend", crisis.daily_trend);
  $("alertTimeline").innerHTML = (crisis.alert_timeline || []).map(item => (
    `<div class="alertRow"><span>${escapeHtml(item.date)}</span><strong>${item.high_risk || 0} high-risk signals</strong></div>`
  )).join("") || `<div class="clearState"><strong>No alerts for this task</strong><span>No recall, consumer rights, or other high-risk keywords were detected.</span></div>`;
  renderOriginals("crisisOriginals", crisis.high_risk_originals);
  renderStandardData();
}

function renderStandardData() {
  const data = state.standardData || { items: [], total: 0, limit: 50, offset: 0 };
  const fields = ["source_id", "channel", "published_at", "language", "region", "brand", "model", "text", "source_url"];
  $("standardDataMeta").textContent = `Source: ${data.source || "unknown"} · ${data.total || 0} cleaned records · 9 standardized fields`;
  $("standardDataBody").innerHTML = (data.items || []).map(item => `
    <tr>${fields.map(field => {
      const value = item[field] || "";
      if (field === "source_url" && /^https?:\/\/\S+$/i.test(value)) {
        return `<td class="urlCell"><a href="${escapeHtml(value)}" target="_blank" rel="noreferrer">View source</a></td>`;
      }
      return `<td class="${field === "text" ? "textCell" : ""}" title="${escapeHtml(value)}">${escapeHtml(value) || "-"}</td>`;
    }).join("")}</tr>
  `).join("") || `<tr><td colspan="9" class="tableEmpty">No cleaned data is available for this task.</td></tr>`;
  const page = Math.floor((data.offset || 0) / (data.limit || 50)) + 1;
  const pages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 50)));
  $("dataPageLabel").textContent = `Page ${page} of ${pages}`;
  $("dataPrevBtn").disabled = (data.offset || 0) <= 0;
  $("dataNextBtn").disabled = (data.offset || 0) + (data.limit || 50) >= (data.total || 0);
}

async function loadStandardData(jobId) {
  state.standardData = await api(`/api/tasks/${jobId}/items?limit=50&offset=${state.dataOffset}`);
  renderStandardData();
}

async function loadResult(jobId, preferredTab = "") {
  if (String(state.selectedJobId) !== String(jobId)) state.dataOffset = 0;
  state.selectedJobId = String(jobId);
  const [detail, insights, standardData] = await Promise.all([
    api(`/api/tasks/${jobId}`),
    api(`/api/insights?job_id=${jobId}`),
    api(`/api/tasks/${jobId}/items?limit=50&offset=${state.dataOffset}`),
  ]);
  state.selectedTask = detail;
  state.insights = insights;
  state.standardData = standardData;
  setPage("result", jobId);
  renderInsights();
  setTab(preferredTab || ((detail.analyzed_count || 0) > 0 ? state.tab : "data"));
}

async function analyzeTask(jobId, button) {
  if (button) {
    button.disabled = true;
    button.textContent = "Analyzing...";
  }
  try {
    const result = await api(`/api/tasks/${jobId}/analyze`, { method: "POST" });
    if (result.queued) {
      toast(`Task #${jobId} queued for background analysis`);
      startPolling(jobId);
    } else {
      toast(result.analyzed_now ? `Task #${jobId}: analyzed ${result.analyzed_now} records` : "No pending records to analyze");
    }
    await refresh();
    if (state.page === "result" && String(state.selectedJobId) === String(jobId)) await loadResult(jobId);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Analyze";
    }
  }
}

async function deleteTask(jobId) {
  if (!window.confirm(`Delete task #${jobId}? Its source data, analysis results, and logs will also be deleted.`)) return;
  await api(`/api/tasks/${jobId}`, { method: "DELETE" });
  toast(`Task #${jobId} deleted`);
  if (String(state.selectedJobId) === String(jobId)) {
    state.selectedJobId = "";
    state.selectedTask = null;
    state.insights = null;
    setPage("tasks");
  }
  await refresh();
}

async function refresh(options = {}) {
  const tasks = await api("/api/tasks");
  state.tasks = tasks.tasks || [];
  renderTasks();
  const activeListTask = state.tasks.find(task => String(task.id) === String(state.activeJobId))
    || state.tasks.find(task => ["queued", "running"].includes(task.status));
  if (activeListTask) {
    try {
      renderActiveTaskProgress(await api(`/api/tasks/${activeListTask.id}`));
    } catch {
      renderActiveTaskProgress(activeListTask);
    }
  } else {
    renderActiveTaskProgress(null);
  }
  const monitor = await api("/api/monitor");
  $("monitorEnabled").checked = Boolean(monitor.enabled);
  $("monitorInterval").value = monitor.interval_minutes || 60;
  $("monitorConfig").textContent = JSON.stringify(monitor, null, 2);
  $("monitorState").textContent = monitor.enabled ? "Enabled" : "Disabled";
  $("monitorState").className = `pill ${monitor.enabled ? "live" : "mutedPill"}`;
  if (state.page === "result" && state.selectedJobId) {
    await loadResult(state.selectedJobId);
  }
  stopPollingIfIdle();
}

document.querySelectorAll(".nav").forEach(button => {
  button.addEventListener("click", () => setPage(button.dataset.page));
});

document.querySelectorAll(".tab").forEach(button => {
  button.addEventListener("click", () => setTab(button.dataset.tab));
});

$("refreshBtn").addEventListener("click", () => refresh().then(() => toast("Refreshed")).catch(err => toast(err.message)));
$("backBtn").addEventListener("click", () => setPage("tasks"));
$("backToTasksBtn").addEventListener("click", () => setPage("tasks"));

$("taskList").addEventListener("click", event => {
  const openButton = event.target.closest(".openResult");
  const analyzeButton = event.target.closest(".analyzeTask");
  const deleteButton = event.target.closest(".deleteTask");
  if (openButton) loadResult(openButton.dataset.job).catch(err => toast(err.message));
  if (analyzeButton) analyzeTask(analyzeButton.dataset.job, analyzeButton).catch(err => toast(err.message));
  if (deleteButton) deleteTask(deleteButton.dataset.job).catch(err => toast(err.message));
});

$("resultAnalyzeBtn").addEventListener("click", event => {
  analyzeTask(state.selectedJobId, event.currentTarget).catch(err => toast(err.message));
});

$("resultDeleteBtn").addEventListener("click", () => {
  deleteTask(state.selectedJobId).catch(err => toast(err.message));
});

$("dataPrevBtn").addEventListener("click", () => {
  state.dataOffset = Math.max(0, state.dataOffset - 50);
  loadStandardData(state.selectedJobId).catch(err => toast(err.message));
});

$("dataNextBtn").addEventListener("click", () => {
  state.dataOffset += 50;
  loadStandardData(state.selectedJobId).catch(err => toast(err.message));
});

$("uploadForm").addEventListener("submit", async event => {
  event.preventDefault();
  const file = $("fileInput").files[0];
  if (!file) return toast("Select a CSV or XLSX file.");
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api(`/api/import?analyze=${$("fileAnalyze").checked ? "1" : "0"}`, { method: "POST", body: form });
    toast(result.duplicate_upload ? `This file already exists. Opening task #${result.job_id}.` : `Task #${result.job_id} created.`);
    await refresh();
    await loadResult(result.job_id);
  } catch (err) {
    toast(err.message);
  }
});

$("crawlBtn").addEventListener("click", async () => {
  const button = $("crawlBtn");

  if (!brandSelect.value || !modelSelect.value) {
    alert("Select a brand and vehicle model first.");
    return;
  }

  button.disabled = true;
  button.textContent = "Creating...";

  try {
    const result = await api("/api/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sources: activeSources(),

        keywords: [
          `${brandSelect.value} ${modelSelect.value} owner review`
        ],

        autohome_urls: lines($("autohomeUrls").value),
        limit_per_source: Number($("limitInput").value || 10),
        auto_analyze: $("crawlAnalyze").checked,
      }),
    });
    
    toast(`Task #${result.job_id} created. Collection is running in the background.`);
    startPolling(result.job_id);
    await refresh();
    await loadResult(result.job_id, "data");
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Create Collection Task";
  }
});

$("saveMonitorBtn").addEventListener("click", async () => {
  try {
    const config = await api("/api/monitor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: $("monitorEnabled").checked,
        interval_minutes: Number($("monitorInterval").value || 60),
        sources: activeSources(),
        keywords: lines($("keywords").value),
        autohome_urls: lines($("autohomeUrls").value),
        limit_per_source: Number($("limitInput").value || 10),
        auto_analyze: $("crawlAnalyze").checked,
      }),
    });
    $("monitorConfig").textContent = JSON.stringify(config, null, 2);
    $("monitorState").textContent = config.enabled ? "Enabled" : "Disabled";
    $("monitorState").className = `pill ${config.enabled ? "live" : "mutedPill"}`;
    toast("Collection schedule saved.");
  } catch (err) {
    toast(err.message);
  }
});

$("runMonitorBtn").addEventListener("click", async () => {
  try {
    const result = await api("/api/monitor/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    toast(result.ran ? "Collection run completed." : result.reason);
    await refresh();
    if (result.summary?.job_id) await loadResult(result.summary.job_id);
  } catch (err) {
    toast(err.message);
  }
});

function initRoute() {
  const match = location.hash.match(/^#\/results\/(\d+)/);
  if (match) {
    loadResult(match[1]).catch(err => {
      toast(err.message);
      setPage("tasks");
    });
  } else {
    setPage("tasks");
  }
}

refresh().then(() => {
  if (state.tasks.some(task => ["queued", "running"].includes(task.status))) startPolling();
  initRoute();
}).catch(err => toast(err.message));
