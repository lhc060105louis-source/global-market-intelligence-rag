"use strict";

const postState = {view: "overview", kol: "@AutoBildDE", crisis: null, initialized: false};

function postEscape(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function postNumber(value) {
  return new Intl.NumberFormat("en-US", {notation: "compact", maximumFractionDigits: 2}).format(Number(value || 0));
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
      ${monitorMetric("Total impressions / views", postNumber(m.impressions), "To date")}
      ${monitorMetric("Total engagements", postNumber(m.engagements), "To date")}
      ${monitorMetric("Total conversions", postNumber(m.conversions), "Tracked results")}
      ${monitorMetric("Average engagement rate", `${m.engagement_rate}%`, "Current campaign")}
      ${monitorMetric("Target completion", `${m.target_completion}%`, "Campaign target")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Target Completion</h3></div>
        <div class="monitor-performance">${Object.entries(data.targets || {}).map(([name, item]) => `<div><span>${postEscape(name)}</span><strong>${postNumber(item.actual)} / ${postNumber(item.target)}</strong></div>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Platform Performance</h3></div>
        <div class="monitor-list">${data.platforms.map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>Impressions ${postNumber(item.impressions)}</small></span><em>${item.engagement_rate}%</em></div>`).join("")}</div>
      </article>
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Creator Performance Ranking</h3></div>
        <div class="monitor-list">${data.ranking.map((item, index) => `<button class="monitor-list-row" data-post-kol="${postEscape(item.kol)}" type="button"><b>#${index + 1}</b><span><strong>${postEscape(item.kol)}</strong><small>${postEscape(item.platform)} · ${postNumber(item.impressions)} impressions</small></span><em>${item.completion}%</em></button>`).join("")}</div>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Content Highlights</h3></div>
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
      <article class="content-card monitor-review-head"><div><small>${postEscape(data.platform)} · ${postEscape(data.handle)}</small><h3>${postEscape(data.name)}</h3></div><div class="monitor-head-badges"><span>Target completion ${data.target_completion ?? "—"}%</span><span>Content quality ${data.content_quality ?? "—"}/100</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("Impressions / views", postNumber(data.impressions), "Campaign contribution")}
      ${monitorMetric("Total engagements", postNumber(data.engagements), "All engagements")}
      ${monitorMetric("Conversions", postNumber(data.conversions), "Tracked results")}
      ${monitorMetric("Share of impressions", `${data.contribution ?? "—"}%`, "Campaign impressions")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Content Performance</h3></div>
        <table class="monitor-table"><thead><tr><th>Content</th><th>Platform</th><th>Impressions</th><th>Engagement Rate</th><th>Conversions</th><th>Result</th></tr></thead><tbody>${contents.map(item => `<tr><td>${postEscape(item.title)}</td><td>${postEscape(item.platform)}</td><td>${postNumber(item.impressions)}</td><td>${item.engagement_rate ?? 0}%</td><td>${postNumber(item.conversions)}</td><td>${postEscape(item.result)}</td></tr>`).join("")}</tbody></table>
      </article>
      <article class="content-card monitor-pad">
        <div class="monitor-card-title"><h3>Execution</h3></div>
        <div class="monitor-owner-list">${Object.entries(data.execution || {}).map(([name, value]) => `<div><span>${postEscape(name)}</span><strong>${postEscape(value)}</strong></div>`).join("")}</div>
      </article>
    </div>
    <div class="monitor-actions"><button class="tb-btn teal" data-post-view="sentiment" type="button">View Content & Sentiment</button></div>`;
  document.getElementById("post-kol").querySelector("[data-post-view]").addEventListener("click", () => switchPostView("sentiment"));
}

async function loadPostSentiment() {
  initPostCampaignModule();
  const data = await api("/post-campaign/sentiment");
  document.getElementById("post-sentiment").innerHTML = `
    <article class="content-card monitor-context"><div><strong>${postEscape(data.content)}</strong><small>${postEscape(data.kol)} · Sample of ${postNumber(data.sample_size)} engagements</small></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("Positive", `${data.positive}%`, "Audience sentiment")}
      ${monitorMetric("Neutral", `${data.neutral}%`, "Audience sentiment")}
      ${monitorMetric("Negative", `${data.negative}%`, "Audience sentiment", true)}
      ${monitorMetric("Brand awareness", `${data.brand_attitude?.before}% → ${data.brand_attitude?.after}%`, "Before and after publication")}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Trending Topics</h3></div><div class="monitor-list">${(data.topics || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>${postEscape(item.sentiment)}</small></span><em>${item.share}%</em></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Vehicle Feedback</h3></div><div class="monitor-list">${(data.vehicle_feedback || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong><small>${postEscape(item.note)}</small></span><em>${item.score}</em></div>`).join("")}</div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Related Risks</h3></div><div class="monitor-list">${(data.risk_items || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.name)}</strong></span><em>${postEscape(item.status)}</em></div>`).join("")}</div></article>
    <div class="monitor-actions"><button class="tb-btn teal" data-post-view="review" type="button">Open Partnership Review</button></div>`;
  document.getElementById("post-sentiment").querySelector("[data-post-view]").addEventListener("click", () => switchPostView("review"));
}

async function loadPostReview() {
  initPostCampaignModule();
  const data = await api("/post-campaign/review");
  const choices = ["Recommend Continuing the Partnership", "Continue with Conditions", "Adjust the Partnership Approach", "Do Not Continue Yet"];
  document.getElementById("post-review").innerHTML = `
    <div class="monitor-metrics">${Object.entries(data.scores || {}).map(([name, score]) => monitorMetric(name, score, "Review score")).join("")}</div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Review Summary</h3><strong>${data.overall_score}/100</strong></div><p>${postEscape(data.summary)}</p><h4>Key Strengths</h4><ul>${(data.strengths || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul><h4>Key Issues</h4><ul>${(data.issues || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Next Partnership Decision</h3><span>${postEscape(data.status)}</span></div><div class="monitor-remediation">${choices.map(item => `<label><input type="radio" name="post-decision" value="${postEscape(item)}" ${data.decision === item ? "checked" : ""}> ${postEscape(item)}</label>`).join("")}</div><label>Notes<textarea id="post-review-notes" rows="4">${postEscape(data.notes || "")}</textarea></label><div class="monitor-actions"><button id="post-save-decision" class="tb-btn teal" type="button">Save Decision</button></div></article>
    </div>
    <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Recommendations for the Next Partnership</h3></div><ul>${(data.recommendations || []).map(item => `<li>${postEscape(item)}</li>`).join("")}</ul></article>`;
  document.getElementById("post-save-decision").addEventListener("click", async () => {
    const selected = document.querySelector('input[name="post-decision"]:checked');
    if (!selected) return showStatus("Select a partnership decision.", true);
    await api("/post-campaign/review/decision", {method: "POST", body: JSON.stringify({decision: selected.value, notes: document.getElementById("post-review-notes").value})});
    showStatus("Decision saved.");
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
    root.innerHTML = `<div class="empty-state">There are no major creator-level risk incidents.</div>`;
    return;
  }
  const data = await api(`/post-campaign/crises/${encodeURIComponent(crisisCode)}`);
  postState.crisis = data.crisis_code;
  const impact = data.impact || {};
  root.innerHTML = `
      <article class="content-card monitor-review-head risk-head"><div><small>${postEscape(data.crisis_code)} · ${postEscape(data.kol)}</small><h3>${postEscape(data.title)}</h3></div><div class="monitor-head-badges"><span class="risk-label high">${postEscape(data.level)}</span><span>${postEscape(data.status)}</span><span>${data.verified ? "Facts verified" : "Fact verification in progress"}</span></div></article>
    <div class="monitor-metrics">
      ${monitorMetric("Affected campaigns", impact.projects ?? 0, "Partnership campaigns")}
      ${monitorMetric("Blocked content", impact.blocked_contents ?? 0, "Awaiting publication")}
      ${monitorMetric("Published content", impact.published_contents ?? 0, "Brand content")}
      ${monitorMetric("Open tasks", impact.open_tasks ?? 0, "Crisis response", true)}
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Fact Check & Evidence</h3></div><div class="monitor-list">${(data.evidence || []).map(item => `<div class="monitor-list-row"><span><strong>${postEscape(item.source)}</strong><small>${postEscape(item.note)}</small></span><em>${postEscape(item.status)}</em></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Crisis Actions</h3></div><div class="monitor-remediation">${(data.actions || []).map(item => `<div class="${item.done ? "done" : ""}"><b>${item.done ? "✓" : "○"}</b><span>${postEscape(item.label)}</span>${item.done ? "" : `<button class="text-btn" data-crisis-action="${postEscape(item.key)}" type="button">Complete</button>`}</div>`).join("")}</div></article>
    </div>
    <div class="monitor-grid monitor-grid-main">
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Action History</h3></div><div class="monitor-timeline">${(data.timeline || []).map(item => `<div><time>${postEscape(item.time)}</time><b>•</b><span>${postEscape(item.event)}</span></div>`).join("")}</div></article>
      <article class="content-card monitor-pad"><div class="monitor-card-title"><h3>Partnership Response</h3><span>${postEscape(data.decision || "Not confirmed")}</span></div><div class="monitor-remediation">${["Continue Monitoring", "Limit Exposure", "Pause All Partnerships", "Terminate and Disassociate"].map(item => `<label><input type="radio" name="crisis-decision" value="${postEscape(item)}" ${data.decision === item ? "checked" : ""}> ${postEscape(item)}</label>`).join("")}</div><div class="monitor-actions"><button id="crisis-save-decision" class="tb-btn teal" type="button">Confirm Decision</button><button id="crisis-close" class="tb-btn" type="button">Close Incident</button></div></article>
    </div>`;
  document.getElementById("crisis-save-decision").addEventListener("click", saveCrisisDecision);
  document.getElementById("crisis-close").addEventListener("click", closeCurrentCrisis);
}

async function runCrisisAction(action) {
  if (!postState.crisis) return;
  await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/actions/${encodeURIComponent(action)}`, {method: "POST"});
    showStatus("Task updated.");
  await loadCrisisWorkspace(postState.crisis);
}

async function saveCrisisDecision() {
  const selected = document.querySelector('input[name="crisis-decision"]:checked');
  if (!selected) return showStatus("Select a response decision.", true);
  await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/decision`, {method: "POST", body: JSON.stringify({decision: selected.value})});
  showStatus("Decision saved.");
  await loadCrisisWorkspace(postState.crisis);
}

async function closeCurrentCrisis() {
  try {
    await api(`/post-campaign/crises/${encodeURIComponent(postState.crisis)}/close`, {method: "POST"});
  showStatus("Incident closed.");
    await loadCrisisWorkspace();
  } catch (error) {
    showStatus(error.message, true);
  }
}
