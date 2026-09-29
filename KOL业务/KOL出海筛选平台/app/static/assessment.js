(function () {
  "use strict";

  function commercialGrade(score) {
    if (score == null) return "待补充";
    return score >= 80 ? "A 级" : score >= 65 ? "B 级" : "C 级";
  }

  function riskLevel(score) {
    if (score == null) return "待补充";
    return score >= 61 ? "高风险" : score >= 31 ? "中风险" : "低风险";
  }

  function scoreColor(score, risk) {
    if (score == null) return "#94A3B8";
    if (risk) return score >= 61 ? "#DC2626" : score >= 31 ? "#D97706" : "#047857";
    return score >= 80 ? "#0D9488" : score >= 65 ? "#2563EB" : "#D97706";
  }

  function clamp(value, minimum = 0, maximum = 100) {
    return Math.min(Math.max(Number(value) || 0, minimum), maximum);
  }

  function calcCommercial(dimensions) {
    const weights = [.20, .15, .15, .15, .15, .10, .10];
    const layers = (dimensions || []).slice(0, weights.length).map(clamp);
    while (layers.length < weights.length) layers.push(0);
    return Math.round(layers.reduce((total, value, index) => total + value * weights[index], 0));
  }

  function calcRisk(dimensions) {
    const weights = [.20, .15, .15, .15, .10, .10, .10, .05];
    const layers = (dimensions || []).slice(0, weights.length).map(clamp);
    while (layers.length < weights.length) layers.push(0);
    return Math.round(layers.reduce((total, value, index) => total + value * weights[index], 0));
  }

  async function calculatePreview(commercialInputs, riskInputs, request) {
    return request("/kols/assessment-preview", {method: "POST", body: JSON.stringify({commercial_inputs: commercialInputs, risk_inputs: riskInputs})});
  }

  window.KolAssessment = {commercialGrade, riskLevel, scoreColor, calcCommercial, calcRisk, calculatePreview};
})();
