"use strict";

const MAX_COMPARISON_KOLS = 4;
const COMPARISON_COMMERCIAL_DIMENSIONS = ["audience_fit", "content_relevance", "interaction_quality", "voc_value", "commercial_efficiency", "brand_fit", "execution_capability"];
const COMPARISON_RISK_DIMENSIONS = ["historical_controversy", "ad_disclosure", "competitor_conflict", "fake_traffic", "data_privacy", "sensitive_audience", "sustainability_claims", "execution_risk"];

function toggleComparison(kolId, checked) {
  if (checked && state.selectedKolIds.size >= MAX_COMPARISON_KOLS) {
    showStatus("最多对比 4 位 KOL，请先取消一位后再选。", true);
    renderKOLPage();
    return false;
  }
  if (checked) state.selectedKolIds.add(kolId); else state.selectedKolIds.delete(kolId);
  updateSelectionUI();
  return true;
}

function updateComparisonControls() {
  document.querySelectorAll(".kol-card input[type=checkbox]").forEach(checkbox => {
    checkbox.disabled = !checkbox.checked && state.selectedKolIds.size >= MAX_COMPARISON_KOLS;
  });
}

function comparisonRecommendation(kol) {
  const totals = kol.score_summary || {};
  if (totals.commercial_score == null || totals.risk_score == null) return "补充数据后决策";
  const commercial = totals.commercial_score >= 80 ? "high" : totals.commercial_score >= 65 ? "medium" : "low";
  const risk = totals.risk_score <= 30 ? "low" : totals.risk_score <= 60 ? "medium" : "high";
  const actions = {
    "high:low": "🟢 强烈推荐合作，优先推进签约",
    "high:medium": "🟡 高价值但需管控风险，合同中加强约束条款",
    "high:high": "🔴 高价值但高风险，进入法务复核流程后再决策",
    "medium:low": "🟢 稳健合作对象，正常推进",
    "medium:medium": "🟡 可考虑合作，关注内容专业度提升",
    "low:high": "🔴 不建议合作，直接排除",
  };
  return actions[`${commercial}:${risk}`] || "⚪ 综合评估后决策";
}

function comparisonDimension(kol, dimension) {
  return (kol.score_records || []).find(record => record.dimension === dimension) || {dimension};
}

function dimensionRow(record) {
  const row = el("div", "comparison-dimension");
  const evidence = record.manual_evidence || record.evidence || "无证据";
  const source = record.manual_source || record.source || "无来源";
  row.append(el("strong", "", record.dimension), el("span", "", record.final_score == null ? "待补充" : String(Math.round(record.final_score))), el("small", "", `${evidence} · ${source}`));
  return row;
}

function comparisonCard(kol) {
  const totals = kol.score_summary || {};
  const card = el("article", "compare-card");
  card.append(el("h3", "", kol.name || kol.handle || "未命名 KOL"));
  card.append(el("p", "compare-base", `${kol.platform} · ${kol.country} · ${formatNumber(kol.followers)} 粉丝`));
  card.append(el("p", "compare-total", `商业价值 ${totals.commercial_score ?? "待补充"} · 完整度 ${Math.round((totals.commercial_completeness || 0) * 100)}%`));
  card.append(el("p", "compare-total risk", `风险 ${totals.risk_score ?? "待补充"} · 完整度 ${Math.round((totals.risk_completeness || 0) * 100)}%`));
  card.append(el("h4", "", "7 项商业维度"));
  COMPARISON_COMMERCIAL_DIMENSIONS.forEach(dimension => card.append(dimensionRow(comparisonDimension(kol, dimension))));
  card.append(el("h4", "", "8 项风险维度"));
  COMPARISON_RISK_DIMENSIONS.forEach(dimension => card.append(dimensionRow(comparisonDimension(kol, dimension))));
  card.append(el("div", "recommendation", `建议：${comparisonRecommendation(kol)}`));
  return card;
}

async function renderComparison() {
  if (!state.selectedKolIds.size) return showStatus("请先在 KOL 列表中选择对比对象", true);
  const result = await api("/comparisons", {method: "POST", body: JSON.stringify({kol_ids: [...state.selectedKolIds]})});
  const grid = document.getElementById("comparison-results"); clear(grid);
  result.items.forEach(kol => grid.append(comparisonCard(kol)));
  document.getElementById("comparison-empty").hidden = true;
}
