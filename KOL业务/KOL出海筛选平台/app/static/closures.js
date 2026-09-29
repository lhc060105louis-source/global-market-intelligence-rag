"use strict";

const closureState = {
  current: null,
  items: [],
  view: "overview",
};

const closureActionLabels = {
  created: "创建结案工作区",
  checks_updated: "更新结案核对项",
  issue_created: "新增遗留事项",
  issue_updated: "更新遗留事项",
  summary_updated: "保存结案摘要",
  submitted: "提交结案确认",
  returned: "退回补充",
  closed: "确认结案",
  revision_created: "建立修订版本",
};

function closureStatusClass(status) {
  if (["通过", "已解决"].includes(status)) return "pass";
  if (["closed", "已结案"].includes(status)) return "closed";
  if (["阻断", "阻断项"].includes(status)) return "block";
  if (["not_ready", "暂不能结案"].includes(status)) return "not-ready";
  if (["returned", "已退回"].includes(status)) return "returned";
  return "pending";
}

function closureStatus(text, raw = text) {
  return el("span", `closure-status ${closureStatusClass(raw)}`, text);
}

function closureDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", {hour12: false});
}

async function closureRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (window.__KOL_SESSION_TOKEN__) headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let message = `请求失败 ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (data.detail && data.detail.message) {
        message = data.detail.message;
        const issues = data.detail.issues || [];
        if (issues.length) message += `：${issues.slice(0, 3).map(item => item.message).join("；")}`;
      }
    } catch (_) { /* keep the status fallback */ }
    throw new Error(message);
  }
  return response.json();
}

function switchClosureView(view) {
  closureState.view = view;
  document.querySelectorAll("[data-closure-view]").forEach(node => {
    node.classList.toggle("active", node.dataset.closureView === view);
  });
  document.querySelectorAll(".closure-panel").forEach(node => {
    node.classList.toggle("active", node.id === `closure-${view}`);
  });
  if (view === "checks") renderClosureChecks();
  if (view === "archive") renderClosureArchive();
}

function updateClosureContext() {
  const box = document.getElementById("closure-context");
  const data = closureState.current;
  if (!data) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  clear(box);
  box.append(
    el("strong", "", data.project_name),
    document.createElement("br"),
    document.createTextNode(`${data.brand} · ${data.primary_market} · V${data.version} · `),
    closureStatus(data.status_label, data.status),
  );
}

function closureMetric(label, value, note, warning = false) {
  const card = el("article", `closure-metric${warning ? " warning" : ""}`);
  card.append(el("span", "", label), el("strong", "", String(value)), el("small", "", note));
  return card;
}

function readinessNode(value) {
  const wrapper = el("div", "closure-progress");
  const track = el("div", "closure-progress-track");
  const fill = el("div", "closure-progress-fill");
  fill.style.width = `${Math.max(0, Math.min(100, value || 0))}%`;
  track.append(fill);
  wrapper.append(track, el("small", "", `${Math.round(value || 0)}% 已完成`));
  return wrapper;
}

function renderClosureOverview(data) {
  const panel = document.getElementById("closure-overview");
  clear(panel);
  const metrics = el("div", "closure-metrics");
  metrics.append(
    closureMetric("待准备", data.metrics.not_ready, "仍有必需项未完成"),
    closureMetric("待确认", data.metrics.pending_confirmation, "等待品牌负责人确认"),
    closureMetric("已结案", data.metrics.closed, "已冻结最终版本"),
    closureMetric("阻断项", data.metrics.blocking, "需优先处理", data.metrics.blocking > 0),
  );

  const card = el("article", "closure-card");
  const heading = el("div", "closure-card-head");
  const text = el("div");
  text.append(el("h3", "", `项目清单 · ${data.total}`), el("p", "", "点击一行进入核对；未建立结案记录的项目会自动创建草稿。"));
  heading.append(text);

  const toolbar = el("form", "closure-toolbar");
  toolbar.id = "closure-filter-form";
  const search = document.createElement("input");
  search.name = "q";
  search.placeholder = "搜索项目名称或编号";
  const brand = document.createElement("select");
  brand.name = "brand";
  brand.append(new Option("全部品牌", ""), new Option("BYD", "BYD"), new Option("XPENG", "XPENG"));
  const market = document.createElement("select");
  market.name = "market";
  market.append(new Option("全部市场", ""), new Option("德国 DE", "DE"), new Option("英国 GB", "GB"));
  const status = document.createElement("select");
  status.name = "status";
  status.append(
    new Option("全部结案状态", ""), new Option("暂不能结案", "not_ready"),
    new Option("结案草稿", "draft"), new Option("待确认", "pending_confirmation"),
    new Option("已退回", "returned"), new Option("已结案", "closed"),
  );
  const submit = el("button", "tb-btn teal", "筛选");
  submit.type = "submit";
  const reset = el("button", "tb-btn", "重置");
  reset.type = "button";
  reset.addEventListener("click", () => loadClosureOverview());
  toolbar.append(search, brand, market, status, submit, reset);
  toolbar.addEventListener("submit", event => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(toolbar));
    [...params.keys()].forEach(key => { if (!params.get(key)) params.delete(key); });
    loadClosureOverview(params).catch(error => showStatus(error.message, true));
  });

  const tableWrap = el("div", "table-wrap");
  if (!data.items.length) {
    tableWrap.append(el("div", "closure-empty", "当前筛选条件下没有项目。请先在“项目立项”中建立项目。"));
  } else {
    const table = el("table", "closure-table");
    const thead = document.createElement("thead");
    const header = document.createElement("tr");
    ["项目", "品牌/市场", "负责人", "计划结束", "结案准备度", "遗留/阻断", "状态"].forEach(label => header.append(el("th", "", label)));
    thead.append(header);
    const tbody = document.createElement("tbody");
    data.items.forEach(item => {
      const row = document.createElement("tr");
      row.dataset.campaignId = item.campaign_id;
      const project = document.createElement("td");
      project.append(el("strong", "", item.project_name), el("div", "closure-note", item.campaign_id));
      const brandMarket = document.createElement("td");
      brandMarket.append(el("strong", "", item.brand), el("div", "closure-note", (item.markets || []).join(" / ")));
      const progress = document.createElement("td");
      progress.append(readinessNode(item.readiness));
      const counts = document.createElement("td");
      counts.append(document.createTextNode(`${item.open_issue_count} 项遗留`), document.createElement("br"));
      counts.append(closureStatus(`${item.blocking_count} 项阻断`, item.blocking_count ? "阻断" : "通过"));
      const stateCell = document.createElement("td");
      stateCell.append(closureStatus(item.closure_status_label, item.closure_status));
      row.append(project, brandMarket, el("td", "", item.owner), el("td", "", item.planned_end_date), progress, counts, stateCell);
      row.addEventListener("click", () => openClosureItem(item));
      tbody.append(row);
    });
    table.append(thead, tbody);
    tableWrap.append(table);
  }
  card.append(heading, toolbar, tableWrap);
  panel.append(metrics, card);
}

async function loadClosureOverview(params = new URLSearchParams()) {
  const suffix = params.toString() ? `?${params}` : "";
  const data = await closureRequest(`/closures${suffix}`);
  closureState.items = data.items;
  renderClosureOverview(data);
  return data;
}

async function openClosureItem(item) {
  const data = item.closure_id
    ? await closureRequest(`/closures/${encodeURIComponent(item.closure_id)}`)
    : await closureRequest(`/closures/campaigns/${encodeURIComponent(item.campaign_id)}`, {
        method: "POST",
        body: JSON.stringify({actor: "项目负责人", actor_role: "project_owner"}),
      });
  closureState.current = data;
  updateClosureContext();
  switchClosureView(data.status === "closed" ? "archive" : "checks");
}

async function reloadCurrentClosure() {
  if (!closureState.current) return null;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(closureState.current.closure_id)}`);
  updateClosureContext();
  return closureState.current;
}

function closureSummaryStrip(data) {
  const strip = el("div", "closure-summary-strip");
  [
    ["结案状态", data.status_label],
    ["准备度", `${Math.round(data.readiness)}%`],
    ["开放遗留事项", `${data.open_issue_count} 项`],
    ["当前版本", `V${data.version} · 修订 ${data.revision}`],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.append(el("span", "", label), el("strong", "", value));
    strip.append(item);
  });
  return strip;
}

async function saveClosureCheck(checkKey, status) {
  const data = closureState.current;
  const note = status === "通过" ? "人工核对确认" : "需要补充核对";
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/checks`, {
    method: "PUT",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "项目负责人",
      actor_role: "project_owner",
      items: [{check_key: checkKey, status, note}],
    }),
  });
  updateClosureContext();
  renderClosureChecks();
  showStatus(status === "通过" ? "核对项已人工确认" : "核对项已标记为待确认");
}

function renderCheckTable(data) {
  const table = el("table", "closure-table");
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  ["核对维度", "当前状态", "来源与说明", "更新时间/确认人", "操作"].forEach(label => header.append(el("th", "", label)));
  thead.append(header);
  const tbody = document.createElement("tbody");
  data.checks.forEach(check => {
    const row = document.createElement("tr");
    row.className = `closure-check-row${check.system_blocking ? " system-blocking" : ""}`;
    const label = document.createElement("td");
    label.append(el("strong", "", check.label), el("div", "closure-note", check.required ? "必需项" : "建议项"));
    const status = document.createElement("td");
    status.append(closureStatus(check.status));
    const detail = el("td", "closure-check-detail", check.detail);
    detail.append(el("div", "closure-note", `来源：${check.source}`));
    const confirmed = document.createElement("td");
    confirmed.append(document.createTextNode(closureDateTime(check.updated_at)), document.createElement("br"));
    confirmed.append(el("small", "", check.confirmed_by ? `人工确认：${check.confirmed_by}` : `系统状态：${check.automatic_status}`));
    const action = document.createElement("td");
    if (data.status !== "closed") {
      if (check.status !== "通过") {
        const pass = el("button", "tb-btn teal", "确认通过");
        pass.type = "button";
        pass.disabled = check.system_blocking;
        pass.title = check.system_blocking ? "重大风险需在风险模块关闭后才能通过" : "记录人工确认";
        pass.addEventListener("click", () => saveClosureCheck(check.key, "通过").catch(error => showStatus(error.message, true)));
        action.append(pass);
      } else if (check.confirmed_by) {
        const reopen = el("button", "tb-btn", "重新核对");
        reopen.type = "button";
        reopen.addEventListener("click", () => saveClosureCheck(check.key, "待确认").catch(error => showStatus(error.message, true)));
        action.append(reopen);
      } else {
        action.append(el("span", "closure-note", "系统已通过"));
      }
    } else {
      action.append(el("span", "closure-note", "版本已冻结"));
    }
    row.append(label, status, detail, confirmed, action);
    tbody.append(row);
  });
  table.append(thead, tbody);
  return table;
}

function issueForm(data) {
  const form = el("form", "closure-field-grid");
  const fields = [
    ["issue_type", "事项类型", "select", ["数据", "合同", "付款", "内容", "风险", "资产", "其他"]],
    ["severity", "严重程度", "select", ["普通", "重要", "阻断"]],
    ["title", "事项标题", "input"],
    ["owner", "负责人", "input"],
    ["due_date", "计划完成日期", "date"],
    ["source_reference", "来源记录", "input"],
  ];
  fields.forEach(([name, label, kind, options]) => {
    const wrap = el("label", "closure-field");
    wrap.append(el("span", "", label));
    let input;
    if (kind === "select") {
      input = document.createElement("select");
      options.forEach(value => input.append(new Option(value, value)));
    } else {
      input = document.createElement("input");
      input.type = kind === "date" ? "date" : "text";
    }
    input.name = name;
    input.required = name !== "source_reference";
    if (name === "due_date") {
      const due = new Date();
      due.setDate(due.getDate() + 7);
      input.value = due.toISOString().slice(0, 10);
    }
    wrap.append(input);
    form.append(wrap);
  });
  const desc = el("label", "closure-field wide");
  desc.append(el("span", "", "事项说明"));
  const textarea = document.createElement("textarea");
  textarea.name = "description";
  textarea.required = true;
  textarea.placeholder = "说明未完成内容、当前进展和需要的处理结果";
  desc.append(textarea);
  form.append(desc);
  const actions = el("div", "closure-actions end wide");
  const submit = el("button", "tb-btn teal", "+ 新增遗留事项");
  submit.type = "submit";
  actions.append(submit);
  form.append(actions);
  form.addEventListener("submit", event => addClosureIssue(event, data));
  return form;
}

async function addClosureIssue(event, data) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/issues`, {
    method: "POST",
    body: JSON.stringify({
      ...values,
      expected_revision: data.revision,
      actor: "项目负责人",
      actor_role: "project_owner",
    }),
  });
  closureState.current = response.closure;
  updateClosureContext();
  renderClosureChecks();
  showStatus("遗留事项已新增");
}

async function changeClosureIssue(issue, status) {
  let note = null;
  if (["已解决", "接受遗留"].includes(status)) {
    note = window.prompt(status === "已解决" ? "请填写解决说明" : "请填写接受遗留的原因");
    if (!note) return;
  }
  const data = closureState.current;
  closureState.current = await closureRequest(
    `/closures/${encodeURIComponent(data.closure_id)}/issues/${encodeURIComponent(issue.issue_id)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        expected_revision: data.revision,
        actor: "项目负责人",
        actor_role: "project_owner",
        status,
        resolution_note: note,
      }),
    },
  );
  updateClosureContext();
  renderClosureChecks();
  showStatus("遗留事项状态已更新");
}

function renderIssues(data) {
  if (!data.issues.length) return el("div", "closure-empty", "暂无遗留事项。普通缺口也应明确负责人和截止时间。" );
  const table = el("table", "closure-table");
  const head = document.createElement("tr");
  ["事项", "类型/等级", "负责人/截止时间", "状态", "操作"].forEach(label => head.append(el("th", "", label)));
  const thead = document.createElement("thead"); thead.append(head);
  const tbody = document.createElement("tbody");
  data.issues.forEach(issue => {
    const row = document.createElement("tr");
    const title = document.createElement("td");
    title.append(el("strong", "", issue.title), el("div", "closure-note", issue.description));
    const type = document.createElement("td");
    type.append(document.createTextNode(issue.issue_type), document.createElement("br"), closureStatus(issue.severity, issue.severity === "阻断" ? "阻断" : "待确认"));
    const owner = document.createElement("td");
    owner.append(document.createTextNode(issue.owner), document.createElement("br"), el("small", "", issue.due_date || "—"));
    const status = document.createElement("td");
    status.append(closureStatus(issue.status, issue.status));
    if (issue.resolution_note) status.append(el("div", "closure-note", issue.resolution_note));
    const action = el("td", "closure-actions");
    if (data.status !== "closed" && issue.status !== "已解决") {
      const process = el("button", "tb-btn", "处理中");
      process.type = "button";
      process.disabled = issue.status === "处理中";
      process.addEventListener("click", () => changeClosureIssue(issue, "处理中").catch(error => showStatus(error.message, true)));
      const resolve = el("button", "tb-btn teal", "标记解决");
      resolve.type = "button";
      resolve.addEventListener("click", () => changeClosureIssue(issue, "已解决").catch(error => showStatus(error.message, true)));
      action.append(process, resolve);
      if (issue.severity !== "阻断") {
        const accept = el("button", "tb-btn", "接受遗留");
        accept.type = "button";
        accept.addEventListener("click", () => changeClosureIssue(issue, "接受遗留").catch(error => showStatus(error.message, true)));
        action.append(accept);
      }
    }
    row.append(title, type, owner, status, action);
    tbody.append(row);
  });
  table.append(thead, tbody);
  return table;
}

function renderClosureChecks() {
  const panel = document.getElementById("closure-checks");
  const data = closureState.current;
  clear(panel);
  if (!data) {
    panel.append(el("div", "closure-empty", "请先从 M1 项目总览选择一项。"));
    return;
  }
  panel.append(closureSummaryStrip(data));

  const checks = el("article", "closure-card");
  const checkHead = el("div", "closure-card-head");
  const checkText = el("div");
  checkText.append(el("h3", "", "结案核对清单"), el("p", "", "系统状态与人工确认分开显示；重大风险未关闭时会持续阻断。"));
  checkHead.append(checkText, readinessNode(data.readiness));
  checks.append(checkHead, renderCheckTable(data));

  const grid = el("div", "closure-grid");
  const issues = el("article", "closure-card");
  const issueHead = el("div", "closure-card-head");
  const issueText = el("div");
  issueText.append(el("h3", "", `遗留事项 · ${data.issues.length}`), el("p", "", "保留问题、责任人、完成时点和处理结论。"));
  issueHead.append(issueText);
  issues.append(issueHead, renderIssues(data));
  const add = el("article", "closure-card");
  const addHead = el("div", "closure-card-head");
  const addText = el("div");
  addText.append(el("h3", "", "新增遗留事项"), el("p", "", "阻断事项必须解决，不能直接接受遗留。"));
  addHead.append(addText);
  add.append(addHead);
  if (data.status === "closed") add.append(el("div", "closure-empty", "该版本已经冻结，无法新增事项。"));
  else add.append(issueForm(data));
  grid.append(issues, add);

  const footer = el("div", "closure-actions end");
  const next = el("button", "tb-btn teal", "下一步：填写结案摘要 →");
  next.type = "button";
  next.addEventListener("click", () => switchClosureView("archive"));
  footer.append(next);
  panel.append(checks, grid, footer);
}

function summaryForm(data) {
  const summary = data.summary || {};
  const form = el("form", "closure-field-grid");
  const objective = el("label", "closure-field");
  objective.append(el("span", "", "目标总体判断"));
  const select = document.createElement("select");
  select.name = "objective_result";
  ["待确认", "达成", "部分达成", "未达成"].forEach(value => select.append(new Option(value, value)));
  select.value = summary.objective_result || "待确认";
  objective.append(select);
  const fields = [
    ["executive_summary", "管理层摘要", "用三至五句话说明目标、结果、原因和下一步。"],
    ["key_results", "核心业务结果", "引用后期复盘的核心 KPI 和数据口径，不在此重新计算。"],
    ["top_kols", "表现较好的 KOL", "填写 KOL、主要贡献与可复用经验。"],
    ["risk_kols", "谨慎或暂停合作的 KOL", "填写风险事实与当前名单治理状态；没有时写“无”。"],
    ["lessons_learned", "项目经验", "说明有效做法与需要改进的环节。"],
    ["next_action", "下一轮建议", "继续合作、调整策略、补充研究或不再推进。"],
  ];
  form.append(objective);
  fields.forEach(([name, label, placeholder], index) => {
    const wrap = el("label", `closure-field${index < 2 ? " wide" : ""}`);
    wrap.append(el("span", "", label));
    const input = document.createElement("textarea");
    input.name = name;
    input.required = true;
    input.placeholder = placeholder;
    input.value = summary[name] || "";
    wrap.append(input);
    form.append(wrap);
  });
  const actions = el("div", "closure-actions end wide");
  const save = el("button", "tb-btn teal", "保存结案摘要");
  save.type = "submit";
  save.disabled = data.status === "closed";
  actions.append(save);
  form.append(actions);
  form.addEventListener("submit", saveClosureSummary);
  return form;
}

async function saveClosureSummary(event) {
  event.preventDefault();
  const data = closureState.current;
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/summary`, {
    method: "PUT",
    body: JSON.stringify({
      ...values,
      expected_revision: data.revision,
      actor: "业务分析",
      actor_role: "business_analyst",
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus("结案摘要已保存");
}

async function submitCurrentClosure() {
  const data = closureState.current;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/submit`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "项目负责人",
      actor_role: "project_owner",
      reason: "结案核对与摘要已完成",
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus("结案材料已提交，等待品牌负责人确认");
}

async function decideCurrentClosure(decision) {
  const data = closureState.current;
  let reason = null;
  if (decision === "退回补充") {
    reason = window.prompt("请填写退回原因");
    if (!reason) return;
  } else if (!window.confirm("确认结案后，本版本将冻结为只读。是否继续？")) {
    return;
  }
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/decision`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "品牌负责人",
      actor_role: "brand_owner",
      decision,
      reason,
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus(decision === "确认结案" ? "项目已结案，最终版本已冻结" : "结案材料已退回补充");
}

async function reviseCurrentClosure() {
  const data = closureState.current;
  const reason = window.prompt("请填写建立修订版本的原因");
  if (!reason) return;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/revise`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "项目负责人",
      actor_role: "project_owner",
      reason,
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus(`已建立 V${closureState.current.version} 修订版本`);
}

function renderClosureArchive() {
  const panel = document.getElementById("closure-archive");
  const data = closureState.current;
  clear(panel);
  if (!data) {
    panel.append(el("div", "closure-empty", "请先从 M1 项目总览选择一项。"));
    return;
  }
  panel.append(closureSummaryStrip(data));
  const grid = el("div", "closure-grid");
  const summary = el("article", "closure-card");
  const summaryHead = el("div", "closure-card-head");
  const summaryText = el("div");
  summaryText.append(el("h3", "", "结案摘要"), el("p", "", "系统引用事实，最终业务判断由负责人确认。"));
  summaryHead.append(summaryText);
  summary.append(summaryHead, summaryForm(data));

  const side = document.createElement("div");
  const approval = el("article", "closure-card");
  const approvalHead = el("div", "closure-card-head");
  const approvalText = el("div");
  approvalText.append(el("h3", "", "提交与审批"), el("p", "", "提交时重新校验必需项、阻断项和摘要完整度。"));
  approvalHead.append(approvalText);
  approval.append(approvalHead);
  const actions = el("div", "closure-actions");
  if (["not_ready", "draft", "returned", "revised"].includes(data.status)) {
    const submit = el("button", "tb-btn teal", "提交结案确认");
    submit.type = "button";
    submit.addEventListener("click", () => submitCurrentClosure().catch(error => showStatus(error.message, true)));
    actions.append(submit);
  }
  if (data.status === "pending_confirmation") {
    const close = el("button", "tb-btn teal", "确认结案");
    close.type = "button";
    close.addEventListener("click", () => decideCurrentClosure("确认结案").catch(error => showStatus(error.message, true)));
    const reject = el("button", "tb-btn", "退回补充");
    reject.type = "button";
    reject.addEventListener("click", () => decideCurrentClosure("退回补充").catch(error => showStatus(error.message, true)));
    actions.append(close, reject);
  }
  if (data.status === "closed") {
    approval.append(closureStatus("最终版本只读", "已结案"));
    const revise = el("button", "tb-btn", "建立修订版本");
    revise.type = "button";
    revise.addEventListener("click", () => reviseCurrentClosure().catch(error => showStatus(error.message, true)));
    actions.append(revise);
  }
  approval.append(actions, el("p", "closure-note", data.blocking_count
    ? `当前仍有 ${data.blocking_count} 个阻断项，提交前必须处理。`
    : "没有系统阻断项；准备度达到 100% 且摘要完整后可以提交。"));

  const audit = el("article", "closure-card");
  const auditHead = el("div", "closure-card-head");
  const auditText = el("div");
  auditText.append(el("h3", "", "版本与操作记录"), el("p", "", "记录动作、角色、原因和时间，不覆盖历史。"));
  auditHead.append(auditText);
  audit.append(auditHead);
  const list = el("ul", "closure-audit");
  [...data.audits].reverse().slice(0, 10).forEach(item => {
    const row = document.createElement("li");
    row.append(el("strong", "", closureActionLabels[item.action] || item.action));
    row.append(document.createTextNode(` · ${item.actor}`));
    if (item.reason) row.append(el("div", "closure-note", item.reason));
    row.append(el("small", "", `V${item.version} · ${closureDateTime(item.created_at)}`));
    list.append(row);
  });
  if (!data.audits.length) list.append(el("li", "", "暂无操作记录"));
  audit.append(list);
  side.append(approval, audit);
  grid.append(summary, side);
  panel.append(grid);
}

function initClosureModule() {
  document.querySelectorAll("[data-closure-view]").forEach(button => {
    button.addEventListener("click", () => switchClosureView(button.dataset.closureView));
  });
}
