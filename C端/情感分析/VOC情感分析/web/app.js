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

  modelSelect.innerHTML = '<option value="">请选择车型</option>';

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
  if (task?.status === "failed") return { label: "失败", percent: 100 };
  if (analysisPayload.total) {
    return {
      label: `模型分析 ${analysisPayload.done}/${analysisPayload.total}`,
      percent: Math.round(analysisPayload.done / Math.max(1, analysisPayload.total) * 100),
    };
  }
  if (task?.status === "queued") return { label: "任务已创建，等待后台执行", percent: 8 };
  if (task?.status === "running") {
    const logs = task.logs || [];
    if (logs.some(log => log.step === "cleaned_items")) return { label: "清洗完成，准备分析", percent: 68 };
    if (logs.some(log => log.step === "raw_items")) return { label: "采集完成，正在清洗", percent: 52 };
    const runningSource = [...logs].reverse().find(log => log.status === "running" && String(log.step || "").startsWith("collect_"));
    return { label: runningSource ? `正在采集：${runningSource.step.replace("collect_", "")}` : "后台运行中", percent: 28 };
  }
  if (task?.status === "completed") return { label: "已完成", percent: 100 };
  if (task?.status === "partial_failed") return { label: "部分完成，请查看错误", percent: 100 };
  return { label: "等待开始", percent: 0 };
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
      <span class="eyebrow">当前任务</span>
      <h3>${escapeHtml(taskTitle(task))} · #${task.id}</h3>
      <p>${escapeHtml(task.error_message || "后台正在推进采集、清洗和分析流程。")}</p>
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
  range_lower_than_claimed: "实际续航低于宣传",
  other_unclassified: "其他未分类问题",
  charging_cost: "充电成本",
  service_no_response: "售后无响应",
  charging_failure: "充电故障",
  cabin_noise: "车内噪音",
  safety_warning: "安全警告",
};

const journeyNames = {
  full_journey: "全旅程反馈",
  pre_sales_awareness: "购车了解",
  purchase_consideration: "选车比较",
  purchase_delivery: "购买与交付",
  product_usage: "日常使用",
  after_sales_service: "售后服务",
  unknown: "未识别阶段",
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
  if (joined.includes("autohome") || joined.includes("汽车之家")) names.push("汽车之家");
  return names;
}

function taskTitle(task) {
  const config = safeJson(task?.config);
  if (task?.job_type === "file_import") return `文件导入 · ${config.filename || "未命名文件"}`;
  const names = sourceNames(task);
  const mode = Object.prototype.hasOwnProperty.call(config, "interval_minutes") ? "自动采集" : "实时采集";
  return `${names.length ? names.join(" + ") : "在线数据"} ${mode}`;
}

function taskStatus(task) {
  const pending = (task.cleaned_count || 0) > (task.analyzed_count || 0);
  if (task.status === "failed") return "失败";
  if (pending && !["queued", "running", "failed"].includes(task.status)) return "待分析";
  return statusText(task.status);
}

function taskStatusClass(task) {
  const pending = (task.cleaned_count || 0) > (task.analyzed_count || 0);
  return pending && !["queued", "running", "failed"].includes(task.status) ? "pending" : task.status;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function activeSources() {
  return [...document.querySelectorAll(".sourceCheck:checked")].map(item => item.value);
}

function statusText(status) {
  const map = {
    completed: "已完成",
    partial_failed: "部分完成",
    failed: "失败",
    running: "运行中",
    queued: "排队中",
  };
  return map[status] || status || "未知";
}

function pageTitle(page) {
  if (page === "result") return ["结果页", "一个任务对应一个结果页，只看当前任务数据"];
  return ["任务中心", "创建 CSV/XLSX 导入、实时采集或自动采集任务"];
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
    ["任务总数", total],
    ["进行中", running],
    ["已完成", completed],
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
            <p>创建于 ${escapeHtml(formatTime(task.started_at))}</p>
          </div>
        </div>
        <div class="taskMetrics">
          <span>清洗 <strong>${Math.max(task.cleaned_count || 0, task.analyzed_count || 0)}</strong></span>
          <span>重复 <strong>${task.duplicate_count || 0}</strong></span>
          <span>已分析 <strong>${task.analyzed_count || 0}</strong></span>
        </div>
        ${progressMarkup(task, true)}
        <span class="status ${taskStatusClass(task)}">${taskStatus(task)}</span>
        <div class="taskActions">
          ${canAnalyze ? `<button data-job="${task.id}" class="analyzeTask primaryBtn">开始分析</button>` : ""}
          <button data-job="${task.id}" class="openResult">打开结果页</button>
          <button data-job="${task.id}" class="deleteTask iconBtn" title="删除任务" aria-label="删除任务">删除</button>
        </div>
      </article>
    `;
  }).join("") || `<div class="emptyLine">还没有任务，先上传文件或创建采集任务。</div>`;
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
  if (value.includes("负面") || value.includes("negative")) return "negative";
  if (value.includes("正面") || value.includes("positive")) return "positive";
  if (value.includes("中性") || value.includes("neutral")) return "neutral";
  return "mixed";
}

function groupedSentiments(distribution) {
  const grouped = { positive: 0, neutral: 0, negative: 0, mixed: 0 };
  Object.entries(distribution || {}).forEach(([label, count]) => { grouped[sentimentGroup(label)] += Number(count || 0); });
  return grouped;
}

function renderDonut(target, distribution) {
  const grouped = groupedSentiments(distribution);
  const labels = { positive: "正面", neutral: "中性", negative: "负面", mixed: "混合" };
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
        <div><strong>${total}</strong><span>条反馈</span></div>
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
      <div class="barContent"><div><strong>${escapeHtml(humanName(item.name, dictionary))}</strong><span>${item.count} 次</span></div>
      <div class="barTrack"><i style="width:${Math.max(4, item.count / max * 100)}%"></i></div></div>
    </div>
  `).join("") || `<div class="clearState"><strong>暂无可排名的问题</strong><span>当前分析结果中没有提取到明确的抱怨主题。</span></div>`;
}

function renderStackedRows(target, rows, dictionary = {}) {
  const colors = { positive: "#16876b", neutral: "#7c8da6", negative: "#d64545", mixed: "#e2a93b" };
  const entries = Object.entries(rows || {});
  $(target).innerHTML = entries.map(([name, distribution]) => {
    const grouped = groupedSentiments(distribution);
    const total = Object.values(grouped).reduce((sum, value) => sum + value, 0);
    return `<div class="stackRow"><div><strong>${escapeHtml(humanName(name, dictionary))}</strong><span>${total} 条</span></div>
      <div class="stackBar">${Object.entries(grouped).filter(([, count]) => count).map(([key, count]) => (
        `<i title="${key} ${count}" style="width:${count / total * 100}%;background:${colors[key]}"></i>`
      )).join("")}</div></div>`;
  }).join("") || `<div class="clearState"><strong>暂无阶段数据</strong><span>当前反馈尚未识别到对应体验阶段。</span></div>`;
}

function renderOriginals(target, items, emptyMessage = "本任务没有触发高风险原文。") {
  $(target).innerHTML = (items || []).map(item => `
    <article class="original">
      <strong>${escapeHtml(item.sentiment_label || "风险反馈")}</strong>
      <p>${escapeHtml(item.text || "")}</p>
      <span>任务 #${item.job_id || ""} · ${escapeHtml(item.brand || "品牌未提及")} ${escapeHtml(item.model || "")} · ${escapeHtml(item.region || "地区未提及")}</span>
      ${/^https?:\/\/\S+$/i.test(item.source_url || "") ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">查看原始内容</a>` : ""}
    </article>
  `).join("") || `<div class="clearState"><strong>未发现高风险原文</strong><span>${emptyMessage}</span></div>`;
}

function renderTrend(target, rows) {
  const values = rows || [];
  const max = Math.max(1, ...values.map(item => Number(item.total || 0)));
  $(target).innerHTML = values.length ? `<div class="trendChart">${values.map(item => {
    const totalHeight = Math.max(8, item.total / max * 150);
    const negativeHeight = item.total ? item.negative / item.total * totalHeight : 0;
    return `<div class="trendColumn" title="${item.date}：共 ${item.total} 条，负面 ${item.negative} 条">
      <div class="trendBars" style="height:${totalHeight}px"><i style="height:${negativeHeight}px"></i></div>
      <strong>${item.negative}</strong><span>${escapeHtml(String(item.date).slice(5))}</span>
    </div>`;
  }).join("")}</div><div class="trendLegend"><span><i class="all"></i>全部反馈</span><span><i class="negative"></i>负面反馈</span></div>`
    : `<div class="clearState"><strong>暂无趋势数据</strong><span>完成分析后，这里会按发布日期展示反馈变化。</span></div>`;
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

  $("resultTitle").textContent = task ? `${taskTitle(task)} · #${task.id}` : `任务 #${state.selectedJobId}`;
  $("resultMeta").textContent = task ? `${taskStatus(task)} · 创建于 ${formatTime(task.started_at)} · 清洗 ${Math.max(task.cleaned_count || 0, state.standardData?.total || 0)} 条 · 已分析 ${task.analyzed_count || 0} 条` : "只展示当前任务的数据";
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
    ["清洗后数据", Math.max(task?.cleaned_count || 0, state.standardData?.total || 0), "可进入分析的数据"],
    ["已完成分析", overview.analysis_completed_count || 0, "已生成洞察的反馈"],
    ["负面反馈", findings.negative_count ?? grouped.negative, "表达明确不满的问题"],
    ["高风险信号", overview.high_risk_count || 0, "命中危机判断条件"],
  ].map(([label, value, help]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${help}</small></div>`).join("");

  $("overviewSummary").innerHTML = [
    ["主要情感", findings.dominant_sentiment || "暂无"],
    ["负面占比", `${findings.negative_ratio || 0}%`],
    ["首要问题", humanName(findings.top_complaint?.name || "暂无", topicNames)],
    ["主要车型", findings.top_model?.name || "暂无"],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  renderDonut("sentimentChart", overview.sentiment_distribution);
  $("overviewFindings").innerHTML = [
    ["样本范围", `本次共分析 ${overview.total_results || 0} 条反馈`],
    ["负面情况", `发现 ${findings.negative_count || 0} 条负面反馈，占 ${findings.negative_ratio || 0}%`],
    ["集中问题", findings.top_complaint?.count ? `${humanName(findings.top_complaint.name, topicNames)}被提及 ${findings.top_complaint.count} 次` : "未提取到集中问题"],
    ["风险判断", overview.high_risk_count ? `发现 ${overview.high_risk_count} 条高风险信号` : "未发现高风险信号"],
  ].map(([label, value]) => `<div class="findingRow"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");

  renderStackedRows("journeyCurve", six.journey_sentiment_curve, journeyNames);
  const score = six.nps_prediction?.score ?? 0;
  $("npsBox").innerHTML = `<div class="nps"><div><strong>${score}</strong><span>/ 100</span></div><div class="scoreTrack"><i style="width:${Math.max(0, Math.min(100, score))}%"></i></div><p>基于 ${six.nps_prediction?.basis || 0} 条反馈的情绪估算，不等同于正式 NPS 问卷。</p></div>`;
  renderBarChart("sixComplaints", six.complaint_ranking, topicNames);
  renderStackedRows("brandAttitude", six.brand_attitude);
  renderOriginals("recallWarning", six.recall_warning?.items, "当前反馈未命中召回或批次安全相关表达。");
  renderOriginals("rightsRisk", six.rights_risk?.items, "当前反馈未命中投诉、法律或集体维权相关表达。");

  $("riskBanner").className = `riskBanner ${crisis.risk_level || "normal"}`;
  $("riskBanner").innerHTML = `<div><span>${crisis.risk_level === "alert" ? "风险告警" : crisis.risk_level === "watch" ? "持续关注" : "状态正常"}</span><h3>${escapeHtml(crisis.risk_title || "当前未发现危机信号")}</h3><p>${escapeHtml(crisis.risk_reason || "")}</p></div>`;
  const crisisSummary = crisis.summary || {};
  $("crisisSummary").innerHTML = [
    ["负面反馈", crisisSummary.negative_count || 0, `${crisisSummary.negative_ratio || 0}%`],
    ["高风险", crisisSummary.high_risk_count || 0, crisisSummary.high_risk_count ? "需优先核查" : "未触发"],
    ["召回信号", crisisSummary.recall_count || 0, crisisSummary.recall_count ? "安全/批次问题" : "未触发"],
    ["维权信号", crisisSummary.rights_count || 0, crisisSummary.rights_count ? "投诉/法律行动" : "未触发"],
  ].map(([label, value, note]) => `<div><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join("");
  renderTrend("negativeTrend", crisis.daily_trend);
  $("alertTimeline").innerHTML = (crisis.alert_timeline || []).map(item => (
    `<div class="alertRow"><span>${escapeHtml(item.date)}</span><strong>触发 ${item.high_risk || 0} 条高风险信号</strong></div>`
  )).join("") || `<div class="clearState"><strong>本任务没有告警记录</strong><span>未检测到召回、维权或其他高危关键词。</span></div>`;
  renderOriginals("crisisOriginals", crisis.high_risk_originals);
  renderStandardData();
}

function renderStandardData() {
  const data = state.standardData || { items: [], total: 0, limit: 50, offset: 0 };
  const fields = ["source_id", "channel", "published_at", "language", "region", "brand", "model", "text", "source_url"];
  $("standardDataMeta").textContent = `来源：${data.source || "unknown"} · 清洗后共 ${data.total || 0} 条 · 统一为 9 个字段`;
  $("standardDataBody").innerHTML = (data.items || []).map(item => `
    <tr>${fields.map(field => {
      const value = item[field] || "";
      if (field === "source_url" && /^https?:\/\/\S+$/i.test(value)) {
        return `<td class="urlCell"><a href="${escapeHtml(value)}" target="_blank" rel="noreferrer">查看原文</a></td>`;
      }
      return `<td class="${field === "text" ? "textCell" : ""}" title="${escapeHtml(value)}">${escapeHtml(value) || "-"}</td>`;
    }).join("")}</tr>
  `).join("") || `<tr><td colspan="9" class="tableEmpty">这个任务还没有清洗后的数据</td></tr>`;
  const page = Math.floor((data.offset || 0) / (data.limit || 50)) + 1;
  const pages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 50)));
  $("dataPageLabel").textContent = `第 ${page} / ${pages} 页`;
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
    button.textContent = "分析中...";
  }
  try {
    const result = await api(`/api/tasks/${jobId}/analyze`, { method: "POST" });
    if (result.queued) {
      toast(`任务 #${jobId} 已进入后台分析`);
      startPolling(jobId);
    } else {
      toast(result.analyzed_now ? `任务 #${jobId} 已分析 ${result.analyzed_now} 条` : "该任务没有待分析数据");
    }
    await refresh();
    if (state.page === "result" && String(state.selectedJobId) === String(jobId)) await loadResult(jobId);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "开始分析";
    }
  }
}

async function deleteTask(jobId) {
  if (!window.confirm(`确定删除任务 #${jobId}？该任务的原始数据、分析结果和日志都会一起删除。`)) return;
  await api(`/api/tasks/${jobId}`, { method: "DELETE" });
  toast(`任务 #${jobId} 已删除`);
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
  $("monitorState").textContent = monitor.enabled ? "已启用" : "未启用";
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

$("refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")).catch(err => toast(err.message)));
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
  if (!file) return toast("请选择 CSV 或 XLSX");
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api(`/api/import?analyze=${$("fileAnalyze").checked ? "1" : "0"}`, { method: "POST", body: form });
    toast(result.duplicate_upload ? `同一文件已存在，打开任务 #${result.job_id}` : `任务 #${result.job_id} 已创建`);
    await refresh();
    await loadResult(result.job_id);
  } catch (err) {
    toast(err.message);
  }
});

$("crawlBtn").addEventListener("click", async () => {
  const button = $("crawlBtn");

  if (!brandSelect.value || !modelSelect.value) {
    alert("请先选择品牌和车型");
    return;
  }

  button.disabled = true;
  button.textContent = "创建中...";

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
    
    toast(`任务 #${result.job_id} 已创建，后台采集中`);
    startPolling(result.job_id);
    await refresh();
    await loadResult(result.job_id, "data");
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "创建采集任务";
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
    $("monitorState").textContent = config.enabled ? "已启用" : "未启用";
    $("monitorState").className = `pill ${config.enabled ? "live" : "mutedPill"}`;
    toast("自动采集已保存");
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
    toast(result.ran ? "已运行一轮" : result.reason);
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
