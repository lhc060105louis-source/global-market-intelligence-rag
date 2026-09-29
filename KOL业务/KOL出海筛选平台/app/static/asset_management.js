"use strict";

const assetState = {view: "overview", kol: "@AutoBildDE", initialized: false};

function assetEscape(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function assetNumber(value) {
  return new Intl.NumberFormat("zh-CN", {notation: "compact", maximumFractionDigits: 2}).format(Number(value || 0));
}

function assetStatusClass(status) {
  if (["优选", "优先", "批准复投"].includes(status)) return "good";
  if (["条件", "有条件继续合作", "有条件批准"].includes(status)) return "conditional";
  if (["暂停", "禁止", "暂停评估", "不批准"].includes(status)) return "blocked";
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
    <article class="content-card monitor-context"><div><strong>KOL 合作资产池</strong><small>历史合作结果、名单、风险与数据完整度统一查看</small></div><span>更新 ${assetEscape(String(data.updated_at).slice(0, 10))}</span></article>
    <div class="monitor-metrics">
      ${monitorMetric("资产 KOL", m.total, "当前资产池")}
      ${monitorMetric("优选", m.preferred, "长期合作资格")}
      ${monitorMetric("条件", m.conditional, "需满足合作条件")}
      ${monitorMetric("观察", m.watch, "继续积累证据")}
      ${monitorMetric("暂停 / 禁止", m.blocked, "当前不可直接推进", m.blocked > 0)}
      ${monitorMetric("重大风险", m.major_risk, "需人工核验", m.major_risk > 0)}
    </div>
    <form id="asset-filter-form" class="filter-bar asset-filter">
      <select name="country"><option value="">全部市场</option><option value="GB">英国</option><option value="DE">德国</option><option value="FR">法国</option></select>
      <select name="platform"><option value="">全部平台</option><option>YouTube</option><option>Instagram</option><option>TikTok</option></select>
      <select name="status"><option value="">全部状态</option><option>优选</option><option>条件</option><option>观察</option><option>暂停</option><option>禁止</option></select>
      <button class="tb-btn" type="submit">筛选</button><button id="asset-filter-reset" class="tb-btn" type="button">重置</button>
    </form>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>资产清单</h3><span>${data.assets.length} 条</span></div>
        <div class="table-wrap"><table class="monitor-table"><thead><tr><th>KOL</th><th>市场 / 平台</th><th>合作次数</th><th>最近项目</th><th>近期结果</th><th>名单状态</th><th>风险</th><th>完整度</th></tr></thead><tbody>
        ${data.assets.map(item => `<tr class="asset-row" data-asset-kol="${assetEscape(item.handle)}"><td><strong>${assetEscape(item.name)}</strong><small>${assetEscape(item.handle)}</small></td><td>${assetEscape(item.market)} · ${assetEscape(item.platform)}</td><td>${item.collaborations}</td><td>${assetEscape(item.recent_project)}</td><td>${item.recent_score}/100</td><td><span class="asset-status ${assetStatusClass(item.list_status)}">${assetEscape(item.list_status)}</span></td><td>${assetEscape(item.risk)}</td><td>${item.data_completeness}%</td></tr>`).join("")}
        </tbody></table></div>
      </article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>注意事项</h3></div><div class="monitor-list">${(data.attention || []).map(item => `<div class="monitor-list-row"><span><strong>${assetEscape(item.type)}</strong><small>${assetEscape(item.text)}</small></span></div>`).join("") || `<div class="empty-state">暂无待处理事项</div>`}</div></article>
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

async function loadAssetArchive(kolKey = "@AutoBildDE") {
  const data = await api(`/reinvestment/archives/${encodeURIComponent(kolKey)}`);
  assetState.kol = data.identity.handle;
  const m = data.metrics;
  const root = document.getElementById("asset-archive");
  root.innerHTML = `
    <article class="content-card monitor-review-head"><div><small>${assetEscape(data.identity.market)} · ${assetEscape(data.identity.platform)} · ${assetEscape(data.identity.handle)}</small><h3>${assetEscape(data.identity.name)}</h3></div><div class="monitor-head-badges"><span class="asset-status ${assetStatusClass(data.identity.list_status)}">${assetEscape(data.identity.list_status)}</span><span>数据完整度 ${data.data_completeness}%</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("合作次数", m.collaborations, "跨项目")}${monitorMetric("覆盖市场", m.markets, "历史市场")}${monitorMetric("内容资产", m.content_assets, "可追溯记录")}${monitorMetric("平均互动率", `${m.avg_engagement}%`, "历史参考")}${monitorMetric("转化", assetNumber(m.conversions), "最近项目")}${monitorMetric("内容质量", `${m.content_quality}/100`, "复盘记录")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>项目历史</h3><span>${assetEscape(data.trend_note)}</span></div><table class="monitor-table"><thead><tr><th>项目</th><th>时间</th><th>平台</th><th>结果</th><th>复盘分</th></tr></thead><tbody>${data.project_history.map(row => `<tr><td><strong>${assetEscape(row.project)}</strong><small>${assetEscape(row.note)}</small></td><td>${assetEscape(row.date)}</td><td>${assetEscape(row.platform)}</td><td>${assetEscape(row.result)}</td><td>${row.score ?? "—"}</td></tr>`).join("")}</tbody></table></article>
      <div class="monitor-stack">
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>可复用资产</h3></div><ul>${data.reusable_assets.map(item => `<li>${assetEscape(item)}</li>`).join("")}</ul></article>
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>风险与限制</h3></div><ul>${data.risks.map(item => `<li>${assetEscape(item)}</li>`).join("")}</ul></article>
        <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>审计记录</h3></div><div class="monitor-timeline">${data.audit.map(item => `<div><time>记录</time><b>•</b><span>${assetEscape(item)}</span></div>`).join("")}</div></article>
      </div>
    </div>
    <div class="monitor-actions"><button id="asset-to-evaluation" class="tb-btn teal" type="button">进入本项目复投评估 →</button></div>`;
  document.getElementById("asset-to-evaluation").addEventListener("click", () => switchAssetView("evaluation", {kol: data.identity.handle}).catch(error => showStatus(error.message, true)));
}

async function loadAssetEvaluation(kolKey = "@AutoBildDE") {
  const data = await api(`/reinvestment/evaluations/${encodeURIComponent(kolKey)}`);
  assetState.kol = data.kol.handle;
  const root = document.getElementById("asset-evaluation");
  root.innerHTML = `
    <article class="content-card monitor-context"><div><strong>${assetEscape(data.project.name)}</strong><small>${assetEscape(data.project.brand)} ${assetEscape(data.project.model)} · ${assetEscape(data.project.market)} · ${assetEscape(data.project.objective)}</small></div><span>${assetEscape(data.kol.handle)}</span></article>
    <div class="monitor-metrics">
      ${monitorMetric("建议分", `${data.suggestion_score}/100`, "项目级辅助指标")}${monitorMetric("建议状态", data.suggestion_status, "当前项目")}${monitorMetric("数据完整度", `${data.data_completeness}%`, "缺失不等于 0")}${monitorMetric("重大风险", data.major_risk ? "存在阻断" : "无阻断", "独立于总分", data.major_risk)}
    </div>
    <div class="asset-score-grid">${data.dimensions.map(item => `<article class="content-card monitor-pad"><div class="monitor-card-title"><h3>${assetEscape(item.name)}</h3><strong>${item.score}</strong></div><div class="asset-score-bar"><i style="width:${item.score}%"></i></div><p>${assetEscape(item.evidence)}</p><small>${assetEscape(item.limitation)}</small></article>`).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>合作条件</h3></div><div class="monitor-owner-list"><div><span>报价上限</span><strong>${assetNumber(data.conditions.quote_cap)} ${assetEscape(data.conditions.currency)}</strong></div><div><span>内容形式</span><strong>${assetEscape(data.conditions.content_format)}</strong></div><div><span>档期</span><strong>${assetEscape(data.conditions.schedule)}</strong></div><div><span>广告披露</span><strong>${assetEscape(data.conditions.disclosure)}</strong></div><div><span>竞品排他</span><strong>${assetEscape(data.conditions.exclusivity)}</strong></div><div><span>补充数据</span><strong>${assetEscape(data.conditions.data_required)}</strong></div></div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>人工审批</h3><span>${assetEscape(data.approval.decision)}</span></div><form id="asset-approval-form"><label>审批决定<select name="decision"><option>批准复投</option><option>有条件批准</option><option>退回补充</option><option>不批准</option></select></label><label>备注<textarea name="note" rows="4">${assetEscape(data.approval.note || "")}</textarea></label><div class="monitor-actions"><button class="tb-btn teal" type="submit">保存审批</button></div></form><div class="asset-callout">${assetEscape(data.note)}</div></article>
    </div>
    <div class="monitor-actions"><button id="asset-to-portfolio" class="tb-btn teal" type="button">进入组合与预算 →</button></div>`;
  const form = document.getElementById("asset-approval-form");
  if (data.approval.decision !== "待审批") form.decision.value = data.approval.decision;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    await api(`/reinvestment/evaluations/${encodeURIComponent(assetState.kol)}/approval`, {method: "POST", body: JSON.stringify(payload)});
    showStatus("复投审批已保存");
    await loadAssetEvaluation(assetState.kol);
  });
  document.getElementById("asset-to-portfolio").addEventListener("click", () => switchAssetView("portfolio").catch(error => showStatus(error.message, true)));
}

async function loadAssetPortfolio() {
  const data = await api("/reinvestment/portfolio");
  const root = document.getElementById("asset-portfolio");
  root.innerHTML = `
    <article class="content-card monitor-context"><div><strong>${assetEscape(data.project.name)}</strong><small>总预算 ${assetNumber(data.project.budget)} ${assetEscape(data.project.currency)} · ${assetEscape(data.project.period)}</small></div><span>预测仅作方案比较</span></article>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>候选池</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>市场 / 平台</th><th>适配建议</th><th>建议分</th><th>报价上限</th><th>档期</th><th>风险</th></tr></thead><tbody>${data.candidates.map(item => `<tr><td>${assetEscape(item.handle)}</td><td>${assetEscape(item.market)} · ${assetEscape(item.platform)}</td><td><span class="asset-status ${assetStatusClass(item.recommendation)}">${assetEscape(item.recommendation)}</span></td><td>${item.score}</td><td>${assetNumber(item.quote_cap)} ${assetEscape(item.currency)}</td><td>${assetEscape(item.availability)}</td><td>${assetEscape(item.risk)}</td></tr>`).join("")}</tbody></table></article>
    <div class="asset-budget-grid">${data.scenarios.map(row => `<article class="content-card monitor-pad asset-scenario ${row.selected ? "selected" : ""}"><div class="monitor-card-title"><h3>方案 ${row.id} · ${assetEscape(row.name)}</h3><strong>${row.budget_usage}%</strong></div><p><strong>${row.kols.map(assetEscape).join(" + ")}</strong></p><div class="asset-range"><span>预算</span><b>${assetNumber(row.cost)} ${assetEscape(data.project.currency)}</b></div><div class="asset-range"><span>触达参考</span><b>${assetEscape(row.reach_range)}</b></div><div class="asset-range"><span>互动参考</span><b>${assetEscape(row.engagement_range)}</b></div><div class="asset-range"><span>可信度</span><b>${assetEscape(row.confidence)}</b></div><small>${assetEscape(row.note)}；${assetEscape(row.assumption)}</small><div class="monitor-actions"><button class="tb-btn ${row.selected ? "" : "teal"}" data-select-scenario="${row.id}" type="button">${row.selected ? "当前方案" : "选择方案"}</button></div></article>`).join("")}</div>
    <div class="monitor-grid monitor-grid-main"><article class="content-card monitor-pad"><div class="monitor-card-title"><h3>组合检查</h3></div><div class="monitor-list">${data.checks.map(item => `<div class="monitor-list-row"><span><strong>${assetEscape(item.name)}</strong><small>${assetEscape(item.detail)}</small></span><em>${assetEscape(item.status)}</em></div>`).join("")}</div></article><article class="content-card monitor-pad"><div class="asset-callout">${assetEscape(data.prediction_note)}</div><div class="monitor-actions"><button id="asset-to-governance" class="tb-btn teal" type="button">进入名单治理 →</button></div></article></div>`;
  root.querySelectorAll("[data-select-scenario]").forEach(button => button.addEventListener("click", async () => {
    await api("/reinvestment/portfolio/select", {method: "POST", body: JSON.stringify({scenario_id: button.dataset.selectScenario})});
    showStatus(`已选择方案 ${button.dataset.selectScenario}`);
    await loadAssetPortfolio();
  }));
  document.getElementById("asset-to-governance").addEventListener("click", () => switchAssetView("governance").catch(error => showStatus(error.message, true)));
}

async function loadAssetGovernance() {
  const data = await api("/reinvestment/governance");
  const root = document.getElementById("asset-governance");
  root.innerHTML = `
    ${data.risk_banner.visible ? `<article class="content-card asset-risk-banner"><strong>${assetEscape(data.risk_banner.title)}</strong><span>${assetEscape(data.risk_banner.kol)} · ${assetEscape(data.risk_banner.fact)}</span></article>` : ""}
    <div class="monitor-metrics">${["优选","条件","观察","暂停","禁止"].map(name => monitorMetric(name, data.metrics[name] || 0, "名单状态", ["暂停","禁止"].includes(name))).join("")}${monitorMetric("待复核", data.metrics.pending_approval, "需审批 / 复核")}</div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>合作资格名单</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>状态</th><th>适用范围</th><th>原因</th><th>影响项目</th><th>负责人</th><th>复核</th></tr></thead><tbody>${data.rows.map(row => `<tr><td><strong>${assetEscape(row.handle)}</strong></td><td><span class="asset-status ${assetStatusClass(row.status)}">${assetEscape(row.status)}</span></td><td>${assetEscape(row.scope)}</td><td>${assetEscape(row.reason)}</td><td>${row.affected_projects}</td><td>${assetEscape(row.owner)}</td><td>${assetEscape(row.review_at)}</td></tr>`).join("")}</tbody></table></article>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>调整合作资格</h3><span>必须保留原因</span></div><form id="asset-governance-form" class="asset-form-grid"><label>KOL<select name="kol">${data.rows.map(row => `<option value="${assetEscape(row.handle)}">${assetEscape(row.handle)}</option>`).join("")}</select></label><label>状态<select name="status"><option>优选</option><option>条件</option><option>观察</option><option>暂停</option><option>禁止</option></select></label><label>适用范围<input name="scope" value="欧洲汽车合作项目"></label><label>复核时间<input name="review_at" placeholder="如 2026-09-15 / 按项目复核"></label><label class="wide">原因<input name="reason" required placeholder="说明事实依据、限制或审批原因"></label><div class="monitor-actions wide"><button class="tb-btn teal" type="submit">保存状态</button></div></form><div class="asset-callout">${assetEscape(data.rule)}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>最近审计记录</h3></div><div class="monitor-timeline">${data.timeline.map(row => `<div><time>${assetEscape(String(row.time).slice(5, 16).replace("T", " "))}</time><b>•</b><span>${assetEscape(row.kol)} · ${assetEscape(row.event)}：${assetEscape(row.reason)}</span></div>`).join("") || `<div class="empty-state">暂无人工状态变更</div>`}</div></article>
    </div>
    <div class="monitor-actions"><button id="asset-to-actions" class="tb-btn teal" type="button">进入行动追踪 →</button></div>`;
  document.getElementById("asset-governance-form").addEventListener("submit", async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    const kol = payload.kol; delete payload.kol;
    await api(`/reinvestment/governance/${encodeURIComponent(kol)}`, {method: "POST", body: JSON.stringify(payload)});
    showStatus("名单状态已保存");
    await loadAssetGovernance();
  });
  document.getElementById("asset-to-actions").addEventListener("click", () => switchAssetView("actions").catch(error => showStatus(error.message, true)));
}

async function loadAssetActions() {
  const data = await api("/reinvestment/actions");
  const root = document.getElementById("asset-actions");
  root.innerHTML = `
    <article class="content-card monitor-review-head"><div><small>${assetEscape(data.source_plan)}</small><h3>${assetEscape(data.project.name)}</h3></div><div class="monitor-head-badges"><span>预算 ${assetNumber(data.expected_budget)} ${assetEscape(data.currency)}</span><span>${assetEscape(data.milestone)}</span><span>下一截止 ${assetEscape(data.next_deadline)}</span></div></article>
    <div class="asset-pipeline">${Object.entries(data.pipeline).map(([name, count]) => `<div><span>${assetEscape(name)}</span><strong>${count}</strong></div>`).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>候选推进</h3></div><table class="monitor-table"><thead><tr><th>KOL</th><th>阶段</th><th>报价</th><th>档期</th><th>合作条件</th><th>阻塞</th></tr></thead><tbody>${data.candidates.map(row => `<tr><td>${assetEscape(row.handle)}</td><td><span class="monitor-pill">${assetEscape(row.stage)}</span></td><td>${assetEscape(row.quote)}</td><td>${assetEscape(row.schedule)}</td><td>${assetEscape(row.conditions)}</td><td>${assetEscape(row.blocker)}</td></tr>`).join("")}</tbody></table></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>交接与写回</h3></div><div class="asset-callout">${assetEscape(data.writeback_note)}</div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>任务中心</h3><span>负责人 ${assetEscape(data.owner)}</span></div><table class="monitor-table"><thead><tr><th>任务</th><th>KOL</th><th>负责人</th><th>截止</th><th>依赖</th><th>状态</th></tr></thead><tbody>${data.tasks.map(row => `<tr><td><strong>${assetEscape(row.task)}</strong><small>${assetEscape(row.task_code)}</small></td><td>${assetEscape(row.kol)}</td><td>${assetEscape(row.owner)}</td><td>${assetEscape(row.due_at)}</td><td>${assetEscape(row.dependency)}</td><td><select class="asset-task-status" data-task-code="${assetEscape(row.task_code)}"><option ${row.status === "待办" ? "selected" : ""}>待办</option><option ${row.status === "进行中" ? "selected" : ""}>进行中</option><option ${row.status === "已完成" ? "selected" : ""}>已完成</option><option ${row.status === "阻塞" ? "selected" : ""}>阻塞</option></select></td></tr>`).join("")}</tbody></table></article>`;
  root.querySelectorAll("[data-task-code]").forEach(select => select.addEventListener("change", async () => {
    await api(`/reinvestment/actions/${encodeURIComponent(select.dataset.taskCode)}`, {method: "POST", body: JSON.stringify({status: select.value})});
    showStatus(`${select.dataset.taskCode} 已更新为${select.value}`);
  }));
}
