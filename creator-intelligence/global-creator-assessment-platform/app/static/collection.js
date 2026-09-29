"use strict";

let collectionTimer = null;
let activeCollectionJobId = null;
let collectionPollGeneration = 0;
const COLLECTION_STATUS_LABELS = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Partially completed",
  partial_failed: "Partially failed",
  failed: "Failed",
};

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
  status.append(el("strong", "", `Job #${job.id} · ${COLLECTION_STATUS_LABELS[job.status] || job.status}`));
  const summary = el("div", "collection-summary");
  [["Found", job.total_found], ["Created", job.created_count], ["Updated", job.updated_count], ["Skipped", job.skipped_count], ["Failed", job.failed_count]].forEach(([label, value]) => {
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
    document.getElementById("collection-status").textContent = `Collection job #${job.job_id} started.`;
    await pollCollection(job.job_id);
  } catch (error) {
    submit.disabled = false; setCollectionError(`Could not start the job: ${error.message}`);
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
    setCollectionError(`Could not refresh the status: ${error.message}`);
  }
}

function bindCollectionEvents() {
  document.getElementById("retry-collection").addEventListener("click", () => { setCollectionError(""); pollCollection(activeCollectionJobId); });
  document.getElementById("view-collected-kols").addEventListener("click", () => { closeOverlay(document.getElementById("auto-collection-overlay")); navigate("kol"); });
  window.addEventListener("beforeunload", stopCollectionPolling);
}
