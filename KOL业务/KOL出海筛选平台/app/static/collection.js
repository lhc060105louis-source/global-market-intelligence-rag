"use strict";

let collectionTimer = null;
let activeCollectionJobId = null;
let collectionPollGeneration = 0;

function stopCollectionPolling() {
  collectionPollGeneration += 1;
  if (collectionTimer !== null) window.clearTimeout(collectionTimer);
  collectionTimer = null;
}

function setCollectionError(message) {
  const error = document.getElementById("collection-error");
  error.textContent = message;
  error.hidden = !message;
  document.getElementById("retry-collection").hidden = !message || activeCollectionJobId === null;
}

function renderCollectionStatus(job) {
  const status = document.getElementById("collection-status");
  const logs = document.getElementById("collection-logs");
  clear(status); clear(logs);
  status.append(el("strong", "", `任务 #${job.id} · ${job.status}`));
  const summary = el("div", "collection-summary");
  [["发现", job.total_found], ["新增", job.created_count], ["更新", job.updated_count], ["跳过", job.skipped_count], ["失败", job.failed_count]].forEach(([label, value]) => {
    const item = el("div", "collection-stat"); item.append(el("span", "", label), el("strong", "", String(value ?? 0))); summary.append(item);
  });
  status.append(summary);
  (job.logs || []).forEach(log => { const item = el("li", log.level === "error" ? "error" : ""); item.textContent = `${log.platform ? `${log.platform} · ` : ""}${log.message}`; logs.append(item); });
}

function openCollectionModal() {
  stopCollectionPolling();
  activeCollectionJobId = null;
  document.getElementById("collection-form").reset();
  clear(document.getElementById("collection-status"));
  clear(document.getElementById("collection-logs"));
  setCollectionError("");
  document.getElementById("view-collected-kols").hidden = true;
  document.getElementById("submit-collection").disabled = false;
  openOverlay("auto-collection-overlay");
}

async function submitCollection(event) {
  event.preventDefault(); stopCollectionPolling();
  activeCollectionJobId = null;
  const form = event.currentTarget, submit = document.getElementById("submit-collection");
  const payload = {keywords: form.keywords.value.split(",").map(value => value.trim()).filter(Boolean), platforms: [...form.platforms.selectedOptions].map(option => option.value), languages: [...form.languages.selectedOptions].map(option => option.value), markets: [...form.markets.selectedOptions].map(option => option.value), limit_per_platform: Number(form.limit_per_platform.value)};
  submit.disabled = true; setCollectionError("");
  try {
    const job = await api("/collections", {method: "POST", body: JSON.stringify(payload)});
    activeCollectionJobId = job.job_id;
    document.getElementById("collection-status").textContent = `采集任务 #${job.job_id} 已启动`;
    await pollCollection(job.job_id);
  } catch (error) {
    submit.disabled = false; setCollectionError(`无法启动任务：${error.message}`);
  }
}

async function pollCollection(jobId) {
  const generation = ++collectionPollGeneration;
  try {
    const job = await api(`/collections/${jobId}`);
    if (generation !== collectionPollGeneration) return;
    renderCollectionStatus(job); setCollectionError("");
    if (["queued", "running"].includes(job.status)) {
      collectionTimer = window.setTimeout(() => pollCollection(jobId), 2000);
      return;
    }
    collectionTimer = null;
    document.getElementById("submit-collection").disabled = false;
    if (["completed", "partial", "partial_failed"].includes(job.status)) {
      await loadKols(); updateDashboard();
      document.getElementById("view-collected-kols").hidden = false;
    }
  } catch (error) {
    if (generation !== collectionPollGeneration) return;
    collectionTimer = null;
    document.getElementById("submit-collection").disabled = false;
    setCollectionError(`获取最新状态失败：${error.message}`);
  }
}

function bindCollectionEvents() {
  document.getElementById("retry-collection").addEventListener("click", () => { setCollectionError(""); pollCollection(activeCollectionJobId); });
  document.getElementById("view-collected-kols").addEventListener("click", () => { closeOverlay(document.getElementById("auto-collection-overlay")); navigate("kol"); });
  window.addEventListener("beforeunload", stopCollectionPolling);
}
