"use strict";

const postState = {view: "overview", kol: "@AutoBildDE", crisis: null, initialized: false};

function postEscape(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function postNumber(value) {
  return new Intl.NumberFormat("zh-CN", {notation: "compact", maximumFractionDigits: 2}).format(Number(value || 0));
}

function initPostCampaignModule() {
  if (postState.initialized) return;
  postState.initialized = true;
  document.querySelectorAll("[data-post-view]").forEach(button => {
    button.addEventListener("click", () => switchPostView(button.dataset.postView));
  });
  const root = document.getElementById("post-overview");
  if (root) root.addEventListener("click", event => {
    const button = event.target.closest("[data-post-kol]");
    if (button) switchPostView("kol", {kol: button.dataset.postKol});
  });
  const crisisRoot = document.getElementById("monitoring-crisis");
  if (crisisRoot) crisisRoot.addEventListener("click", event => {
    const action = event.target.closest("[data-crisis-action]");
    if (action) runCrisisAction(action.dataset.crisisAction);
  });
}

function setPostTab(view) {
  postState.view = view;
  document.querySelectorAll("[data-post-view]").forEach(button => button.classList.toggle("active", button.dataset.postView === view));
  document.querySelectorAll(".post-panel").forEach(panel => panel.classList.toggle("active", panel.id === `post-${view}`));
}

async function switchPostView(view, options = {}) {
  initPostCampaignModule();
  if (options.kol) postState.kol = options.kol;
  setPostTab(view);
  if (view === "overview") await loadPostOverview();
  if (view === "kol") await loadPostKol(postState.kol);
  if (view === "sentiment") await loadPostSentiment();
  if (view === "review") await loadPostReview();
}

async function loadPostOverview() {
  initPostCampaignModule();
  setPostTab("overview");
  const data = await api("/post-campaign/overview");
  const m = data.metrics;
  document.getElementById("post-overview").innerHTML = `
    <article class="content-card monitor-context"><div><strong>${postEscape(data.campaign)}</strong><small>${postEscape(data.brand)} · ${postEscape(data.market)}</small></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("总曝光 / 播放", postNumber(m.impressions), "累计")} 
      ${monitorMetric("总互动", postNumber(m.engagements), "累计")} 
      ${monitorMetric("总转化", postNumber(m.conversions), "追踪数据")} 
      ${monitorMetric("平均互动率", `${m.engagement_rate}%`, "当前项目")} 
      ${monitorMetric("目标完成率", `${m.target_completion}%`, "项目目标")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>目标完成</h3></div>
        <div class="monitor-performance">${Object.entries(data.targets || {}).map(([name, item]) => `<div><span>${postEscape(name)}</span><strong>${postNumber(item.actual)} / ${postNumber(item.target)}</strong></div>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>平台效果</h3></div>
        <div class="monitor-list">${data.platforms.map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>曝光 ${postNumber(item.impressions)}</small></span><em>${item.engagement_rate}%</em></div>`).join("")}</div>
      </article>
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>KOL 效果排名</h3></div>
        <div class="monitor-list">${data.ranking.map((item, index) => `<button class="monitor-list-row" data-post-kol="${postEscape(item.kol)}" type="button"><b>#${index + 1}</b><span><strong>${postEscape(item.kol)}</strong><small>${postEscape(item.platform)} · ${postNumber(item.impressions)} 曝光</small></span><em>${item.completion}%</em></button>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>内容亮点</h3></div>
        <div class="monitor-list">${data.highlights.map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.type)} · ${postEscape(item.title)}</strong><small>${postEscape(item.note)}</small></span></div>`).join("")}</div>
      </article>
    </div>`;
}

async function loadPostKol(kolKey = "@AutoBildDE") {
  initPostCampaignModule();
  const data = await api(`/post-campaign/kols/${encodeURIComponent(kolKey)}`);
  postState.kol = data.handle;
  const contents = data.contents || [];
  document.getElementById("post-kol").innerHTML = `
    <article class="content-card monitor-review-head"><div><small>${postEscape(data.platform)} · ${postEscape(data.handle)}</small><h3>${postEscape(data.name)}</h3></div><div class="monitor-head-badges"><span>目标完成 ${data.target_completion ?? "—"}%</span><span>内容质量 ${data.content_quality ?? "—"}/100</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("曝光 / 播放", postNumber(data.impressions), "项目贡献")}
      ${monitorMetric("总互动", postNumber(data.engagements), "累计互动")}
      ${monitorMetric("转化", postNumber(data.conversions), "追踪结果")}
      ${monitorMetric("贡献占比", `${data.contribution ?? "—"}%`, "项目曝光")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>内容表现</h3></div>
        <table class="monitor-table"><thead><tr><th>内容</th><th>平台</th><th>曝光</th><th>互动率</th><th>转化</th><th>结果</th></tr></thead><tbody>${contents.map(item => `<tr><td>${postEscape(item.title)}</td><td>${postEscape(item.platform)}</td><td>${postNumber(item.impressions)}</td><td>${item.engagement_rate ?? 0}%</td><td>${postNumber(item.conversions)}</td><td>${postEscape(item.result)}</td></tr>`).join("")}</tbody></table>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>执行情况</h3></div>
        <div class="monitor-owner-list">${Object.entries(data.execution || {}).map(([name, value]) => `<div><span>${postEscape(name)}</span><strong>${postEscape(value)}</strong></div>`).join("")}</div>
      </article>
    </div>
    <div class="monitor-actions"><button class="tb-btn teal" data-post-view="sentiment" type="button">查看内容与舆情</button></div>`;
  document.getElementById("post-kol").querySelector("[data-post-view]").addEventListener("click", () => switchPostView("sentiment"));
}

async function loadPostSentiment() {
  initPostCampaignModule();
  const data = await api("/post-campaign/sentiment");
  document.getElementById("post-sentiment").innerHTML = `
    <article class="content-card monitor-context"><div><strong>${postEscape(data.content)}</strong><small>${postEscape(data.kol)} · 样本 ${postNumber(data.sample_size)} 条互动</small></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("正向", `${data.positive}%`, "受众情绪")}
      ${monitorMetric("中性", `${data.neutral}%`, "受众情绪")}
      ${monitorMetric("负向", `${data.negative}%`, "受众情绪", true)}
      ${monitorMetric("品牌了解意愿", `${data.brand_attitude?.before}% → ${data.brand_attitude?.after}%`, "发布前后")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>热门话题</h3></div><div class="monitor-list">${(data.topics || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>${postEscape(item.sentiment)}</small></span><em>${item.share}%</em></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>车型反馈</h3></div><div class="monitor-list">${(data.vehicle_feedback || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>${postEscape(item.note)}</small></span><em>${item.score}</em></div>`).join("")}</div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>相关风险</h3></div><div class="monitor-list">${(data.risk_items || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong></span><em>${postEscape(item.status)}</em></div>`).join("")}</div></article>
    <div class="monitor-actions"><button class="tb-btn teal" data-post-view="review" type="button">进入合作复盘</button></div>`;
  document.getElementById("post-sentiment").querySelector("[data-post-view]").addEventListener("click", () => switchPostView("review"));
}

async function loadPostReview() {
  initPostCampaignModule();
  const data = await api("/post-campaign/review");
  const choices = ["推荐继续合作", "有条件继续合作", "调整合作方式", "暂不继续合作"];
  document.getElementById("post-review").innerHTML = `
    <div class="monitor-metrics">${Object.entries(data.scores || {}).map(([name, score]) => monitorMetric(name, score, "复盘评分")).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>复盘结论</h3><strong>${data.overall_score}/100</strong></div><p>${postEscape(data.summary)}</p><h4>主要优势</h4><ul>${(data.strengths || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul><h4>主要问题</h4><ul>${(data.issues || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>后续合作决策</h3><span>${postEscape(data.status)}</span></div><div class="monitor-remediation">${choices.map(item => `<label><input type="radio" name="post-decision" value="${postEscape(item)}" ${data.decision === item ? "checked" : ""}> ${postEscape(item)}</label>`).join("")}</div><label>备注<textarea id="post-review-notes" rows="4">${postEscape(data.notes || "")}</textarea></label><div class="monitor-actions"><button id="post-save-decision" class="tb-btn teal" type="button">保存决定</button></div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>下次合作建议</h3></div><ul>${(data.recommendations || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul></article>`;
  document.getElementById("post-save-decision").addEventListener("click", async () => {
    const selected = document.querySelector('input[name="post-decision"]:checked');
    if (!selected) return showStatus("请选择合作决策", true);
    await api("/post-campaign/review/decision", {method: "POST", body: JSON.stringify({decision: selected.value, notes: document.getElementById("post-review-notes").value})});
    showStatus("已保存");
    await loadPostReview();
  });
}

async function loadCrisisWorkspace(crisisCode = null) {
  initPostCampaignModule();
  const root = document.getElementById("monitoring-crisis");
  if (!root) return;
  if (!crisisCode) {
    const list = await api("/post-campaign/crises");
    crisisCode = list.items[0]?.crisis_code;
  }
  if (!crisisCode) {
    root.innerHTML = `<div class="empty-state">当前没有主体级重大风险事件</div>`;
    return;
  }
  const data = await api(`/post-campaign/crises/${encodeURIComponent(crisisCode)}`);
  postState.crisis = data.crisis_code;
  const impact = data.impact || {};
  root.innerHTML = `
    <article class="content-card monitor-review-head risk-head"><div><small>${postEscape(data.crisis_code)} · ${postEscape(data.kol)}</small><h3>${postEscape(data.title)}</h3></div><div class="monitor-head-badges"><span class="risk-label high">${postEscape(data.level)}</span><span>${postEscape(data.status)}</span><span>${data.verified ? "事实已核验" : "事实核验中"}</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("受影响项目", impact.projects ?? 0, "合作项目")}
      ${monitorMetric("已阻断内容", impact.blocked_contents ?? 0, "待发布")}
      ${monitorMetric("已发布内容", impact.published_contents ?? 0, "品牌内容")}
      ${monitorMetric("未完成任务", impact.open_tasks ?? 0, "应急处理", true)}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>事实核查与证据</h3></div><div class="monitor-list">${(data.evidence || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.source)}</strong><small>${postEscape(item.note)}</small></span><em>${postEscape(item.status)}</em></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>应急任务</h3></div><div class="monitor-remediation">${(data.actions || []).map(item => `<div class="${item.done ? "done" : ""}"><b>${item.done ? "✓" : "○"}</b><span>${postEscape(item.label)}</span>${item.done ? "" : `<button class="text-btn" data-crisis-action="${postEscape(item.key)}" type="button">完成</button>`}</div>`).join("")}</div></article>
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>处理记录</h3></div><div class="monitor-timeline">${(data.timeline || []).map(item => `<div><time>${postEscape(item.time)}</time><b>•</b><span>${postEscape(item.event)}</span></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>合作处置决定</h3><span>${postEscape(data.decision || "未确认")}</span></div><div class="monitor-remediation">${["继续观察", "限制露出", "暂停全部合作", "终止并切割"].map(item => `<label><input type="radio" name="crisis-decision" value="${postEscape(item)}" ${data.decision === item ? "checked" : ""}> ${postEscape(item)}</label>`).join("")}</div><div class="monitor-actions"><button id="crisis-save-decision" class="tb-btn teal" type="button">确认决定</button><button id="crisis-close" class="tb-btn" type="button">关闭事件</button></div></article>
    </div>`;
  document.getElementById("crisis-save-decision").addEventListener("click", saveCrisisDecision);
  document.getElementById("crisis-close").addEventListener("click", closeCurrentCrisis);
}

async function runCrisisAction(action) {
  if (!postState.crisis) return;
  await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/actions/${encodeURIComponent(action)}`, {method: "POST"});
  showStatus("任务已更新");
  await loadCrisisWorkspace(postState.crisis);
}

async function saveCrisisDecision() {
  const selected = document.querySelector('input[name="crisis-decision"]:checked');
  if (!selected) return showStatus("请选择处置决定", true);
  await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/decision`, {method: "POST", body: JSON.stringify({decision: selected.value})});
  showStatus("已保存");
  await loadCrisisWorkspace(postState.crisis);
}

async function closeCurrentCrisis() {
  try {
    await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/close`, {method: "POST"});
    showStatus("事件已关闭");
    await loadCrisisWorkspace();
  } catch (error) {
    showStatus(error.message, true);
  }
}
