"use strict";

const campaignState = {items: [], current: null, step: "M1"};

const CAMPAIGN_STATUS = {
  draft: "草稿",
  pending_approval: "待审批",
  approved: "已批准",
  executing: "执行中",
  completed: "已完成",
  archived: "已归档",
};

function campaignEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function campaignList(value) {
  return String(value || "").split(/[，,\n]/).map(item => item.trim()).filter(Boolean);
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
    let message = `请求失败 ${response.status}`;
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
    <div><span class="campaign-status status-${campaignEscape(project.status)}">${CAMPAIGN_STATUS[project.status] || project.status}</span><span>当前 V${project.current_version}${project.approved_version ? ` · 已批准 V${project.approved_version}` : ""}</span></div>`;
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
      <div class="empty-page"><div><h2>请先选择项目</h2><p>在M1项目总览中打开一个项目，再继续配置。</p><button class="tb-btn teal" id="campaign-back-list" type="button">返回项目总览</button></div></div>`;
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
      <article class="metric-card"><span>项目总数</span><strong>${items.length}</strong><small>当前筛选结果</small></article>
      <article class="metric-card"><span>草稿</span><strong>${count("draft")}</strong><small>仍需补齐配置</small></article>
      <article class="metric-card"><span>待审批</span><strong>${count("pending_approval")}</strong><small>等待人工决定</small></article>
      <article class="metric-card"><span>已批准</span><strong>${count("approved")}</strong><small>可发布下游交接包</small></article>
    </div>
    <form id="campaign-filter" class="filter-bar">
      <input name="q" placeholder="搜索项目名称或项目编号">
      <select name="brand"><option value="">全部品牌</option><option>BYD</option><option>XPENG</option></select>
      <select name="market"><option value="">全部市场</option><option value="DE">德国 DE</option><option value="GB">英国 GB</option></select>
      <select name="status"><option value="">全部状态</option><option value="draft">草稿</option><option value="pending_approval">待审批</option><option value="approved">已批准</option></select>
      <button class="tb-btn" type="submit">筛选</button>
      <button class="tb-btn" id="campaign-filter-reset" type="button">重置</button>
    </form>
    <article class="content-card">
      <div class="card-hd"><h2>项目清单 <span class="count">${items.length}</span></h2><span class="campaign-muted">仅显示未归档项目</span></div>
      <div class="table-wrap"><table class="campaign-table"><thead><tr><th>项目</th><th>品牌与市场</th><th>预算</th><th>状态</th><th>版本</th><th>负责人</th><th>操作</th></tr></thead><tbody id="campaign-list-body"></tbody></table></div>
      ${items.length ? "" : '<div class="empty-state">暂无项目，点击右上角“新建项目”开始配置。</div>'}
    </article>`;
  const body = document.getElementById("campaign-list-body");
  items.forEach(item => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${campaignEscape(item.project_name)}</strong><small>${campaignEscape(item.campaign_id)}</small></td>
      <td>${campaignEscape(item.brand)} · ${campaignEscape(item.vehicle_model)}<small>${item.markets.map(m => campaignEscape(m)).join(" / ")}</small></td>
      <td>${new Intl.NumberFormat("zh-CN").format(item.budget_total)} ${campaignEscape(item.currency)}</td>
      <td><span class="campaign-status status-${campaignEscape(item.status)}">${CAMPAIGN_STATUS[item.status] || item.status}</span></td>
      <td>V${item.current_version}<small>完整度 ${item.completion}%</small></td>
      <td>${campaignEscape(item.owner)}</td>
      <td><button class="text-btn campaign-open" type="button">打开</button></td>`;
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
  return `<div class="campaign-form-actions"><button class="tb-btn" data-back-m1 type="button">返回总览</button><button class="tb-btn teal" type="submit">${label}</button></div>`;
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
      <div class="card-hd"><div><h2>M2 项目基本信息与时间计划</h2><p>${isNew ? "填写必需信息后建立项目草稿。" : "草稿可分步保存；批准版本再次编辑会自动建立新版本。"}</p></div><span class="campaign-save-state">${isNew ? "尚未创建" : `Revision ${project.revision}`}</span></div>
      <form id="campaign-basic-form" class="campaign-form">
        <div class="campaign-form-grid">
          <label class="wide">项目名称<input name="project_name" maxlength="100" required value="${campaignEscape(project?.project_name)}" placeholder="例如 XPENG G6 英国试驾传播"></label>
          <label>服务品牌<select name="brand" required><option ${project?.brand === "BYD" ? "selected" : ""}>BYD</option><option ${project?.brand === "XPENG" || !project ? "selected" : ""}>XPENG</option></select></label>
          <label>传播车型<input name="vehicle_model" required value="${campaignEscape(project?.vehicle_model)}" placeholder="例如 G6"></label>
          <fieldset class="wide campaign-fieldset"><legend>目标市场</legend><label><input type="checkbox" name="markets" value="DE" ${markets.includes("DE") ? "checked" : ""}> 德国 DE</label><label><input type="checkbox" name="markets" value="GB" ${markets.includes("GB") ? "checked" : ""}> 英国 GB</label></fieldset>
          <label>主市场<select name="primary_market"><option value="DE" ${project?.primary_market === "DE" ? "selected" : ""}>德国 DE</option><option value="GB" ${project?.primary_market === "GB" || !project ? "selected" : ""}>英国 GB</option></select></label>
          <label>总预算<input name="budget_total" type="number" min="1" step="0.01" required value="${campaignEscape(project?.budget_total || 60000)}"></label>
          <label>开始日期<input name="start_date" type="date" required value="${campaignEscape(project?.start_date)}"></label>
          <label>结束日期<input name="end_date" type="date" required value="${campaignEscape(project?.end_date)}"></label>
          <label>项目负责人<input name="owner" required value="${campaignEscape(project?.owner)}"></label>
          <label>协作人<input name="collaborators" value="${campaignEscape((project?.collaborators || []).join("，"))}" placeholder="用逗号分隔"></label>
          <label class="wide">传播目标<input name="objectives" value="${campaignEscape((project?.objectives || []).join("，"))}" placeholder="认知、产品教育、试驾、留资"></label>
        </div>
        <div class="campaign-subsection"><div><h3>关键里程碑</h3><p>格式：节点名称｜日期｜负责人，每行一条。</p></div></div>
        <textarea name="milestones" rows="5" placeholder="立项审批｜2026-10-02｜项目负责人\n内容发布｜2026-11-01｜内容负责人">${campaignEscape(milestones.map(item => `${item.name}｜${item.planned_date}｜${item.owner}`).join("\n"))}</textarea>
        ${campaignFormActions(isNew ? "创建项目草稿" : "保存基本信息")}
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
      showStatus("项目基本信息已保存");
    } else {
      campaignState.current = await campaignRequest("/campaigns", {method: "POST", body: JSON.stringify(payload)});
      showStatus("项目草稿已创建");
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
      <div class="card-hd"><div><h2>M3 目标受众与内容策略</h2><p>结构化保存受众、平台、内容主张、CTA与合规边界。</p></div><span class="campaign-save-state">Revision ${project.revision}</span></div>
      <form id="campaign-strategy-form" class="campaign-form">
        <label>核心受众 <small>每行：名称｜市场代码｜语言｜决策阶段｜core/secondary/reach</small><textarea name="audiences" rows="5" placeholder="英国城市家庭新能源车考虑者｜GB｜英语｜考虑｜core">${campaignEscape(audiences)}</textarea></label>
        <div class="campaign-form-grid">
          <label>目标平台<input name="platforms" required value="${campaignEscape((data.platforms || []).join("，"))}" placeholder="YouTube，Instagram"></label>
          <label>内容形式<input name="content_formats" required value="${campaignEscape((data.content_formats || []).join("，"))}" placeholder="深度试驾，短视频"></label>
          <label class="wide">必须传递的信息<textarea name="message_pillars" rows="3" placeholder="每行一项">${campaignEscape((data.message_pillars || []).join("\n"))}</textarea></label>
          <label class="wide">禁止或待法务确认的表述<textarea name="prohibited_claims" rows="3" required placeholder="每行一项">${campaignEscape((data.prohibited_claims || []).join("\n"))}</textarea></label>
          <label>CTA<input name="cta" required value="${campaignEscape(data.cta)}" placeholder="预约试驾"></label>
          <label>风险合规复核人<input name="risk_reviewer" required value="${campaignEscape(data.risk_reviewer)}"></label>
          <label class="wide">商业合作披露规则<textarea name="disclosure_rule" rows="2" required>${campaignEscape(data.disclosure_rule)}</textarea></label>
          <label>素材授权需求<input name="usage_rights_need" value="${campaignEscape(data.usage_rights_need)}"></label>
          <label>竞品排他需求<input name="competitor_exclusivity" value="${campaignEscape(data.competitor_exclusivity)}"></label>
        </div>
        ${campaignFormActions("保存受众与内容策略")}
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
    showStatus("受众与内容策略已保存");
    showCampaignStep("M4");
  } catch (error) { showStatus(error.message, true); }
}

function metricRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-metric-row";
  row.innerHTML = `
    <input data-field="metric_code" placeholder="指标代码" value="${campaignEscape(item.metric_code)}">
    <input data-field="name" placeholder="中文名称" value="${campaignEscape(item.name)}">
    <input data-field="target_value" type="number" min="0" step="0.01" placeholder="目标值" value="${campaignEscape(item.target_value)}">
    <input data-field="unit" placeholder="单位" value="${campaignEscape(item.unit)}">
    <input data-field="formula" placeholder="定义或公式" value="${campaignEscape(item.formula)}">
    <input data-field="data_source" placeholder="数据来源" value="${campaignEscape(item.data_source)}">
    <input data-field="observation_window" placeholder="观察窗口" value="${campaignEscape(item.observation_window)}">
    <input data-field="owner" placeholder="负责人" value="${campaignEscape(item.owner)}">
    <select data-field="refresh_frequency"><option ${item.refresh_frequency === "每日" ? "selected" : ""}>每日</option><option ${item.refresh_frequency === "每周" ? "selected" : ""}>每周</option><option ${item.refresh_frequency === "项目结束后" ? "selected" : ""}>项目结束后</option></select>
    <label class="campaign-check"><input data-field="is_primary" type="checkbox" ${item.is_primary ? "checked" : ""}> 核心</label>
    <button class="icon-btn" data-remove-row type="button">移除</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function renderCampaignMeasurement() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  const items = project.configuration.measurement_plan?.items || [];
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
      <div class="card-hd"><div><h2>M4 KPI与效果测量方案</h2><p>点击、留资、试驾和成交分别保存，不合并为“总转化”。</p></div><button class="tb-btn" id="campaign-add-metric" type="button">+ 添加KPI</button></div>
      <form id="campaign-measurement-form" class="campaign-form">
        <div class="campaign-repeat-head metric-head"><span>代码</span><span>名称</span><span>目标</span><span>单位</span><span>公式</span><span>来源</span><span>窗口</span><span>负责人</span><span>频率</span><span>核心</span><span></span></div>
        <div id="campaign-metric-rows" class="campaign-repeat-list"></div>
        ${campaignFormActions("保存KPI方案")}
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
    showStatus("KPI测量方案已保存");
    showCampaignStep("M5");
  } catch (error) { showStatus(error.message, true); }
}

function roleRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-role-row";
  row.innerHTML = `
    <input data-field="role_code" placeholder="角色代码" value="${campaignEscape(item.role_code)}">
    <input data-field="role_name" placeholder="角色名称" value="${campaignEscape(item.role_name)}">
    <select data-field="market"><option value="DE" ${item.market === "DE" ? "selected" : ""}>DE</option><option value="GB" ${item.market === "GB" || !item.market ? "selected" : ""}>GB</option></select>
    <input data-field="platform" placeholder="平台" value="${campaignEscape(item.platform || "YouTube")}">
    <input data-field="required_count" type="number" min="1" placeholder="人数" value="${campaignEscape(item.required_count || 1)}">
    <input data-field="content_format" placeholder="内容形式" value="${campaignEscape(item.content_format)}">
    <input data-field="audience_requirement" placeholder="受众要求" value="${campaignEscape(item.audience_requirement)}">
    <input data-field="risk_threshold" placeholder="风险门槛" value="${campaignEscape(item.risk_threshold || "重大主体风险直接阻断")}">
    <input data-field="quote_cap" type="number" min="0" placeholder="报价上限" value="${campaignEscape(item.quote_cap)}">
    <button class="icon-btn" data-remove-row type="button">移除</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function budgetRow(item = {}) {
  const row = document.createElement("div");
  row.className = "campaign-repeat-row campaign-budget-row";
  row.innerHTML = `
    <input data-field="category" placeholder="预算项" value="${campaignEscape(item.category)}">
    <input data-field="amount" type="number" min="0" step="0.01" placeholder="金额" value="${campaignEscape(item.amount)}">
    <label class="campaign-check"><input data-field="estimated" type="checkbox" ${item.estimated !== false ? "checked" : ""}> 估算</label>
    <input data-field="assumption" placeholder="估算假设或说明" value="${campaignEscape(item.assumption)}">
    <button class="icon-btn" data-remove-row type="button">移除</button>`;
  row.querySelector("[data-remove-row]").addEventListener("click", () => row.remove());
  return row;
}

function renderCampaignRequirements() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  const data = project.configuration.kol_requirements || {};
  panel.innerHTML = `
    <article class="content-card campaign-form-card">
      <div class="card-hd"><div><h2>M5 KOL角色组合与预算配置</h2><p>将策略转换为筛选条件，并检查分项预算是否超过 ${new Intl.NumberFormat("zh-CN").format(project.budget_total)} ${campaignEscape(project.currency)}。</p></div></div>
      <form id="campaign-requirements-form" class="campaign-form">
        <div class="campaign-subsection"><div><h3>KOL角色需求</h3><p>市场和平台必须与M2、M3配置一致。</p></div><button class="tb-btn" id="campaign-add-role" type="button">+ 添加角色</button></div>
        <div class="campaign-repeat-head role-head"><span>代码</span><span>角色</span><span>市场</span><span>平台</span><span>人数</span><span>形式</span><span>受众要求</span><span>风险门槛</span><span>报价上限</span><span></span></div>
        <div id="campaign-role-rows" class="campaign-repeat-list"></div>
        <div class="campaign-subsection"><div><h3>分项预算</h3><p>未获得报价时保留估算标记和假设。</p></div><button class="tb-btn" id="campaign-add-budget" type="button">+ 添加预算项</button></div>
        <div class="campaign-repeat-head budget-head"><span>预算项</span><span>金额</span><span>状态</span><span>假设</span><span></span></div>
        <div id="campaign-budget-rows" class="campaign-repeat-list"></div>
        <div id="campaign-budget-summary" class="campaign-budget-summary"></div>
        ${campaignFormActions("保存KOL需求与预算")}
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
  node.textContent = `分项合计 ${new Intl.NumberFormat("zh-CN").format(total)} / 总预算 ${new Intl.NumberFormat("zh-CN").format(budget)} ${campaignState.current?.currency || ""}${total > budget ? `，超出 ${new Intl.NumberFormat("zh-CN").format(total - budget)}` : ""}`;
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
    showStatus("KOL需求与预算已保存");
    showCampaignStep("M6");
  } catch (error) { showStatus(error.message, true); }
}

async function renderCampaignApproval() {
  const panel = document.getElementById("campaign-panel");
  const project = campaignState.current;
  updateCampaignContext();
  panel.innerHTML = '<div class="empty-state">正在执行审批前校验…</div>';
  let validation;
  try { validation = await campaignRequest(`/campaigns/${project.campaign_id}/validate`, {method: "POST"}); }
  catch (error) { panel.innerHTML = `<div class="empty-state">${campaignEscape(error.message)}</div>`; return; }
  const issues = [...validation.errors, ...validation.warnings];
  const approvals = project.approvals || [];
  const handoffs = project.handoffs || [];
  panel.innerHTML = `
    <div class="campaign-approval-grid">
      <article class="content-card campaign-check-card">
        <div class="card-hd"><div><h2>M6 审批前检查</h2><p>完整度 ${validation.completion}% · V${validation.version_number}</p></div><span class="campaign-validation ${validation.valid ? "pass" : "fail"}">${validation.valid ? "校验通过" : `${validation.errors.length}项阻断`}</span></div>
        <div class="campaign-issue-list">${issues.length ? issues.map(issue => `<button type="button" data-issue-page="${campaignEscape(issue.page)}" class="campaign-issue ${issue.severity}"><b>${campaignEscape(issue.page)}</b><span>${campaignEscape(issue.message)}</span></button>`).join("") : '<div class="campaign-success">所有审批前检查均已通过。</div>'}</div>
      </article>
      <article class="content-card campaign-decision-card">
        <div class="card-hd"><h2>人工审批与发布</h2><span class="campaign-status status-${campaignEscape(project.status)}">${CAMPAIGN_STATUS[project.status] || project.status}</span></div>
        <div class="campaign-decision-body">
          <p>批准动作由品牌负责人执行；本项目包含合规边界时，需要勾选风险合规会签。</p>
          <label class="campaign-check"><input id="campaign-risk-signoff" type="checkbox"> 已完成风险合规会签</label>
          <div class="campaign-decision-actions">
            ${project.status === "draft" ? '<button id="campaign-submit" class="tb-btn teal" type="button">提交审批</button>' : ""}
            ${project.status === "pending_approval" ? '<button id="campaign-return" class="tb-btn" type="button">退回修改</button><button id="campaign-reject" class="tb-btn" type="button">不批准</button><button id="campaign-approve" class="tb-btn teal" type="button">批准并冻结版本</button>' : ""}
            ${project.status === "approved" ? '<button id="campaign-publish" class="tb-btn teal" type="button">发布下游交接包</button>' : ""}
          </div>
        </div>
      </article>
    </div>
    <div class="campaign-audit-grid">
      <article class="content-card"><div class="card-hd"><h2>版本与审批记录</h2></div><div class="table-wrap"><table><thead><tr><th>版本</th><th>状态</th><th>创建人</th><th>提交/批准</th></tr></thead><tbody>${(project.versions || []).map(item => `<tr><td>V${item.version_number}</td><td>${campaignEscape(item.status)}</td><td>${campaignEscape(item.created_by)}</td><td>${campaignEscape(item.approved_at || item.submitted_at || "—")}</td></tr>`).join("")}</tbody></table></div><div class="campaign-audit-list">${approvals.map(item => `<p><b>${campaignEscape(item.action)}</b><span>V${item.version_number} · ${campaignEscape(item.actor)} · ${campaignEscape(item.reason || "无补充说明")}</span></p>`).join("") || '<div class="empty-state">暂无审批记录</div>'}</div></article>
      <article class="content-card"><div class="card-hd"><h2>下游交接记录</h2><span>${handoffs.length}个模块</span></div><div class="campaign-handoff-list">${handoffs.map(item => `<div><b>${campaignEscape(item.target_label)}</b><span>V${item.version_number} · ${campaignEscape(item.status)} · 第${item.attempts}次</span></div>`).join("") || '<div class="empty-state">批准后可发布交接包</div>'}</div></article>
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
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/submit`, {method: "POST", body: JSON.stringify({expected_revision: campaignState.current.revision, actor: "项目负责人", actor_role: "project_owner"})});
    showStatus("项目已提交审批，当前版本已锁定");
    renderCampaignApproval();
  } catch (error) {
    showStatus(error.message, true);
    if (error.issues?.[0]?.page) showCampaignStep(error.issues[0].page);
  }
}

async function decideCurrentCampaign(decision) {
  const reason = decision === "approve" ? null : window.prompt(decision === "return" ? "请输入退回原因" : "请输入不批准原因");
  if (decision !== "approve" && !reason) return;
  const riskSignoff = Boolean(document.getElementById("campaign-risk-signoff")?.checked);
  try {
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/decision`, {method: "POST", body: JSON.stringify({expected_revision: campaignState.current.revision, decision, reason, risk_signoff: riskSignoff, actor: "品牌负责人", actor_role: "brand_owner"})});
    showStatus(decision === "approve" ? "项目已批准并冻结版本" : "审批决定已记录");
    renderCampaignApproval();
  } catch (error) { showStatus(error.message, true); }
}

async function publishCurrentCampaign() {
  try {
    await campaignRequest(`/campaigns/${campaignState.current.campaign_id}/publish`, {method: "POST", body: JSON.stringify({actor: "项目负责人", actor_role: "project_owner"})});
    campaignState.current = await campaignRequest(`/campaigns/${campaignState.current.campaign_id}`);
    showStatus("已向筛选、合同、监控、复盘和资产模块发布交接包");
    renderCampaignApproval();
  } catch (error) { showStatus(error.message, true); }
}
