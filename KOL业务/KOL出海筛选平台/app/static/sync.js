"use strict";

const SYNC_LABELS = {
  offline: "离线",
  syncing: "同步中",
  synced: "已同步",
  conflict: "存在冲突",
  failed: "同步失败",
};

async function loadSyncStatus() {
  const button = document.getElementById("sync-status");
  try {
    const status = await api("/sync/status");
    button.dataset.state = status.state;
    button.textContent = status.state === "offline" && status.pending
      ? `离线 · 待同步 ${status.pending}`
      : status.state === "conflict"
        ? `冲突 ${status.conflicts}`
        : SYNC_LABELS[status.state];
  } catch (error) {
    button.dataset.state = "failed";
    button.textContent = SYNC_LABELS.failed;
  }
}

async function runSyncNow() {
  const button = document.getElementById("sync-status");
  button.dataset.state = "syncing";
  button.textContent = SYNC_LABELS.syncing;
  try {
    const result = await api("/sync/run", {method: "POST"});
    showStatus(`同步完成：上传 ${result.pushed}，下载 ${result.pulled}`);
  } catch (error) {
    button.dataset.state = "failed";
    button.textContent = SYNC_LABELS.failed;
    showStatus(error.message, true);
  }
  await loadSyncStatus();
}
