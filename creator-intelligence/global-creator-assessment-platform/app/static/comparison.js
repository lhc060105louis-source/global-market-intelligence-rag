"use strict";

const MAX_COMPARISON_KOLS = 4;
const COMPARISON_COMMERCIAL_DIMENSIONS = ["audience_fit", "content_relevance", "interaction_quality", "voc_value", "commercial_efficiency", "brand_fit", "execution_capability"];
const COMPARISON_RISK_DIMENSIONS = ["historical_controversy", "ad_disclosure", "competitor_conflict", "fake_traffic", "data_privacy", "sensitive_audience", "sustainability_claims", "execution_risk"];

function toggleComparison(kolId, checked) {
  if (checked && state.selectedKolIds.size >= MAX_COMPARISON_KOLS) {
    showStatus("You can compare up to four creators. Remove one before selecting another.", true);
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
  if (totals.commercial_score == null || totals.risk_score == null) return "Complete the missing data before deciding.";
  const commercial = totals.commercial_score >= 80 ? "high" : totals.commercial_score >= 65 ? "medium" : "low";
  const risk = totals.risk_score <= 30 ? "low" : totals.risk_score <= 60 ? "medium" : "high";
  const actions = {
    "high:low": "🟢 Strong partnership candidate; prioritize contracting.",
    "high:medium": "🟡 High potential with managed risk; add stronger contract safeguards.",
    "high:high": "🔴 High potential and high risk; request legal review before deciding.",
    "medium:low": "🟢 Reliable partnership candidate; proceed with standard checks.",
    "medium:medium": "🟡 Consider a partnership; look for stronger subject-matter expertise.",
    "low:high": "🔴 Partnership is not recommended; exclude from consideration.",
  };
  return actions[`${commercial}:${risk}`] || "⚪ Decide after reviewing the complete assessment.";
}

function comparisonDimension(kol, dimension) {
  return (kol.score_records || []).find(record => record.dimension === dimension) || {dimension};
}

function dimensionRow(record) {
  const row = el("div", "comparison-dimension");
  const evidence = record.manual_evidence || record.evidence || "No evidence provided";
  const source = record.manual_source || record.source || "No source provided";
  row.append(el("strong", "", record.dimension), el("span", "", record.final_score == null ? "Not provided" : String(Math.round(record.final_score))), el("small", "", `${evidence} · ${source}`));
  return row;
}

function comparisonCard(kol) {
  const totals = kol.score_summary || {};
  const card = el("article", "compare-card");
  card.append(el("h3", "", kol.name || kol.handle || "Unnamed creator"));
  card.append(el("p", "compare-base", `${kol.platform} · ${kol.country} · ${formatNumber(kol.followers)} followers`));
  card.append(el("p", "compare-total", `Commercial score ${totals.commercial_score ?? "Not provided"} · ${Math.round((totals.commercial_completeness || 0) * 100)}% complete`));
  card.append(el("p", "compare-total risk", `Risk score ${totals.risk_score ?? "Not provided"} · ${Math.round((totals.risk_completeness || 0) * 100)}% complete`));
  card.append(el("h4", "", "7 commercial dimensions"));
  COMPARISON_COMMERCIAL_DIMENSIONS.forEach(dimension => card.append(dimensionRow(comparisonDimension(kol, dimension))));
  card.append(el("h4", "", "8 risk dimensions"));
  COMPARISON_RISK_DIMENSIONS.forEach(dimension => card.append(dimensionRow(comparisonDimension(kol, dimension))));
  card.append(el("div", "recommendation", `Recommendation: ${comparisonRecommendation(kol)}`));
  return card;
}

async function renderComparison() {
  if (!state.selectedKolIds.size) return showStatus("Select creators from the list to compare.", true);
  const result = await api("/comparisons", {method: "POST", body: JSON.stringify({kol_ids: [...state.selectedKolIds]})});
  const grid = document.getElementById("comparison-results"); clear(grid);
  result.items.forEach(kol => grid.append(comparisonCard(kol)));
  document.getElementById("comparison-empty").hidden = true;
}
