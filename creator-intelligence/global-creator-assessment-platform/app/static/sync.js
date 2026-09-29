"use strict";

const SYNC_LABELS = {
  offline: "Offline",
  syncing: "Syncing…",
  synced: "Synced",
  conflict: "Conflicts found",
  failed: "Sync failed",
};

async function loadSyncStatus() {
  const button = document.getElementById("sync-status");
  try {
    const status = await api("/sync/status");
    button.dataset.state = status.state;
    button.textContent = status.state === "offline" && status.pending
      ? `Offline · ${status.pending} pending`
      : status.state === "conflict"
        ? `${status.conflicts} conflict(s)`
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
    showStatus(`Sync complete: ${result.pushed} uploaded, ${result.pulled} downloaded.`);
  } catch (error) {
    button.dataset.state = "failed";
    button.textContent = SYNC_LABELS.failed;
    showStatus(error.message, true);
  }
  await loadSyncStatus();
}
