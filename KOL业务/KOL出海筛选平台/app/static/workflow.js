"use strict";

async function advanceWorkflow(kolId) {
  const nextStage = state.stage + 1;
  await api(`/kols/${kolId}/workflow`, {method: "PUT", body: JSON.stringify({stage: nextStage})});
  await loadKols(state.currentQuery, {skipEnrichment: true});
  showStatus("合作阶段已保存");
}
